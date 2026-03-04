import json
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..idempotency import read_idempotency, write_idempotency
from ..models import (
    Inventory,
    Material,
    Project,
    StockDraft,
    StockInItem,
    StockInOrder,
    StockMovement,
    StockOutItem,
    StockOutOrder,
    User,
    Warehouse,
)
from ..schemas import StockInCreate, StockOrderItemInput, StockOutCreate
from ..utils.text import normalized_lower, payload_text


def order_no(prefix: str, db: Session, order_model) -> str:
    date_part = datetime.now().strftime("%Y%m%d")
    base = f"{prefix}{date_part}"
    last_order_no = db.scalar(
        select(order_model.order_no)
        .where(order_model.order_no.like(f"{base}%"))
        .order_by(order_model.order_no.desc())
    )
    seq = 1
    if last_order_no and len(last_order_no) >= len(base) + 3:
        tail = last_order_no[len(base):]
        if tail.isdigit():
            seq = int(tail) + 1
    return f"{base}{seq:03d}"


def inventory_row(db: Session, material_id: int, warehouse_id: int) -> Inventory:
    row = db.scalar(select(Inventory).where(Inventory.material_id == material_id, Inventory.warehouse_id == warehouse_id))
    if row:
        return row
    db.execute(
        text(
            "INSERT OR IGNORE INTO inventory (material_id, warehouse_id, qty, updated_at) "
            "VALUES (:material_id, :warehouse_id, :qty, CURRENT_TIMESTAMP)"
        ),
        {"material_id": material_id, "warehouse_id": warehouse_id, "qty": "0.000"},
    )
    row = db.scalar(select(Inventory).where(Inventory.material_id == material_id, Inventory.warehouse_id == warehouse_id))
    if row:
        return row
    raise HTTPException(status_code=500, detail="库存初始化失败")


def default_warehouse(db: Session) -> Warehouse:
    row = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()))
    if row:
        return row
    row = Warehouse(name="主仓库")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_stock_in(
    payload: StockInCreate,
    db: Session,
    current_user: User,
    project: Project,
    x_idempotency_key: str | None = None,
) -> dict:
    cache_key = ""
    key_part = (x_idempotency_key or "").strip()
    if key_part:
        cache_key = f"in:{project.id}:{current_user.id}:{key_part}"
        cached = read_idempotency(db, cache_key)
        if cached:
            return cached

    warehouse = db.get(Warehouse, payload.warehouse_id) if payload.warehouse_id else default_warehouse(db)
    if not warehouse:
        warehouse = default_warehouse(db)
    if not payload.items:
        raise HTTPException(status_code=400, detail="入库明细不能为空")

    order = None
    for _ in range(3):
        try:
            order = StockInOrder(
                project_id=project.id,
                order_no=order_no("IN", db, StockInOrder),
                warehouse_id=warehouse.id,
                operator_name=current_user.username,
                note=payload.note,
            )
            db.add(order)
            db.flush()
            break
        except IntegrityError:
            db.rollback()
            continue
    if not order:
        raise HTTPException(status_code=500, detail="生成入库单号失败，请重试")

    for item in payload.items:
        material = db.get(Material, item.material_id)
        if not material or not material.is_active:
            raise HTTPException(status_code=400, detail=f"材料不可用: {item.material_id}")
        if material.project_id != project.id:
            raise HTTPException(status_code=400, detail=f"材料不属于当前工程: {item.material_id}")
        detail = StockInItem(order_id=order.id, material_id=item.material_id, qty=item.qty, remark=item.remark)
        db.add(detail)
        db.flush()

        inv = inventory_row(db, item.material_id, warehouse.id)
        db.execute(
            text("UPDATE inventory SET qty = qty + :delta, updated_at = CURRENT_TIMESTAMP WHERE id = :inv_id"),
            {"delta": str(item.qty), "inv_id": inv.id},
        )
        inv_qty = db.scalar(select(Inventory.qty).where(Inventory.id == inv.id))
        current_qty = Decimal(inv_qty or "0")

        db.add(
            StockMovement(
                project_id=project.id,
                material_id=item.material_id,
                warehouse_id=warehouse.id,
                movement_type="in",
                order_type="stock_in",
                order_id=order.id,
                item_id=detail.id,
                qty=item.qty,
                balance_after=current_qty,
                operator_name=order.operator_name,
                note=order.note,
            )
        )

    db.commit()
    result = {"id": order.id, "order_no": order.order_no}
    if cache_key:
        try:
            write_idempotency(db, cache_key, result)
            db.commit()
        except IntegrityError:
            db.rollback()
    return result


