import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import require_project as _require_project, require_user as _require_user
from .models import Material, Project, StockDraft, StockInItem, StockInOrder, StockOutItem, StockOutOrder, User
from .services.exports import build_stock_records_export
from .services.stock_flow import (
    commit_stock_draft as _commit_stock_draft,
    correct_stock_record as _correct_stock_record,
    create_stock_in as _create_stock_in,
    create_stock_out as _create_stock_out,
    load_stock_draft as _load_stock_draft,
    stock_draft_type_or_400 as _stock_draft_type_or_400,
)
from .utils.number_format import dec_fixed_3
from .schemas import StockInCreate, StockOutCreate

router = APIRouter(prefix="/api")


@router.post("/stock-in")
def create_stock_in(
    payload: StockInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    x_idempotency_key: str | None = Header(default=None),
) -> dict:
    return _create_stock_in(payload, db, current_user, project, x_idempotency_key)


@router.post("/stock-out")
def create_stock_out(
    payload: StockOutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    x_idempotency_key: str | None = Header(default=None),
) -> dict:
    return _create_stock_out(payload, db, current_user, project, x_idempotency_key)


@router.get("/stock-drafts/{draft_type}")
def get_stock_draft(
    draft_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    kind = _stock_draft_type_or_400(draft_type)
    row = _load_stock_draft(db, project.id, current_user.id, kind)
    if not row:
        return {"items": [], "updated_at": ""}
    try:
        items = json.loads(row.payload_json or "[]")
        if not isinstance(items, list):
            items = []
    except json.JSONDecodeError:
        items = []
    return {"items": items, "updated_at": row.updated_at.isoformat() if row.updated_at else ""}


@router.put("/stock-drafts/{draft_type}")
def save_stock_draft(
    draft_type: str,
    payload: list[dict] = Body(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    kind = _stock_draft_type_or_400(draft_type)
    row = _load_stock_draft(db, project.id, current_user.id, kind)
    data = json.dumps(payload or [], ensure_ascii=False)
    if not row:
        row = StockDraft(project_id=project.id, user_id=current_user.id, draft_type=kind, payload_json=data)
        db.add(row)
    else:
        row.payload_json = data
    db.commit()
    db.refresh(row)
    return {"ok": True, "updated_at": row.updated_at.isoformat() if row.updated_at else ""}


@router.get("/stock-drafts/pending/count")
def stock_draft_pending_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    rows = db.scalars(
        select(StockDraft).where(and_(StockDraft.project_id == project.id, StockDraft.user_id == current_user.id))
    ).all()
    result = {"in": 0, "out": 0}
    for row in rows:
        try:
            items = json.loads(row.payload_json or "[]")
            count = len(items) if isinstance(items, list) else 0
        except json.JSONDecodeError:
            count = 0
        if row.draft_type in result:
            result[row.draft_type] = count
    result["total"] = result["in"] + result["out"]
    return result


@router.post("/stock-drafts/{draft_type}/commit")
def commit_stock_draft(
    draft_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _commit_stock_draft(draft_type, db, current_user, project)


@router.get("/stock-records")
def list_stock_records(
    record_type: str = Query(default="all"),
    keyword: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    kind = (record_type or "all").strip().lower()
    if kind not in {"all", "in", "out"}:
        raise HTTPException(status_code=400, detail="记录类型无效")

    kw = (keyword or "").strip().lower()
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from e

    in_summary = (
        select(
            StockInOrder.id.label("order_id"),
            literal("in").label("type"),
            StockInOrder.order_no.label("raw_order_no"),
            StockInOrder.created_at.label("created_at"),
            StockInOrder.operator_name.label("operator_name"),
            func.ifnull(StockInOrder.note, "").label("note"),
            func.ifnull(StockInOrder.note, "").label("remark"),
            func.group_concat(func.distinct(func.ifnull(Material.name, ""))).label("materials_summary"),
            func.group_concat(func.distinct(func.ifnull(Material.spec, ""))).label("specs_summary"),
            func.sum(StockInItem.qty).label("total_qty"),
            func.count(StockInItem.id).label("item_count"),
            func.count(func.distinct(func.ifnull(Material.unit, ""))).label("unit_count"),
            func.min(func.ifnull(Material.unit, "")).label("single_unit"),
        )
        .join(StockInItem, StockInItem.order_id == StockInOrder.id)
        .join(Material, Material.id == StockInItem.material_id)
        .where(StockInOrder.project_id == project.id, StockInOrder.status == "normal")
        .group_by(StockInOrder.id)
    )

    out_summary = (
        select(
            StockOutOrder.id.label("order_id"),
            literal("out").label("type"),
            StockOutOrder.order_no.label("raw_order_no"),
            StockOutOrder.created_at.label("created_at"),
            StockOutOrder.operator_name.label("operator_name"),
            func.ifnull(StockOutOrder.note, "").label("note"),
            func.ifnull(StockOutOrder.note, "").label("remark"),
            func.group_concat(func.distinct(func.ifnull(Material.name, ""))).label("materials_summary"),
            func.group_concat(func.distinct(func.ifnull(Material.spec, ""))).label("specs_summary"),
            func.sum(StockOutItem.qty).label("total_qty"),
            func.count(StockOutItem.id).label("item_count"),
            func.count(func.distinct(func.ifnull(Material.unit, ""))).label("unit_count"),
            func.min(func.ifnull(Material.unit, "")).label("single_unit"),
        )
        .join(StockOutItem, StockOutItem.order_id == StockOutOrder.id)
        .join(Material, Material.id == StockOutItem.material_id)
        .where(StockOutOrder.project_id == project.id, StockOutOrder.status == "normal")
        .group_by(StockOutOrder.id)
    )

    if kind == "in":
        base_union = in_summary.subquery("records")
    elif kind == "out":
        base_union = out_summary.subquery("records")
    else:
        base_union = union_all(in_summary, out_summary).subquery("records")

    filters = []
    if start_dt:
        filters.append(func.date(base_union.c.created_at) >= start_dt.strftime("%Y-%m-%d"))
    if end_dt:
        filters.append(func.date(base_union.c.created_at) <= end_dt.strftime("%Y-%m-%d"))
    if kw:
        like_kw = f"%{kw}%"
        filters.append(
            or_(
                func.lower(func.ifnull(base_union.c.raw_order_no, "")).like(like_kw),
                func.lower(func.ifnull(base_union.c.operator_name, "")).like(like_kw),
                func.lower(func.ifnull(base_union.c.note, "")).like(like_kw),
                func.lower(func.ifnull(base_union.c.remark, "")).like(like_kw),
                func.lower(func.ifnull(base_union.c.materials_summary, "")).like(like_kw),
                func.lower(func.ifnull(base_union.c.specs_summary, "")).like(like_kw),
            )
        )

    total_stmt = select(func.count()).select_from(base_union)
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = int(db.scalar(total_stmt) or 0)

    data_stmt = (
        select(
            base_union.c.type,
            base_union.c.raw_order_no,
            base_union.c.created_at,
            base_union.c.operator_name,
            base_union.c.note,
            base_union.c.remark,
            base_union.c.materials_summary,
            base_union.c.specs_summary,
            base_union.c.total_qty,
            base_union.c.item_count,
            case((base_union.c.unit_count <= 1, base_union.c.single_unit), else_="混合").label("unit"),
        )
        .where(*filters)
        .order_by(base_union.c.created_at.desc(), base_union.c.raw_order_no.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(data_stmt).mappings().all()

    items = []
    for row in rows:
        created_at = row.get("created_at")
        created_iso = created_at.isoformat() if created_at else ""
        materials_summary_parts = [x for x in (row.get("materials_summary") or "").split(",") if x]
        specs_summary_parts = [x for x in (row.get("specs_summary") or "").split(",") if x]
        items.append(
            {
                "type": row.get("type") or "",
                "order_no": row.get("raw_order_no") or "",
                "raw_order_no": row.get("raw_order_no") or "",
                "created_at": created_iso,
                "operator_name": row.get("operator_name") or "",
                "note": row.get("note") or "",
                "remark": row.get("remark") or "",
                "materials_summary": "、".join(materials_summary_parts[:3]) + ("..." if len(materials_summary_parts) > 3 else ""),
                "specs_summary": "、".join(specs_summary_parts[:3]) + ("..." if len(specs_summary_parts) > 3 else ""),
                "unit": row.get("unit") or "",
                "item_count": int(row.get("item_count") or 0),
                "total_qty": dec_fixed_3(row.get("total_qty") or "0"),
            }
        )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/stock-records/correct")
def correct_stock_record(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _correct_stock_record(payload, db, current_user, project)


@router.get("/export/stock-records")
def export_stock_records(
    record_type: str = Query(default="all"),
    keyword: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> StreamingResponse:
    kind = (record_type or "").strip().lower()
    if kind not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="导出仅支持入库或出库")

    data = list_stock_records(kind, keyword, start_date, end_date, 1, 10000, db, current_user, project)
    rows = data.get("items", [])
    return build_stock_records_export(rows, kind)


@router.get("/stock-records/{record_type}/{order_no}")
def stock_record_detail(
    record_type: str,
    order_no: str,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    kind = (record_type or "").strip().lower()
    if kind not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="记录类型无效")

    if kind == "in":
        order = db.scalar(select(StockInOrder).where(and_(StockInOrder.project_id == project.id, StockInOrder.order_no == order_no)))
        if not order:
            raise HTTPException(status_code=404, detail="记录不存在")
        items = db.scalars(select(StockInItem).where(StockInItem.order_id == order.id)).all()
    else:
        order = db.scalar(select(StockOutOrder).where(and_(StockOutOrder.project_id == project.id, StockOutOrder.order_no == order_no)))
        if not order:
            raise HTTPException(status_code=404, detail="记录不存在")
        items = db.scalars(select(StockOutItem).where(StockOutItem.order_id == order.id)).all()

    detail_items = []
    for item in items:
        material = db.get(Material, item.material_id)
        detail_items.append(
            {
                "material_name": material.name if material else "",
                "material_spec": material.spec if material else "",
                "material_unit": material.unit if material else "",
                "qty": dec_fixed_3(item.qty),
                "remark": item.remark or "",
            }
        )

    return {
        "type": kind,
        "order_no": order.order_no,
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "operator_name": order.operator_name,
        "note": order.note or "",
        "items": detail_items,
    }
