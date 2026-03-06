from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import Attachment, ConstructionLog, MachineLedger, Project, User
from ..schemas import ConstructionLogCreate, ConstructionLogUpdate
from .attachments import safe_remove_uploaded_file
from ..utils.id_parse import parse_positive_int_ids
from ..utils.number_format import dec_trimmed
from ..utils.text import normalized_lower, payload_text


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_construction_log(payload: ConstructionLogCreate, db: Session, current_user: User, project: Project) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="日志标题不能为空")
    row = ConstructionLog(
        project_id=project.id,
        log_date=payload.log_date.strip(),
        title=title,
        weather=payload.weather.strip(),
        content=payload.content.strip(),
        created_by=current_user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


def list_construction_logs(
    db: Session,
    project: Project,
    keyword: str = "",
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | dict:
    stmt = select(ConstructionLog).where(ConstructionLog.project_id == project.id).order_by(ConstructionLog.id.desc())
    if keyword.strip():
        kw = f"%{normalized_lower(keyword)}%"
        stmt = stmt.where(
            or_(
                func.lower(ConstructionLog.log_date).like(kw),
                func.lower(ConstructionLog.weather).like(kw),
                func.lower(ConstructionLog.content).like(kw),
                func.lower(ConstructionLog.title).like(kw),
            )
        )

    if page is None and page_size is None:
        rows = db.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "log_date": row.log_date,
                "title": row.title,
                "weather": row.weather,
                "content": row.content,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    page_value = max(1, int(page or 1))
    page_size_value = max(1, min(100, int(page_size or 10)))
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    rows = db.scalars(stmt.offset((page_value - 1) * page_size_value).limit(page_size_value)).all()
    items = [
        {
            "id": row.id,
            "log_date": row.log_date,
            "title": row.title,
            "weather": row.weather,
            "content": row.content,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
    total_pages = max(1, (total + page_size_value - 1) // page_size_value)
    return {
        "items": items,
        "total": total,
        "page": page_value,
        "page_size": page_size_value,
        "total_pages": total_pages,
    }


def update_construction_log(log_id: int, payload: ConstructionLogUpdate, db: Session, project: Project) -> dict:
    row = db.get(ConstructionLog, log_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="施工日志不存在")
    title = payload.title.strip()
    if title:
        row.title = title
    row.log_date = payload.log_date.strip()
    row.weather = payload.weather.strip()
    row.content = payload.content.strip()
    db.commit()
    return {"ok": True}


def delete_construction_log(log_id: int, db: Session, project: Project) -> dict:
    row = db.get(ConstructionLog, log_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="施工日志不存在")

    attachments = db.scalars(
        select(Attachment).where(
            Attachment.order_type == "construction_log",
            Attachment.order_id == log_id,
            Attachment.is_deleted.is_(False),
        )
    ).all()
    attachment_paths = [item.path for item in attachments]
    for item in attachments:
        item.is_deleted = True
        item.deleted_at = _utcnow_naive()

    db.delete(row)
    db.commit()

    for file_path in attachment_paths:
        safe_remove_uploaded_file(file_path)

    return {"ok": True}


def machine_ledger_list(
    keyword: str,
    db: Session,
    project: Project,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | dict:
    stmt = (
        select(MachineLedger)
        .where(MachineLedger.project_id == project.id)
        .order_by(MachineLedger.id.desc())
    )
    if keyword.strip():
        kw = f"%{normalized_lower(keyword)}%"
        stmt = stmt.where(
            or_(
                func.lower(MachineLedger.name).like(kw),
                func.lower(MachineLedger.spec).like(kw),
                func.lower(MachineLedger.remark).like(kw),
            )
        )

    if page is None and page_size is None:
        rows = db.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "spec": row.spec,
                "use_date": row.use_date,
                "shift_count": dec_trimmed(row.shift_count),
                "remark": row.remark,
            }
            for row in rows
        ]

    page_value = max(1, int(page or 1))
    page_size_value = max(1, min(100, int(page_size or 10)))
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    rows = db.scalars(stmt.offset((page_value - 1) * page_size_value).limit(page_size_value)).all()
    items = [
        {
            "id": row.id,
            "name": row.name,
            "spec": row.spec,
            "use_date": row.use_date,
            "shift_count": dec_trimmed(row.shift_count),
            "remark": row.remark,
        }
        for row in rows
    ]
    total_pages = max(1, (total + page_size_value - 1) // page_size_value)
    return {
        "items": items,
        "total": total,
        "page": page_value,
        "page_size": page_size_value,
        "total_pages": total_pages,
    }


def machine_ledger_create(payload: dict, db: Session, project: Project) -> dict:
    name = payload_text(payload, "name")
    if not name:
        raise HTTPException(status_code=400, detail="机械名称不能为空")
    spec = payload_text(payload, "spec")
    use_date = payload_text(payload, "use_date")
    remark = payload_text(payload, "remark")
    shift_count = _parse_shift_count(payload.get("shift_count", "0"))

    row = MachineLedger(
        project_id=project.id,
        name=name,
        spec=spec,
        use_date=use_date,
        shift_count=shift_count,
        remark=remark,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


def machine_ledger_update(row_id: int, payload: dict, db: Session, project: Project) -> dict:
    row = db.get(MachineLedger, row_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="记录不存在")

    name = payload_text(payload, "name")
    if not name:
        raise HTTPException(status_code=400, detail="机械名称不能为空")
    row.name = name
    row.spec = payload_text(payload, "spec")
    row.use_date = payload_text(payload, "use_date")
    row.remark = payload_text(payload, "remark")
    row.shift_count = _parse_shift_count(payload.get("shift_count", "0"))

    db.commit()
    return {"ok": True}


def machine_ledger_delete(payload: dict, db: Session, project: Project) -> dict:
    raw_ids = payload.get("ids") or []
    ids = parse_positive_int_ids(raw_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")

    rows = db.scalars(
        select(MachineLedger).where(
            and_(
                MachineLedger.project_id == project.id,
                MachineLedger.id.in_(ids),
            )
        )
    ).all()

    target_ids = [row.id for row in rows]
    attachment_paths: list[str] = []
    if target_ids:
        attachments = db.scalars(
            select(Attachment).where(
                and_(
                    Attachment.order_type == "machine_ledger",
                    Attachment.order_id.in_(target_ids),
                    Attachment.is_deleted.is_(False),
                )
            )
        ).all()
        attachment_paths = [item.path for item in attachments if item.path]
        for item in attachments:
            item.is_deleted = True
            item.deleted_at = _utcnow_naive()

    deleted = 0
    for row in rows:
        db.delete(row)
        deleted += 1
    db.commit()

    for file_path in attachment_paths:
        safe_remove_uploaded_file(file_path)

    return {"ok": True, "deleted": deleted}


def _parse_shift_count(raw_value: object) -> Decimal:
    try:
        value = Decimal(str(raw_value or "0"))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="台班格式不正确") from exc
    if value < Decimal("0"):
        raise HTTPException(status_code=400, detail="台班不能小于0")
    return value