def create_stock_out(
    payload: StockOutCreate,
    db: Session,
    current_user: User,
    project: Project,
    x_idempotency_key: str | None = None,
) -> dict:
    cache_key = ""
    key_part = (x_idempotency_key or "").strip()
    if key_part:
        cache_key = f"out:{project.id}:{current_user.id}:{key_part}"
        cached = read_idempotency(db, cache_key)
        if cached:
            return cached

    warehouse = db.get(Warehouse, payload.warehouse_id) if payload.warehouse_id else default_warehouse(db)
    if not warehouse:
        warehouse = default_warehouse(db)
    if not payload.items:
        raise HTTPException(status_code=400, detail="出库明细不能为空")

    order = None
    for _ in range(3):
        try:
            order = StockOutOrder(
                project_id=project.id,
                order_no=order_no("OUT", db, StockOutOrder),
                warehouse_id=warehouse.id,
                operator_name=current_user.username,
                receiver_name=payload.receiver_name,
                usage=payload.usage,
                work_area=payload.work_area,
                note=payload.note,
            )
            db.add(order)
            db.flush()
            break
        except IntegrityError:
            db.rollback()
            continue
    if not order:
        raise HTTPException(status_code=500, detail="生成出库单号失败，请重试")

    try:
        for item in payload.items:
            material = db.get(Material, item.material_id)
            if not material or not material.is_active:
                raise HTTPException(status_code=400, detail=f"材料不可用: {item.material_id}")
            if material.project_id != project.id:
                raise HTTPException(status_code=400, detail=f"材料不属于当前工程: {item.material_id}")

            inv = inventory_row(db, item.material_id, warehouse.id)
            delta = str(item.qty)
            updated = db.execute(
                text(
                    "UPDATE inventory "
                    "SET qty = qty - :delta, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :inv_id AND qty >= :delta"
                ),
                {"delta": delta, "inv_id": inv.id},
            )
            if int(updated.rowcount or 0) <= 0:
                raise HTTPException(status_code=400, detail=f"库存不足: {material.name}")

            detail = StockOutItem(order_id=order.id, material_id=item.material_id, qty=item.qty, remark=item.remark)
            db.add(detail)
            db.flush()

            inv_qty = db.scalar(select(Inventory.qty).where(Inventory.id == inv.id))
            current_qty = Decimal(inv_qty or "0")
            db.add(
                StockMovement(
                    project_id=project.id,
                    material_id=item.material_id,
                    warehouse_id=warehouse.id,
                    movement_type="out",
                    order_type="stock_out",
                    order_id=order.id,
                    item_id=detail.id,
                    qty=item.qty,
                    balance_after=current_qty,
                    operator_name=order.operator_name,
                    note=order.note,
                )
            )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="出库失败，请重试") from exc

    db.commit()
    result = {"id": order.id, "order_no": order.order_no}
    if cache_key:
        try:
            write_idempotency(db, cache_key, result)
            db.commit()
        except IntegrityError:
            db.rollback()
    return result


def stock_draft_type_or_400(draft_type: str) -> str:
    normalized = normalized_lower(draft_type)
    if normalized not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="草稿类型无效")
    return normalized


def load_stock_draft(db: Session, project_id: int, user_id: int, draft_type: str) -> StockDraft | None:
    return db.scalar(
        select(StockDraft).where(
            and_(
                StockDraft.project_id == project_id,
                StockDraft.user_id == user_id,
                StockDraft.draft_type == draft_type,
            )
        )
    )


