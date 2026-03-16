from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import require_project as _require_project, require_user as _require_user
from .models import ProgressPlanItem, Project, User
from .schemas import ProgressPlanItemCreate, ProgressPlanItemUpdate

router = APIRouter(prefix="/api/progress-plans")


@router.post("")
def create_progress_plan_item(
    payload: ProgressPlanItemCreate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    task_name = payload.task_name.strip()
    if not task_name:
        raise HTTPException(status_code=400, detail="任务名称不能为空")
    row = ProgressPlanItem(
        project_id=project.id,
        task_name=task_name,
        owner=payload.owner.strip(),
        start_date=payload.start_date.strip(),
        end_date=payload.end_date.strip(),
        progress=payload.progress,
        status=payload.status.strip(),
        predecessor=payload.predecessor.strip(),
        note=payload.note.strip(),
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.get("")
def list_progress_plan_items(
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    rows = db.scalars(
        select(ProgressPlanItem)
        .where(ProgressPlanItem.project_id == project.id)
        .order_by(ProgressPlanItem.sort_order.asc(), ProgressPlanItem.id.asc())
    ).all()
    return [
        {
            "id": row.id,
            "task_name": row.task_name,
            "owner": row.owner,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "progress": row.progress,
            "status": row.status,
            "predecessor": row.predecessor,
            "note": row.note,
            "sort_order": row.sort_order,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.put("/{item_id}")
def update_progress_plan_item(
    item_id: int,
    payload: ProgressPlanItemUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    row = db.get(ProgressPlanItem, item_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="计划任务不存在")
    row.task_name = payload.task_name.strip()
    row.owner = payload.owner.strip()
    row.start_date = payload.start_date.strip()
    row.end_date = payload.end_date.strip()
    row.progress = payload.progress
    row.status = payload.status.strip()
    row.predecessor = payload.predecessor.strip()
    row.note = payload.note.strip()
    row.sort_order = payload.sort_order
    db.commit()
    return {"ok": True}


@router.delete("/{item_id}")
def delete_progress_plan_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    row = db.get(ProgressPlanItem, item_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="计划任务不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}
