from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import require_project as _require_project, require_user as _require_user
from .models import Inventory, MachineLedger, Project, User
from .schemas import InventoryDeleteRequest, MaterialCreate, MaterialDeleteRequest, MaterialUpdate
from .services.exports import build_inventory_export, build_machine_ledger_export
from .services.logs_and_ledger import (
    machine_ledger_create as _machine_ledger_create,
    machine_ledger_delete as _machine_ledger_delete,
    machine_ledger_list as _machine_ledger_list,
    machine_ledger_update as _machine_ledger_update,
)
from .services.materials_inventory import (
    create_material as _create_material,
    delete_inventory_rows as _delete_inventory_rows,
    delete_materials as _delete_materials,
    inventory_list as _inventory_list,
    list_materials as _list_materials,
    update_material as _update_material,
)
from .models import Material
from .security import verify_password

router = APIRouter(prefix="/api")


@router.post("/materials")
def create_material(payload: MaterialCreate, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _create_material(payload, db, project)


@router.get("/materials")
def list_materials(keyword: str = "", page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> list[dict] | dict:
    return _list_materials(keyword, db, project, page=page, page_size=page_size)


@router.put("/materials/{material_id}")
def update_material(material_id: int, payload: MaterialUpdate, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _update_material(material_id, payload, db, project)


@router.post("/materials/delete")
def delete_materials(payload: MaterialDeleteRequest, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _delete_materials(payload, db, project)


@router.get("/inventory")
def inventory_list(keyword: str = "", page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> list[dict] | dict:
    return _inventory_list(keyword, db, project, page=page, page_size=page_size)


@router.get("/machine-ledger")
def machine_ledger_list(keyword: str = "", page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> list[dict] | dict:
    return _machine_ledger_list(keyword, db, project, page=page, page_size=page_size)


@router.post("/machine-ledger")
def machine_ledger_create(payload: dict, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _machine_ledger_create(payload, db, project)


@router.put("/machine-ledger/{row_id}")
def machine_ledger_update(row_id: int, payload: dict, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _machine_ledger_update(row_id, payload, db, project)


@router.post("/machine-ledger/delete")
def machine_ledger_delete(payload: dict, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _machine_ledger_delete(payload, db, project)


@router.post("/inventory/delete")
def delete_inventory_rows(payload: InventoryDeleteRequest, db: Session = Depends(get_db), current_user: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _delete_inventory_rows(payload=payload, db=db, project=project, password_ok=verify_password(payload.password, current_user.password_hash))


@router.get("/export/inventory")
def export_inventory(db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> StreamingResponse:
    rows = db.scalars(
        select(Inventory)
        .join(Material, Inventory.material_id == Material.id)
        .where(Material.project_id == project.id, Material.is_active.is_(True))
        .order_by(Inventory.id.desc())
    ).all()
    return build_inventory_export(rows)


@router.get("/export/machine-ledger")
def export_machine_ledger(keyword: str = "", db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> StreamingResponse:
    rows = db.scalars(select(MachineLedger).where(MachineLedger.project_id == project.id).order_by(MachineLedger.id.desc())).all()
    return build_machine_ledger_export(rows, keyword=keyword)