def commit_stock_draft(draft_type: str, db: Session, current_user: User, project: Project) -> dict:
    kind = stock_draft_type_or_400(draft_type)
    row = load_stock_draft(db, project.id, current_user.id, kind)
    if not row:
        raise HTTPException(status_code=400, detail="暂无待入账草稿")
    try:
        items_raw = json.loads(row.payload_json or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="草稿数据损坏，请重新录入") from exc
    if not isinstance(items_raw, list) or not items_raw:
        raise HTTPException(status_code=400, detail="暂无待入账草稿")

    normalized_items = []
    for item in items_raw:
        try:
            material_id = int(item.get("material_id", 0))
            qty = Decimal(str(item.get("qty", "0")))
        except (ArithmeticError, TypeError, ValueError):
            continue
        if material_id <= 0 or qty <= Decimal("0"):
            continue
        normalized_items.append(
            {
                "material_id": material_id,
                "qty": qty,
                "remark": f"{item.get('remark', '')}".strip(),
            }
        )

    if not normalized_items:
        raise HTTPException(status_code=400, detail="草稿内容无有效明细")

    if kind == "in":
        result = create_stock_in(
            StockInCreate(items=normalized_items, note=""),
            db,
            current_user,
            project,
            None,
        )
    else:
        result = create_stock_out(
            StockOutCreate(items=normalized_items, note="", receiver_name="", usage="", work_area=""),
            db,
            current_user,
            project,
            None,
        )

    row.payload_json = "[]"
    db.commit()
    return {"ok": True, "result": result}


def correct_stock_record(payload: dict, db: Session, current_user: User, project: Project) -> dict:
    kind = normalized_lower(payload.get("record_type"))
    order_no_value = payload_text(payload, "order_no")
    reason = payload_text(payload, "reason")
    if kind not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="记录类型无效")
    if not order_no_value:
        raise HTTPException(status_code=400, detail="单号不能为空")
    if not reason:
        raise HTTPException(status_code=400, detail="请填写更正原因")

    if kind == "in":
        origin = db.scalar(
            select(StockInOrder).where(
                and_(
                    StockInOrder.project_id == project.id,
                    StockInOrder.order_no == order_no_value,
                    StockInOrder.status == "normal",
                )
            )
        )
        if not origin:
            raise HTTPException(status_code=404, detail="原入库记录不存在或已处理")
        origin_items = db.scalars(select(StockInItem).where(StockInItem.order_id == origin.id)).all()
        if not origin_items:
            raise HTTPException(status_code=400, detail="原记录无明细，无法更正")
        result = create_stock_out(
            StockOutCreate(
                warehouse_id=origin.warehouse_id,
                operator_name=current_user.username,
                receiver_name="更正冲正",
                usage="冲正",
                work_area="",
                note=f"冲正原入库单 {origin.order_no}，原因：{reason}",
                items=[
                    StockOrderItemInput(
                        material_id=item.material_id,
                        qty=Decimal(item.qty),
                        remark=f"冲正 {origin.order_no}",
                    )
                    for item in origin_items
                ],
            ),
            db,
            current_user,
            project,
            None,
        )
        origin.status = "corrected"
        db.commit()
        return {"ok": True, "corrected_order_no": result["order_no"]}

    origin = db.scalar(
        select(StockOutOrder).where(
            and_(
                StockOutOrder.project_id == project.id,
                StockOutOrder.order_no == order_no_value,
                StockOutOrder.status == "normal",
            )
        )
    )
    if not origin:
        raise HTTPException(status_code=404, detail="原出库记录不存在或已处理")
    origin_items = db.scalars(select(StockOutItem).where(StockOutItem.order_id == origin.id)).all()
    if not origin_items:
        raise HTTPException(status_code=400, detail="原记录无明细，无法更正")

    result = create_stock_in(
        StockInCreate(
            warehouse_id=origin.warehouse_id,
            operator_name=current_user.username,
            note=f"冲正原出库单 {origin.order_no}，原因：{reason}",
            items=[
                StockOrderItemInput(
                    material_id=item.material_id,
                    qty=Decimal(item.qty),
                    remark=f"冲正 {origin.order_no}",
                )
                for item in origin_items
            ],
        ),
        db,
        current_user,
        project,
        None,
    )
    origin.status = "corrected"
    db.commit()
    return {"ok": True, "corrected_order_no": result["order_no"]}
