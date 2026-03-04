import os
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Attachment,
    ConstructionLog,
    MachineLedger,
    Project,
    StockInOrder,
    StockOutOrder,
)

IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_CONTENT_TYPES = IMAGE_CONTENT_TYPES | {"application/pdf"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_CONSTRUCTION_LOG_PHOTOS = 30
MAX_IMAGE_EDGE = 1920
IMAGE_WEBP_QUALITY = 82


def safe_fs_name(value: str, fallback: str = "unnamed") -> str:
    text = (value or "").strip()
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def uploads_root() -> Path:
    root = Path(settings.uploads_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_subpath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def safe_remove_uploaded_file(file_path: str) -> bool:
    if not file_path:
        return False
    root = uploads_root()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    if not is_subpath(resolved, root):
        return False
    try:
        if resolved.exists():
            resolved.unlink()
            return True
    except OSError:
        return False
    return False


def attachment_disk_path_candidates(row: Attachment) -> list[Path]:
    root = uploads_root()
    candidates: list[Path] = []

    stored_name = (row.stored_name or "").strip()
    if stored_name:
        candidates.append(root / Path(stored_name))

    raw_path = (row.path or "").strip()
    if raw_path:
        path_obj = Path(raw_path)
        if not path_obj.is_absolute():
            path_obj = root / path_obj
        candidates.append(path_obj)

    unique: list[Path] = []
    seen: set[str] = set()
    for path_obj in candidates:
        key = str(path_obj)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path_obj)
    return unique


def resolve_attachment_disk_path(row: Attachment) -> Path | None:
    root = uploads_root()
    for candidate in attachment_disk_path_candidates(row):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if is_subpath(resolved, root):
            return resolved
    return None


def cleanup_deleted_attachments(db: Session, retention_days: int | None = None) -> dict:
    days = settings.deleted_attachment_retention_days if retention_days is None else retention_days
    days = max(0, int(days or 0))
    cutoff = utcnow_naive() - timedelta(days=days)
    rows = db.scalars(
        select(Attachment)
        .where(Attachment.is_deleted.is_(True), Attachment.created_at <= cutoff)
        .order_by(Attachment.id.asc())
    ).all()

    deleted_rows = 0
    deleted_files = 0
    for row in rows:
        storage_key = (row.stored_name or "").strip() or (row.path or "").strip()
        if not storage_key:
            db.delete(row)
            deleted_rows += 1
            continue

        active_ref_count = db.scalar(
            select(func.count(Attachment.id)).where(
                or_(
                    Attachment.stored_name == storage_key,
                    Attachment.path == storage_key,
                ),
                Attachment.id != row.id,
                Attachment.is_deleted.is_(False),
            )
        )
        if int(active_ref_count or 0) <= 0 and safe_remove_uploaded_file(storage_key):
            deleted_files += 1
        db.delete(row)
        deleted_rows += 1

    if deleted_rows:
        db.commit()
    return {"ok": True, "deleted_rows": deleted_rows, "deleted_files": deleted_files, "retention_days": days}


def attachment_bucket(order_type: str, content_type: str) -> str:
    is_image = (content_type or "").startswith("image/")
    if order_type == "construction_log":
        return "日志照片" if is_image else "日志附件"
    if order_type == "machine_ledger":
        return "机械照片" if is_image else "机械附件"
    if order_type == "stock_in":
        return "入库附件"
    if order_type == "stock_out":
        return "出库附件"
    return "其他附件"


def date8_from_text(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) >= 8:
        return digits[:8]
    return utcnow_naive().strftime("%Y%m%d")


def attachment_photo_day8(db: Session, order_type: str, order_id: int) -> str:
    if order_type == "construction_log":
        row = db.get(ConstructionLog, order_id)
        return date8_from_text((row.log_date if row else "") or "")
    if order_type == "machine_ledger":
        row = db.get(MachineLedger, order_id)
        return date8_from_text((row.use_date if row else "") or "")
    return utcnow_naive().strftime("%Y%m%d")


def photo_filename_by_rule(order_type: str, day8: str, seq: int, ext: str) -> str:
    prefix = "RZ" if order_type == "construction_log" else "JX"
    return f"{prefix}-{day8}-{seq:02d}{ext}"


def next_photo_seq(db: Session, project_name: str, order_type: str, day8: str) -> int:
    bucket = attachment_bucket(order_type, "image/webp")
    rel_prefix = f"{safe_fs_name(project_name)}/{bucket}/"
    file_prefix = "RZ" if order_type == "construction_log" else "JX"
    rows = db.scalars(
        select(Attachment).where(
            and_(
                Attachment.order_type == order_type,
                Attachment.is_deleted.is_(False),
                Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
                Attachment.stored_name.like(f"{rel_prefix}%"),
                Attachment.filename.like(f"{file_prefix}-{day8}-%"),
            )
        )
    ).all()
    max_seq = 0
    for row in rows:
        stem = Path(row.filename or "").stem
        parts = stem.split("-")
        if len(parts) < 3:
            continue
        try:
            max_seq = max(max_seq, int(parts[-1]))
        except ValueError:
            continue
    return max_seq + 1


def filename_from_content_type(filename: str, content_type: str) -> str:
    stem = Path(filename or "file").stem or "file"
    suffix = Path(filename or "").suffix
    if suffix:
        return f"{stem}{suffix}"
    if content_type == "image/webp":
        return f"{stem}.webp"
    if content_type == "image/jpeg":
        return f"{stem}.jpg"
    if content_type == "image/png":
        return f"{stem}.png"
    if content_type == "application/pdf":
        return f"{stem}.pdf"
    return f"{stem}.bin"


def alloc_attachment_target(
    db: Session,
    rel_dir: Path,
    filename: str,
    current_attachment_id: int | None = None,
    current_stored_name: str | None = None,
) -> tuple[str, Path]:
    root = uploads_root()
    rel_dir = Path(*[safe_fs_name(part, "x") for part in rel_dir.parts if part])
    rel_dir = rel_dir if rel_dir.parts else Path("其他附件")

    src_name = safe_fs_name(filename, "file")
    stem = Path(src_name).stem or "file"
    suffix = Path(src_name).suffix

    index = 1
    while True:
        candidate_name = f"{stem}{suffix}" if index == 1 else f"{stem}-{index:02d}{suffix}"
        rel_path = (rel_dir / candidate_name).as_posix()
        exists_in_db = db.scalar(
            select(Attachment.id).where(
                and_(
                    Attachment.stored_name == rel_path,
                    Attachment.id != (current_attachment_id or 0),
                )
            )
        )
        full_path = root / Path(rel_path)
        same_as_current = bool(current_stored_name and rel_path == current_stored_name)
        if not exists_in_db and (same_as_current or not full_path.exists()):
            full_path.parent.mkdir(parents=True, exist_ok=True)
            return rel_path, full_path
        index += 1


def target_project_id_for_attachment(db: Session, order_type: str, order_id: int) -> int:
    if order_type == "stock_in":
        row = db.get(StockInOrder, order_id)
    elif order_type == "stock_out":
        row = db.get(StockOutOrder, order_id)
    elif order_type == "construction_log":
        row = db.get(ConstructionLog, order_id)
    elif order_type == "machine_ledger":
        row = db.get(MachineLedger, order_id)
    else:
        raise HTTPException(status_code=400, detail="order_type 无效")

    if not row:
        raise HTTPException(status_code=404, detail="关联业务记录不存在")
    return int(row.project_id)


def compress_image_to_webp(content: bytes) -> tuple[bytes, str, str]:
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")

            width, height = image.size
            max_edge = max(width, height)
            if max_edge > MAX_IMAGE_EDGE:
                scale = MAX_IMAGE_EDGE / max_edge
                image = image.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                    Image.Resampling.LANCZOS,
                )

            output = BytesIO()
            image.save(output, format="WEBP", quality=IMAGE_WEBP_QUALITY, method=6)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="图片格式无法识别") from exc

    return output.getvalue(), ".webp", "image/webp"


