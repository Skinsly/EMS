from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import require_project as _require_project, require_user as _require_user
from .models import Project, User
from .schemas import ConstructionLogCreate, ConstructionLogUpdate
from .services.logs_and_ledger import (
    create_construction_log as _create_construction_log,
    delete_construction_log as _delete_construction_log,
    list_construction_logs as _list_construction_logs,
    update_construction_log as _update_construction_log,
)

router = APIRouter(prefix="/api/construction-logs")


@router.post("")
def create_construction_log(
    payload: ConstructionLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _create_construction_log(payload, db, current_user, project)


@router.get("")
def list_construction_logs(
    keyword: str = "",
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict] | dict:
    return _list_construction_logs(db, project, keyword=keyword, page=page, page_size=page_size)


@router.put("/{log_id}")
def update_construction_log(
    log_id: int,
    payload: ConstructionLogUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _update_construction_log(log_id, payload, db, project)


@router.delete("/{log_id}")
def delete_construction_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _delete_construction_log(log_id, db, project)
