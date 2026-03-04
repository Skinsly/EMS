from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
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
        category="消耗品",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


def list_materials(keyword: str, db: Session, project: Project) -> list[dict]:
    stmt = select(Material).where(Material.project_id == project.id, Material.is_active.is_(True)).order_by(Material.id.desc())
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where((Material.name.like(kw)) | (Material.spec.like(kw)))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "spec": item.spec,
            "unit": item.unit,
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]


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


def inventory_list(keyword: str, db: Session, project: Project) -> list[dict]:
    rows = db.scalars(
        select(Inventory)
        .join(Material, Inventory.material_id == Material.id)
        .where(Material.project_id == project.id, Material.is_active.is_(True))
        .order_by(Inventory.id.desc())
    ).all()
    result: list[dict] = []
    kw = normalized_lower(keyword)
    for row in rows:
        if kw and kw not in (f"{row.material.name} {row.material.spec}".lower()):
            continue
        result.append(
            {
                "id": row.id,
                "material_id": row.material_id,
                "name": row.material.name,
                "spec": row.material.spec,
                "unit": row.material.unit,
                "qty": dec_fixed_3(row.qty),
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
            }
        )
    return result


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