def normalize_machine_photo_filenames(db: Session) -> None:
    rows = db.scalars(
        select(Attachment)
        .where(
            and_(
                Attachment.order_type == "machine_ledger",
                Attachment.is_deleted.is_(False),
                Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
            )
        )
        .order_by(Attachment.order_id.asc(), Attachment.created_at.asc(), Attachment.id.asc())
    ).all()

    grouped: dict[int, list[Attachment]] = {}
    for row in rows:
        grouped.setdefault(int(row.order_id), []).append(row)

    changed = False
    for order_id, items in grouped.items():
        ledger = db.get(MachineLedger, order_id)
        base_date = (ledger.use_date or "").strip() if ledger else ""
        day8 = date8_from_text(base_date)

        for index, item in enumerate(items, start=1):
            suffix = Path(item.filename or "").suffix.lower()
            if not suffix:
                suffix = ".webp" if item.content_type == "image/webp" else ".jpg"
            expected = f"JX-{day8}-{index:02d}{suffix}"
            if item.filename != expected:
                item.filename = expected
                changed = True

    if changed:
        db.commit()


def normalize_attachment_storage(db: Session) -> None:
    rows = db.scalars(
        select(Attachment)
        .where(Attachment.is_deleted.is_(False))
        .order_by(Attachment.created_at.asc(), Attachment.id.asc())
    ).all()
    if not rows:
        return

    root = uploads_root()
    changed = False
    photo_daily_seq: dict[tuple[int, str, str], int] = {}
    for row in rows:
        try:
            project_id = target_project_id_for_attachment(db, row.order_type, row.order_id)
            project = db.get(Project, project_id)
        except HTTPException:
            continue

        project_name = safe_fs_name(project.name if project else f"工程{project_id}", f"工程{project_id}")
        bucket = attachment_bucket(row.order_type, row.content_type)
        rel_dir = Path(project_name) / bucket

        is_photo = row.content_type in IMAGE_CONTENT_TYPES and row.order_type in {"construction_log", "machine_ledger"}
        if is_photo:
            day8 = attachment_photo_day8(db, row.order_type, row.order_id)
            seq_key = (project_id, row.order_type, day8)
            next_seq = photo_daily_seq.get(seq_key, 1)
            ext = Path(row.filename or "").suffix.lower() or (".webp" if row.content_type == "image/webp" else ".jpg")
            desired_filename = photo_filename_by_rule(row.order_type, day8, next_seq, ext)
            photo_daily_seq[seq_key] = next_seq + 1
        else:
            desired_filename = safe_fs_name(filename_from_content_type(row.filename or "file", row.content_type), "file")

        rel_stored, full_target = alloc_attachment_target(
            db,
            rel_dir,
            desired_filename,
            current_attachment_id=row.id,
            current_stored_name=row.stored_name,
        )

        old_path = resolve_attachment_disk_path(row)
        if old_path and old_path.exists() and old_path.resolve() != full_target.resolve():
            full_target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(str(old_path), str(full_target))
            except OSError:
                try:
                    with open(old_path, "rb") as src, open(full_target, "wb") as dst:
                        dst.write(src.read())
                    old_path.unlink()
                except Exception:
                    continue

        row.filename = Path(rel_stored).name
        row.stored_name = rel_stored
        row.path = str(root / Path(rel_stored))
        changed = True

    if changed:
        db.commit()
