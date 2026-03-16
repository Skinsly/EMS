from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import require_admin as _require_admin, require_project as _require_project, require_user as _require_user
from .models import Attachment, ConstructionLog, MachineLedger, Project, User
from .services.attachments import (
    ALLOWED_CONTENT_TYPES,
    IMAGE_CONTENT_TYPES,
    MAX_CONSTRUCTION_LOG_PHOTOS,
    MAX_UPLOAD_SIZE,
    alloc_attachment_target as _alloc_attachment_target,
    attachment_bucket as _attachment_bucket,
    attachment_photo_day8 as _attachment_photo_day8,
    cleanup_deleted_attachments as cleanup_deleted_attachments_service,
    compress_image_to_webp as _compress_image_to_webp,
    filename_from_content_type as _filename_from_content_type,
    next_photo_seq as _next_photo_seq,
    photo_filename_by_rule as _photo_filename_by_rule,
    resolve_attachment_disk_path as _resolve_attachment_disk_path,
    safe_fs_name as _safe_fs_name,
    target_project_id_for_attachment as _target_project_id_for_attachment,
)

router = APIRouter(prefix="/api")


@router.post("/attachments/upload")
async def upload_attachment(
    order_type: str,
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    target_project_id = _target_project_id_for_attachment(db, order_type, order_id)
    if target_project_id != project.id:
        raise HTTPException(status_code=403, detail="无权访问该工程附件")

    content_type = file.content_type or "application/octet-stream"
    is_image_upload = content_type.startswith("image/")
    if not is_image_upload and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="仅支持图片和PDF")

    content = bytearray()
    total_size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="文件超过10MB")
        content.extend(chunk)
    if total_size <= 0:
        raise HTTPException(status_code=400, detail="文件内容为空")
    content = bytes(content)

    if order_type == "construction_log" and is_image_upload:
        current_count = db.scalar(
            select(func.count(Attachment.id)).where(
                Attachment.order_type == "construction_log",
                Attachment.order_id == order_id,
                Attachment.is_deleted.is_(False),
                Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
            )
        )
        if int(current_count or 0) >= MAX_CONSTRUCTION_LOG_PHOTOS:
            raise HTTPException(status_code=400, detail=f"单条施工日志最多上传 {MAX_CONSTRUCTION_LOG_PHOTOS} 张照片")

    display_name = file.filename or "file"
    if is_image_upload:
        content, ext, content_type = _compress_image_to_webp(content)
        day8 = _attachment_photo_day8(db, order_type, order_id)
        if order_type in {"construction_log", "machine_ledger"}:
            target_project = db.get(Project, target_project_id)
            project_name = _safe_fs_name(target_project.name if target_project else f"工程{target_project_id}", f"工程{target_project_id}")
            seq = _next_photo_seq(db, project_name, order_type, day8)
            display_name = _photo_filename_by_rule(order_type, day8, seq, ext)
        else:
            stem = Path(display_name).stem or "photo"
            display_name = f"{stem}.webp"

    target_project = db.get(Project, target_project_id)
    project_name = _safe_fs_name(target_project.name if target_project else f"工程{target_project_id}", f"工程{target_project_id}")
    bucket = _attachment_bucket(order_type, content_type)
    desired_name = _safe_fs_name(_filename_from_content_type(display_name, content_type), "file")
    stored_name, full_path = _alloc_attachment_target(db, Path(project_name) / bucket, desired_name)

    with open(full_path, "wb") as f:
        f.write(content)

    row = Attachment(
        order_type=order_type,
        order_id=order_id,
        filename=display_name,
        stored_name=stored_name,
        content_type=content_type,
        size=len(content),
        path=str(full_path),
        uploaded_by=current_user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "filename": row.filename}


@router.get("/attachments")
def list_attachments(
    order_type: str,
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    if _target_project_id_for_attachment(db, order_type, order_id) != project.id:
        raise HTTPException(status_code=403, detail="无权访问该工程附件")
    rows = db.scalars(
        select(Attachment)
        .where(Attachment.order_type == order_type, Attachment.order_id == order_id, Attachment.is_deleted.is_(False))
        .order_by(Attachment.id.desc())
    ).all()
    return [
        {
            "id": row.id,
            "filename": row.filename,
            "content_type": row.content_type,
            "size": row.size,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    inline: bool = False,
) -> FileResponse:
    row = db.get(Attachment, attachment_id)
    if not row or row.is_deleted:
        raise HTTPException(status_code=404, detail="附件不存在")
    if _target_project_id_for_attachment(db, row.order_type, row.order_id) != project.id:
        raise HTTPException(status_code=403, detail="无权访问该工程附件")
    resolved_path = _resolve_attachment_disk_path(row)
    if not resolved_path or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    response = FileResponse(path=str(resolved_path), filename=row.filename, media_type=row.content_type)
    encoded = quote(row.filename or "file")
    disposition = "inline" if inline else "attachment"
    response.headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded}"
    return response


@router.get("/attachments/{attachment_id}/download")
def download_attachment_route(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> FileResponse:
    return download_attachment(attachment_id, db, _, project, inline=False)


@router.get("/attachments/{attachment_id}/preview")
def preview_attachment_route(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> FileResponse:
    return download_attachment(attachment_id, db, _, project, inline=True)


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    row = db.get(Attachment, attachment_id)
    if not row or row.is_deleted:
        raise HTTPException(status_code=404, detail="附件不存在")
    if _target_project_id_for_attachment(db, row.order_type, row.order_id) != project.id:
        raise HTTPException(status_code=403, detail="无权访问该工程附件")
    row.is_deleted = True
    row.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


@router.post("/admin/attachments/cleanup")
def cleanup_deleted_attachments(
    retention_days: int = Query(default=0, ge=0, le=3650),
    db: Session = Depends(get_db),
    _: User = Depends(_require_admin),
) -> dict:
    return cleanup_deleted_attachments_service(db, retention_days=retention_days)


@router.get("/site-photos")
def list_site_photos(
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    log_rows = db.execute(
        select(Attachment, ConstructionLog)
        .join(ConstructionLog, and_(Attachment.order_type == "construction_log", Attachment.order_id == ConstructionLog.id))
        .where(
            Attachment.is_deleted.is_(False),
            Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
            ConstructionLog.project_id == project.id,
        )
        .order_by(ConstructionLog.log_date.desc(), Attachment.id.desc())
    ).all()
    machine_rows = db.execute(
        select(Attachment, MachineLedger)
        .join(MachineLedger, and_(Attachment.order_type == "machine_ledger", Attachment.order_id == MachineLedger.id))
        .where(
            Attachment.is_deleted.is_(False),
            Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
            MachineLedger.project_id == project.id,
        )
        .order_by(MachineLedger.use_date.desc(), Attachment.id.desc())
    ).all()

    result = [
        {
            "id": attachment.id,
            "log_id": log.id,
            "source_type": "log",
            "log_date": log.log_date or "未填写日期",
            "filename": attachment.filename,
            "content_type": attachment.content_type,
            "size": attachment.size,
            "created_at": attachment.created_at.isoformat(),
        }
        for attachment, log in log_rows
    ]
    result.extend(
        [
            {
                "id": attachment.id,
                "log_id": row.id,
                "source_type": "machine",
                "log_date": row.use_date or "未填写日期",
                "filename": attachment.filename,
                "content_type": attachment.content_type,
                "size": attachment.size,
                "created_at": attachment.created_at.isoformat(),
            }
            for attachment, row in machine_rows
        ]
    )
    result.sort(key=lambda item: (item.get("log_date", ""), item.get("id", 0)), reverse=True)
    return result
