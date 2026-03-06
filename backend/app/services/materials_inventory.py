from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Inventory, Material, Project
from ..schemas import InventoryDeleteRequest, MaterialCreate, MaterialDeleteRequest, MaterialUpdate
from ..utils.number_format import dec_fixed_3
from ..utils.id_parse import parse_positive_int_ids
from ..utils.text import normalized_lower


def create_material(payload: MaterialCreate, db: Session, project: Project) -> dict:
    code = f"MAT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    row = Material(
        project_id=project.id,
        code=code,
        name=payload.name.strip(),
        spec=payload.spec.strip(),
        unit=payload.unit.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


def _normalize_page(page: int | None, page_size: int | None) -> tuple[int, int] | None:
    if page is None and page_size is None:
        return None
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(100, int(page_size or 10)))
    return resolved_page, resolved_page_size


def list_materials(keyword: str, db: Session, project: Project, page: int | None = None, page_size: int | None = None) -> list[dict] | dict:
    stmt = select(Material).where(Material.project_id == project.id, Material.is_active.is_(True)).order_by(Material.id.desc())
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where((Material.name.like(kw)) | (Material.spec.like(kw)))
    paging = _normalize_page(page, page_size)
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    if paging:
        page_value, page_size_value = paging
        stmt = stmt.offset((page_value - 1) * page_size_value).limit(page_size_value)
    rows = db.scalars(stmt).all()
    items = [
        {
            "id": item.id,
            "name": item.name,
            "spec": item.spec,
            "unit": item.unit,
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]
    if not paging:
        return items
    page_value, page_size_value = paging
    total_pages = max(1, (total + page_size_value - 1) // page_size_value)
    return {
        "items": items,
        "total": total,
        "page": page_value,
        "page_size": page_size_value,
        "total_pages": total_pages,
    }


def update_material(material_id: int, payload: MaterialUpdate, db: Session, project: Project) -> dict:
    row = db.get(Material, material_id)
    if not row:
        raise HTTPException(status_code=404, detail="材料不存在")
    if row.project_id != project.id:
        raise HTTPException(status_code=403, detail="无权修改该工程材料")
    row.name = payload.name.strip()
    row.spec = payload.spec.strip()
    row.unit = payload.unit.strip()
    db.commit()
    return {"ok": True}


def delete_materials(payload: MaterialDeleteRequest, db: Session, project: Project) -> dict:
    ids = parse_positive_int_ids(payload.material_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的材料")

    rows = db.scalars(select(Material).where(Material.id.in_(ids))).all()
    deleted = 0
    for row in rows:
        if row.project_id != project.id:
            continue
        row.is_active = False
        deleted += 1
    db.commit()
    return {"ok": True, "deleted": deleted}


def inventory_list(keyword: str, db: Session, project: Project, page: int | None = None, page_size: int | None = None) -> list[dict] | dict:
    stmt = (
        select(Inventory)
        .join(Material, Inventory.material_id == Material.id)
        .where(Material.project_id == project.id, Material.is_active.is_(True))
        .order_by(Inventory.id.desc())
    )
    if keyword.strip():
        kw = f"%{normalized_lower(keyword)}%"
        stmt = stmt.where(
            or_(
                func.lower(Material.name).like(kw),
                func.lower(Material.spec).like(kw),
            )
        )
    paging = _normalize_page(page, page_size)
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    if paging:
        page_value, page_size_value = paging
        stmt = stmt.offset((page_value - 1) * page_size_value).limit(page_size_value)

    rows = db.scalars(stmt).all()
    items = [
        {
            "id": row.id,
            "material_id": row.material_id,
            "name": row.material.name,
            "spec": row.material.spec,
            "unit": row.material.unit,
            "qty": dec_fixed_3(row.qty),
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }
        for row in rows
    ]
    if not paging:
        return items
    page_value, page_size_value = paging
    total_pages = max(1, (total + page_size_value - 1) // page_size_value)
    return {
        "items": items,
        "total": total,
        "page": page_value,
        "page_size": page_size_value,
        "total_pages": total_pages,
    }


def delete_inventory_rows(
    payload: InventoryDeleteRequest,
    db: Session,
    project: Project,
    password_ok: bool,
) -> dict:
    ids = parse_positive_int_ids(payload.inventory_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的库存记录")
    if not password_ok:
        raise HTTPException(status_code=400, detail="登录密码错误")

    rows = db.scalars(select(Inventory).where(Inventory.id.in_(ids))).all()
    deleted = 0
    for row in rows:
        if row.material.project_id != project.id:
            continue
        db.delete(row)
        deleted += 1
    db.commit()
    return {"ok": True, "deleted": deleted}
