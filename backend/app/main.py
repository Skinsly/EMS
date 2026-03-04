import html
import io
import json
import os
import re
import sqlite3
import tempfile
import time
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, case, delete, func, literal, or_, select, text, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .bootstrap import create_initial_admin, is_initialized
from .database import Base, engine, get_db
from .dependencies import (
    is_admin_user as _is_admin_user,
    require_admin as _require_admin,
    require_project as _require_project,
    require_user as _require_user,
    security,
)
from .idempotency import cleanup_expired_idempotency, read_idempotency, write_idempotency
from .models import (
    Attachment,
    ConstructionLog,
    Inventory,
    Material,
    MachineLedger,
    Project,
    ProgressPlanItem,
    StockInItem,
    StockInOrder,
    StockMovement,
    StockDraft,
    StockOutItem,
    StockOutOrder,
    User,
    Warehouse,
)
from .schemas import (
    BootstrapInitRequest,
    ConstructionLogCreate,
    ConstructionLogUpdate,
    InventoryDeleteRequest,
    LoginRequest,
    MaterialCreate,
    MaterialDeleteRequest,
    MaterialUpdate,
    PasswordChangeRequest,
    ProjectCreate,
    ProjectDeleteRequest,
    ProgressPlanItemCreate,
    ProgressPlanItemUpdate,
    StockOrderItemInput,
    StockInCreate,
    StockOutCreate,
    TokenResponse,
)
from .security import create_access_token, decode_access_token, get_password_hash, verify_password

@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_dirs()
    Base.metadata.create_all(bind=engine)
    _ensure_schema_updates()
    with Session(engine) as db:
        _seed_data(db)
        cleanup_expired_idempotency(db)
        _normalize_machine_photo_filenames(db)
        _normalize_attachment_storage(db)
        _cleanup_deleted_attachments(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


def _cors_origins() -> list[str]:
    values = [v.strip() for v in settings.cors_origins.split(",") if v.strip()]
    return values or ["http://localhost:5173", "http://127.0.0.1:5173"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _ensure_dirs() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)


def _resolve_db_path() -> Path:
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = Path(settings.data_dir) / db_path
    return db_path


def _safe_unlink(path: Path) -> None:
    for _ in range(6):
        try:
            if path.exists():
                path.unlink()
            return
        except PermissionError:
            time.sleep(0.12)
        except FileNotFoundError:
            return


def _safe_fs_name(value: str, fallback: str = "unnamed") -> str:
    text = (value or "").strip()
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uploads_root() -> Path:
    root = Path(settings.uploads_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_subpath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _safe_remove_uploaded_file(file_path: str) -> bool:
    if not file_path:
        return False
    uploads_root = _uploads_root()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = uploads_root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    if not _is_subpath(resolved, uploads_root):
        return False
    try:
        if resolved.exists():
            resolved.unlink()
            return True
    except OSError:
        return False
    return False


def _attachment_disk_path_candidates(row: Attachment) -> list[Path]:
    uploads_root = _uploads_root()
    candidates: list[Path] = []

    stored_name = (row.stored_name or "").strip()
    if stored_name:
        candidates.append(uploads_root / Path(stored_name))

    raw_path = (row.path or "").strip()
    if raw_path:
        path_obj = Path(raw_path)
        if not path_obj.is_absolute():
            path_obj = uploads_root / path_obj
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


def _resolve_attachment_disk_path(row: Attachment) -> Path | None:
    uploads_root = _uploads_root()
    for candidate in _attachment_disk_path_candidates(row):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if _is_subpath(resolved, uploads_root):
            return resolved
    return None


def _cleanup_deleted_attachments(db: Session, retention_days: int | None = None) -> dict:
    days = settings.deleted_attachment_retention_days if retention_days is None else retention_days
    days = max(0, int(days or 0))
    cutoff = _utcnow_naive() - timedelta(days=days)
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
        if int(active_ref_count or 0) <= 0 and _safe_remove_uploaded_file(storage_key):
            deleted_files += 1
        db.delete(row)
        deleted_rows += 1

    if deleted_rows:
        db.commit()
    return {"ok": True, "deleted_rows": deleted_rows, "deleted_files": deleted_files, "retention_days": days}


def _attachment_bucket(order_type: str, content_type: str) -> str:
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


def _date8_from_text(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) >= 8:
        return digits[:8]
    return _utcnow_naive().strftime("%Y%m%d")


def _attachment_photo_day8(db: Session, order_type: str, order_id: int) -> str:
    if order_type == "construction_log":
        row = db.get(ConstructionLog, order_id)
        return _date8_from_text((row.log_date if row else "") or "")
    if order_type == "machine_ledger":
        row = db.get(MachineLedger, order_id)
        return _date8_from_text((row.use_date if row else "") or "")
    return _utcnow_naive().strftime("%Y%m%d")


def _photo_filename_by_rule(order_type: str, day8: str, seq: int, ext: str) -> str:
    prefix = "RZ" if order_type == "construction_log" else "JX"
    return f"{prefix}-{day8}-{seq:02d}{ext}"


def _next_photo_seq(db: Session, project_name: str, order_type: str, day8: str) -> int:
    bucket = _attachment_bucket(order_type, "image/webp")
    rel_prefix = f"{_safe_fs_name(project_name)}/{bucket}/"
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


def _filename_from_content_type(filename: str, content_type: str) -> str:
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


def _alloc_attachment_target(
    db: Session,
    rel_dir: Path,
    filename: str,
    current_attachment_id: int | None = None,
    current_stored_name: str | None = None,
) -> tuple[str, Path]:
    uploads_root = _uploads_root()
    rel_dir = Path(*[_safe_fs_name(part, "x") for part in rel_dir.parts if part])
    rel_dir = rel_dir if rel_dir.parts else Path("其他附件")

    src_name = _safe_fs_name(filename, "file")
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
        full_path = uploads_root / Path(rel_path)
        same_as_current = bool(current_stored_name and rel_path == current_stored_name)
        if not exists_in_db and (same_as_current or not full_path.exists()):
            full_path.parent.mkdir(parents=True, exist_ok=True)
            return rel_path, full_path
        index += 1


def _validate_import_sqlite(db_file: Path) -> None:
    try:
        with sqlite3.connect(str(db_file)) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = {str(row[0]) for row in rows}
            required = {"users", "projects", "materials"}
            if not required.issubset(table_names):
                raise HTTPException(status_code=400, detail="数据包结构不匹配")
            user_count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0)
            if user_count <= 0:
                raise HTTPException(status_code=400, detail="导入包无有效账号数据")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="数据包不是有效的 SQLite 数据库") from exc


def _seed_data(db: Session) -> None:
    warehouse = db.scalar(select(Warehouse).where(Warehouse.name == "主仓库"))
    if not warehouse:
        db.add(Warehouse(name="主仓库"))

    db.commit()


def _ensure_schema_updates() -> None:
    with engine.begin() as conn:
        def has_column(table: str, column: str) -> bool:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
            return any(r["name"] == column for r in rows)

        if not has_column("materials", "project_id"):
            conn.execute(text("ALTER TABLE materials ADD COLUMN project_id INTEGER DEFAULT 0"))
        if not has_column("stock_in_orders", "project_id"):
            conn.execute(text("ALTER TABLE stock_in_orders ADD COLUMN project_id INTEGER DEFAULT 0"))
        if not has_column("stock_out_orders", "project_id"):
            conn.execute(text("ALTER TABLE stock_out_orders ADD COLUMN project_id INTEGER DEFAULT 0"))
        if not has_column("stock_movements", "project_id"):
            conn.execute(text("ALTER TABLE stock_movements ADD COLUMN project_id INTEGER DEFAULT 0"))
        if not has_column("construction_logs", "created_by"):
            conn.execute(text("ALTER TABLE construction_logs ADD COLUMN created_by TEXT NOT NULL DEFAULT ''"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS machine_ledger (
                  id INTEGER PRIMARY KEY,
                  project_id INTEGER NOT NULL,
                  name VARCHAR(200) NOT NULL,
                  spec VARCHAR(200) NOT NULL DEFAULT '',
                  use_date VARCHAR(20) NOT NULL DEFAULT '',
                  shift_count NUMERIC(12,3) NOT NULL DEFAULT 0,
                  remark VARCHAR(255) NOT NULL DEFAULT '',
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        if not has_column("machine_ledger", "spec"):
            conn.execute(text("ALTER TABLE machine_ledger ADD COLUMN spec VARCHAR(200) NOT NULL DEFAULT ''"))
        if not has_column("machine_ledger", "use_date"):
            conn.execute(text("ALTER TABLE machine_ledger ADD COLUMN use_date VARCHAR(20) NOT NULL DEFAULT ''"))
        if not has_column("machine_ledger", "shift_count"):
            conn.execute(text("ALTER TABLE machine_ledger ADD COLUMN shift_count NUMERIC(12,3) NOT NULL DEFAULT 0"))
        if not has_column("machine_ledger", "remark"):
            conn.execute(text("ALTER TABLE machine_ledger ADD COLUMN remark VARCHAR(255) NOT NULL DEFAULT ''"))
        if not has_column("machine_ledger", "created_at"):
            conn.execute(text("ALTER TABLE machine_ledger ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"))


def _validate_password_strength(password: str) -> bool:
    return bool(PASSWORD_RULE.match(password))


DELETE_PROJECT_ACK_PHRASE = "我已知晓删除后不可恢复"


def _order_no(prefix: str, db: Session, order_model) -> str:
    date_part = datetime.now().strftime('%Y%m%d')
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


def _dec(v: Decimal) -> str:
    return f"{v:.3f}"


def _qty_text(v: Decimal) -> str:
    text = format(v, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _inventory_row(db: Session, material_id: int, warehouse_id: int) -> Inventory:
    row = db.scalar(
        select(Inventory).where(Inventory.material_id == material_id, Inventory.warehouse_id == warehouse_id)
    )
    if row:
        return row
    db.execute(
        text(
            "INSERT OR IGNORE INTO inventory (material_id, warehouse_id, qty, updated_at) "
            "VALUES (:material_id, :warehouse_id, :qty, CURRENT_TIMESTAMP)"
        ),
        {"material_id": material_id, "warehouse_id": warehouse_id, "qty": "0.000"},
    )
    row = db.scalar(
        select(Inventory).where(Inventory.material_id == material_id, Inventory.warehouse_id == warehouse_id)
    )
    if row:
        return row
    raise HTTPException(status_code=500, detail="初始化库存记录失败")


def _default_warehouse(db: Session) -> Warehouse:
    row = db.scalar(select(Warehouse).where(Warehouse.name == "主仓库"))
    if row:
        return row
    row = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()))
    if row:
        return row
    row = Warehouse(name="主仓库")
    db.add(row)
    db.flush()
    return row


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.scalar(select(func.count()).select_from(User)) == 0:
        raise HTTPException(status_code=403, detail="系统未初始化，请先创建管理员账号")
    user = db.scalar(select(User).where(User.username == payload.username, User.is_active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return TokenResponse(access_token=token, must_change_password=user.must_change_password)


@app.get("/api/bootstrap/status")
def bootstrap_status(db: Session = Depends(get_db)) -> dict:
    return {"initialized": is_initialized(db)}


@app.post("/api/bootstrap/init", response_model=TokenResponse)
def bootstrap_init(payload: BootstrapInitRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if is_initialized(db):
        raise HTTPException(status_code=400, detail="系统已初始化")

    username = payload.username.strip()
    password = payload.password.strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="账号至少 3 位")
    if not _validate_password_strength(password):
        raise HTTPException(status_code=400, detail="密码需至少8位且包含字母和数字")

    return create_initial_admin(db, payload)


@app.post("/api/auth/change-password")
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
) -> dict:
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")

    new_username = payload.new_username.strip()
    new_password = payload.new_password.strip()
    if not new_username and not new_password:
        raise HTTPException(status_code=400, detail="请至少填写新账号或新密码")

    username_changed = False
    if new_username:
        if len(new_username) < 3:
            raise HTTPException(status_code=400, detail="新账号至少 3 位")
        exists = db.scalar(select(User).where(User.username == new_username, User.id != current_user.id))
        if exists:
            raise HTTPException(status_code=400, detail="账号已存在")
        if new_username != current_user.username:
            current_user.username = new_username
            username_changed = True

    if new_password:
        if not _validate_password_strength(new_password):
            raise HTTPException(status_code=400, detail="密码需至少8位且包含字母和数字")
        current_user.password_hash = get_password_hash(new_password)

    current_user.must_change_password = False
    db.commit()
    return {"ok": True, "username_changed": username_changed, "username": current_user.username}


@app.post("/api/projects")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), _: User = Depends(_require_user)) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="工程名称不能为空")
    exists = db.scalar(select(Project).where(Project.name == name))
    if exists and exists.is_active:
        raise HTTPException(status_code=400, detail="工程名称已存在")
    if exists and not exists.is_active:
        exists.is_active = True
        exists.start_date = payload.start_date.strip()
        db.commit()
        db.refresh(exists)
        return {"id": exists.id}

    row = Project(name=name, start_date=payload.start_date.strip(), location="")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db), _: User = Depends(_require_user)) -> list[dict]:
    rows = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.id.desc())).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "start_date": p.start_date,
            "location": p.location,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


@app.delete("/api/projects/{project_id}")
def delete_project(
    project_id: int,
    payload: ProjectDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
) -> dict:
    project = db.get(Project, project_id)
    if not project or not project.is_active:
        raise HTTPException(status_code=404, detail="工程不存在")
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="登录密码错误")
    if payload.confirm_text.strip() != DELETE_PROJECT_ACK_PHRASE:
        raise HTTPException(status_code=400, detail=f"确认短语不正确，请输入：{DELETE_PROJECT_ACK_PHRASE}")

    stock_in_ids = db.scalars(select(StockInOrder.id).where(StockInOrder.project_id == project.id)).all()
    stock_out_ids = db.scalars(select(StockOutOrder.id).where(StockOutOrder.project_id == project.id)).all()
    log_ids = db.scalars(select(ConstructionLog.id).where(ConstructionLog.project_id == project.id)).all()
    machine_ledger_ids = db.scalars(select(MachineLedger.id).where(MachineLedger.project_id == project.id)).all()
    material_ids = db.scalars(select(Material.id).where(Material.project_id == project.id)).all()

    attachment_paths: list[str] = []

    if log_ids:
        log_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "construction_log", Attachment.order_id.in_(log_ids))
        ).all()
        attachment_paths.extend([row.path for row in log_attachments if row.path])
        db.execute(
            delete(Attachment).where(Attachment.order_type == "construction_log", Attachment.order_id.in_(log_ids))
        )

    if stock_in_ids:
        stock_in_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "stock_in", Attachment.order_id.in_(stock_in_ids))
        ).all()
        attachment_paths.extend([row.path for row in stock_in_attachments if row.path])
        db.execute(delete(Attachment).where(Attachment.order_type == "stock_in", Attachment.order_id.in_(stock_in_ids)))
        db.execute(delete(StockInItem).where(StockInItem.order_id.in_(stock_in_ids)))

    if stock_out_ids:
        stock_out_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "stock_out", Attachment.order_id.in_(stock_out_ids))
        ).all()
        attachment_paths.extend([row.path for row in stock_out_attachments if row.path])
        db.execute(delete(Attachment).where(Attachment.order_type == "stock_out", Attachment.order_id.in_(stock_out_ids)))
        db.execute(delete(StockOutItem).where(StockOutItem.order_id.in_(stock_out_ids)))

    if machine_ledger_ids:
        machine_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "machine_ledger", Attachment.order_id.in_(machine_ledger_ids))
        ).all()
        attachment_paths.extend([row.path for row in machine_attachments if row.path])
        db.execute(
            delete(Attachment).where(
                Attachment.order_type == "machine_ledger",
                Attachment.order_id.in_(machine_ledger_ids),
            )
        )

    db.execute(delete(StockMovement).where(StockMovement.project_id == project.id))
    db.execute(delete(StockInOrder).where(StockInOrder.project_id == project.id))
    db.execute(delete(StockOutOrder).where(StockOutOrder.project_id == project.id))
    db.execute(delete(ProgressPlanItem).where(ProgressPlanItem.project_id == project.id))
    db.execute(delete(ConstructionLog).where(ConstructionLog.project_id == project.id))
    db.execute(delete(MachineLedger).where(MachineLedger.project_id == project.id))

    if material_ids:
        db.execute(delete(Inventory).where(Inventory.material_id.in_(material_ids)))

    db.execute(delete(Material).where(Material.project_id == project.id))

    project.is_active = False
    db.commit()

    for file_path in set(attachment_paths):
        _safe_remove_uploaded_file(file_path)

    return {"ok": True}


@app.post("/api/construction-logs")
def create_construction_log(
    payload: ConstructionLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
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


@app.get("/api/construction-logs")
def list_construction_logs(
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    rows = db.scalars(
        select(ConstructionLog).where(ConstructionLog.project_id == project.id).order_by(ConstructionLog.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "log_date": r.log_date,
            "title": r.title,
            "weather": r.weather,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.put("/api/construction-logs/{log_id}")
def update_construction_log(
    log_id: int,
    payload: ConstructionLogUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
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


@app.delete("/api/construction-logs/{log_id}")
def delete_construction_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
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

    db.delete(row)
    db.commit()

    for file_path in attachment_paths:
        _safe_remove_uploaded_file(file_path)

    return {"ok": True}


@app.post("/api/progress-plans")
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


@app.get("/api/progress-plans")
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
            "id": r.id,
            "task_name": r.task_name,
            "owner": r.owner,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "progress": r.progress,
            "status": r.status,
            "predecessor": r.predecessor,
            "note": r.note,
            "sort_order": r.sort_order,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.put("/api/progress-plans/{item_id}")
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


@app.delete("/api/progress-plans/{item_id}")
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


@app.post("/api/materials")
def create_material(
    payload: MaterialCreate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
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


@app.get("/api/materials")
def list_materials(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    stmt = select(Material).where(Material.project_id == project.id, Material.is_active.is_(True)).order_by(Material.id.desc())
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where((Material.name.like(kw)) | (Material.spec.like(kw)))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "spec": m.spec,
            "unit": m.unit,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]


@app.put("/api/materials/{material_id}")
def update_material(
    material_id: int,
    payload: MaterialUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
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


@app.post("/api/materials/delete")
def delete_materials(
    payload: MaterialDeleteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    ids: list[int] = []
    for value in payload.material_ids:
        try:
            n = int(value)
        except Exception:
            continue
        if n > 0:
            ids.append(n)
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


@app.post("/api/stock-in")
def create_stock_in(
    payload: StockInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    x_idempotency_key: str | None = Header(default=None),
) -> dict:
    cache_key = ""
    key_part = (x_idempotency_key or "").strip()
    if key_part:
        cache_key = f"in:{project.id}:{current_user.id}:{key_part}"
        cached = read_idempotency(db, cache_key)
        if cached:
            return cached

    warehouse = db.get(Warehouse, payload.warehouse_id) if payload.warehouse_id else _default_warehouse(db)
    if not warehouse:
        warehouse = _default_warehouse(db)
    if not payload.items:
        raise HTTPException(status_code=400, detail="入库明细不能为空")

    order = None
    for _ in range(3):
        try:
            order = StockInOrder(
                project_id=project.id,
                order_no=_order_no("IN", db, StockInOrder),
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

        inv = _inventory_row(db, item.material_id, warehouse.id)
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


@app.post("/api/stock-out")
def create_stock_out(
    payload: StockOutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    x_idempotency_key: str | None = Header(default=None),
) -> dict:
    cache_key = ""
    key_part = (x_idempotency_key or "").strip()
    if key_part:
        cache_key = f"out:{project.id}:{current_user.id}:{key_part}"
        cached = read_idempotency(db, cache_key)
        if cached:
            return cached

    warehouse = db.get(Warehouse, payload.warehouse_id) if payload.warehouse_id else _default_warehouse(db)
    if not warehouse:
        warehouse = _default_warehouse(db)
    if not payload.items:
        raise HTTPException(status_code=400, detail="出库明细不能为空")

    order = None
    for _ in range(3):
        try:
            order = StockOutOrder(
                project_id=project.id,
                order_no=_order_no("OUT", db, StockOutOrder),
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

            inv = _inventory_row(db, item.material_id, warehouse.id)
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


def _stock_draft_type_or_400(draft_type: str) -> str:
    normalized = (draft_type or "").strip().lower()
    if normalized not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="草稿类型无效")
    return normalized


def _load_stock_draft(db: Session, project_id: int, user_id: int, draft_type: str) -> StockDraft | None:
    return db.scalar(
        select(StockDraft).where(
            and_(
                StockDraft.project_id == project_id,
                StockDraft.user_id == user_id,
                StockDraft.draft_type == draft_type,
            )
        )
    )


@app.get("/api/stock-drafts/{draft_type}")
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


@app.put("/api/stock-drafts/{draft_type}")
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
        row = StockDraft(
            project_id=project.id,
            user_id=current_user.id,
            draft_type=kind,
            payload_json=data,
        )
        db.add(row)
    else:
        row.payload_json = data
    db.commit()
    db.refresh(row)
    return {"ok": True, "updated_at": row.updated_at.isoformat() if row.updated_at else ""}


@app.get("/api/stock-drafts/pending/count")
def stock_draft_pending_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    rows = db.scalars(
        select(StockDraft).where(
            and_(
                StockDraft.project_id == project.id,
                StockDraft.user_id == current_user.id,
            )
        )
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


@app.post("/api/stock-drafts/{draft_type}/commit")
def commit_stock_draft(
    draft_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    kind = _stock_draft_type_or_400(draft_type)
    row = _load_stock_draft(db, project.id, current_user.id, kind)
    if not row:
        raise HTTPException(status_code=400, detail="暂无待入账草稿")
    try:
        items_raw = json.loads(row.payload_json or "[]")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="草稿数据损坏，请重新录入") from e
    if not isinstance(items_raw, list) or not items_raw:
        raise HTTPException(status_code=400, detail="暂无待入账草稿")

    normalized_items = []
    for item in items_raw:
        try:
            material_id = int(item.get("material_id", 0))
            qty = Decimal(str(item.get("qty", "0")))
        except Exception:
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


@app.get("/api/stock-records")
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
        .where(
            StockInOrder.project_id == project.id,
            StockInOrder.status == "normal",
        )
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
        .where(
            StockOutOrder.project_id == project.id,
            StockOutOrder.status == "normal",
        )
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
        items.append(
            {
                "type": row.get("type") or "",
                "order_no": row.get("raw_order_no") or "",
                "raw_order_no": row.get("raw_order_no") or "",
                "created_at": created_iso,
                "operator_name": row.get("operator_name") or "",
                "note": row.get("note") or "",
                "remark": row.get("remark") or "",
                "materials_summary": "、".join([x for x in (row.get("materials_summary") or "").split(",") if x][:3]) + ("..." if len([x for x in (row.get("materials_summary") or "").split(",") if x]) > 3 else ""),
                "specs_summary": "、".join([x for x in (row.get("specs_summary") or "").split(",") if x][:3]) + ("..." if len([x for x in (row.get("specs_summary") or "").split(",") if x]) > 3 else ""),
                "unit": row.get("unit") or "",
                "item_count": int(row.get("item_count") or 0),
                "total_qty": _dec(Decimal(str(row.get("total_qty") or "0"))),
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/api/stock-records/correct")
def correct_stock_record(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    kind = (payload.get("record_type") or "").strip().lower()
    order_no = f"{payload.get('order_no', '')}".strip()
    reason = f"{payload.get('reason', '')}".strip()
    if kind not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="记录类型无效")
    if not order_no:
        raise HTTPException(status_code=400, detail="单号不能为空")
    if not reason:
        raise HTTPException(status_code=400, detail="请填写更正原因")

    if kind == "in":
        origin = db.scalar(
            select(StockInOrder).where(
                and_(
                    StockInOrder.project_id == project.id,
                    StockInOrder.order_no == order_no,
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
                StockOutOrder.order_no == order_no,
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


@app.get("/api/export/stock-records")
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

    data = list_stock_records(
        record_type=kind,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        page=1,
        page_size=10000,
        db=db,
        _=current_user,
        project=project,
    )
    rows = data.get("items", [])

    stream = io.StringIO()
    stream.write('<html><head><meta charset="utf-8"></head><body>')
    title = "入库记录" if kind == "in" else "出库记录"
    stream.write('<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;width:100%;">')
    stream.write(f'<tr><th colspan="5" style="text-align:center;font-size:16px;">{html.escape(title)}</th></tr>')
    stream.write('<tr>')
    for col_title in ["序号", "日期", "名称", "数量", "单位"]:
        stream.write(f'<th style="text-align:center;padding:4px 2ch;white-space:nowrap;">{html.escape(col_title)}</th>')
    stream.write('</tr>')

    for idx, row in enumerate(rows, start=1):
        qty_text = _qty_text(Decimal(str(row.get("total_qty") or "0")))
        row_values = [
            idx,
            (row.get("created_at") or "").replace("T", " ")[:10],
            row.get("materials_summary") or "",
            qty_text,
            row.get("unit") or "",
        ]
        stream.write('<tr>')
        for value in row_values:
            text = html.escape(f"{value or ''}")
            stream.write(f'<td style="text-align:center;padding:4px 2ch;white-space:nowrap;">{text}</td>')
        stream.write('</tr>')

    stream.write('</table></body></html>')
    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.ms-excel; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=stock-records.xls"
    return response


@app.get("/api/stock-records/{record_type}/{order_no}")
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
        order = db.scalar(
            select(StockInOrder).where(
                and_(
                    StockInOrder.project_id == project.id,
                    StockInOrder.order_no == order_no,
                )
            )
        )
        if not order:
            raise HTTPException(status_code=404, detail="记录不存在")
        items = db.scalars(select(StockInItem).where(StockInItem.order_id == order.id)).all()
    else:
        order = db.scalar(
            select(StockOutOrder).where(
                and_(
                    StockOutOrder.project_id == project.id,
                    StockOutOrder.order_no == order_no,
                )
            )
        )
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
                "qty": _dec(Decimal(item.qty)),
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


@app.get("/api/inventory")
def inventory_list(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    rows = db.scalars(
        select(Inventory)
        .join(Material, Inventory.material_id == Material.id)
        .where(Material.project_id == project.id, Material.is_active.is_(True))
        .order_by(Inventory.id.desc())
    ).all()
    result = []
    kw = keyword.strip().lower()
    for r in rows:
        if kw and kw not in (f"{r.material.name} {r.material.spec}".lower()):
            continue
        result.append(
            {
                "id": r.id,
                "material_id": r.material_id,
                "name": r.material.name,
                "spec": r.material.spec,
                "unit": r.material.unit,
                "qty": _dec(Decimal(r.qty)),
                "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            }
        )
    return result


@app.get("/api/machine-ledger")
def machine_ledger_list(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    rows = db.scalars(
        select(MachineLedger)
        .where(MachineLedger.project_id == project.id)
        .order_by(MachineLedger.id.desc())
    ).all()
    kw = keyword.strip().lower()
    result: list[dict] = []
    for row in rows:
        if kw and kw not in f"{row.name} {row.spec} {row.remark}".lower():
            continue
        result.append(
            {
                "id": row.id,
                "name": row.name,
                "spec": row.spec,
                "use_date": row.use_date,
                "shift_count": _qty_text(Decimal(row.shift_count)),
                "remark": row.remark,
            }
        )
    return result


@app.post("/api/machine-ledger")
def machine_ledger_create(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    name = f"{payload.get('name', '')}".strip()
    if not name:
        raise HTTPException(status_code=400, detail="机械名称不能为空")
    spec = f"{payload.get('spec', '')}".strip()
    use_date = f"{payload.get('use_date', '')}".strip()
    remark = f"{payload.get('remark', '')}".strip()
    try:
        shift_count = Decimal(str(payload.get("shift_count", "0") or "0"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="台班格式不正确") from e
    if shift_count < Decimal("0"):
        raise HTTPException(status_code=400, detail="台班不能小于0")

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


@app.put("/api/machine-ledger/{row_id}")
def machine_ledger_update(
    row_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    row = db.get(MachineLedger, row_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="记录不存在")

    name = f"{payload.get('name', '')}".strip()
    if not name:
        raise HTTPException(status_code=400, detail="机械名称不能为空")
    row.name = name
    row.spec = f"{payload.get('spec', '')}".strip()
    row.use_date = f"{payload.get('use_date', '')}".strip()
    row.remark = f"{payload.get('remark', '')}".strip()
    try:
        row.shift_count = Decimal(str(payload.get("shift_count", "0") or "0"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="台班格式不正确") from e
    if row.shift_count < Decimal("0"):
        raise HTTPException(status_code=400, detail="台班不能小于0")

    db.commit()
    return {"ok": True}


@app.post("/api/machine-ledger/delete")
def machine_ledger_delete(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    raw_ids = payload.get("ids") or []
    ids: list[int] = []
    for v in raw_ids:
        try:
            n = int(v)
        except Exception:
            continue
        if n > 0:
            ids.append(n)
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

    deleted = 0
    for row in rows:
        db.delete(row)
        deleted += 1
    db.commit()

    for file_path in attachment_paths:
        _safe_remove_uploaded_file(file_path)

    return {"ok": True, "deleted": deleted}


@app.post("/api/inventory/delete")
def delete_inventory_rows(
    payload: InventoryDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    ids: list[int] = []
    for value in payload.inventory_ids:
        try:
            n = int(value)
        except Exception:
            continue
        if n > 0:
            ids.append(n)
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的库存记录")
    if not verify_password(payload.password, current_user.password_hash):
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


@app.get("/api/export/inventory")
def export_inventory(
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> StreamingResponse:
    rows = db.scalars(
        select(Inventory)
        .join(Material, Inventory.material_id == Material.id)
        .where(Material.project_id == project.id, Material.is_active.is_(True))
        .order_by(Inventory.id.desc())
    ).all()
    stream = io.StringIO()
    stream.write('<html><head><meta charset="utf-8"></head><body>')
    stream.write('<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;width:100%;">')
    stream.write('<tr><th colspan="5" style="text-align:center;font-size:16px;">库存台账</th></tr>')
    stream.write('<tr>')
    for title in ["名称", "规格", "库存", "单位", "更新时间"]:
        stream.write(f'<th style="text-align:center;padding:4px 2ch;white-space:nowrap;">{html.escape(title)}</th>')
    stream.write('</tr>')

    for r in rows:
        row_values = [
            r.material.name,
            r.material.spec,
            _dec(Decimal(r.qty)),
            r.material.unit,
            r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else "",
        ]
        stream.write('<tr>')
        for value in row_values:
            text = html.escape(f"{value or ''}")
            stream.write(f'<td style="text-align:center;padding:4px 2ch;white-space:nowrap;">{text}</td>')
        stream.write('</tr>')

    stream.write('</table></body></html>')

    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.ms-excel; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=inventory.xls"
    return response


@app.get("/api/export/database")
def export_database(_: User = Depends(_require_admin)) -> FileResponse:
    db_path = _resolve_db_path()
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="数据库文件不存在")
    return FileResponse(path=str(db_path), filename="app.db", media_type="application/octet-stream")


@app.post("/api/bootstrap/import-package")
async def import_bootstrap_package(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    _ensure_dirs()
    db_path = _resolve_db_path()

    try:
        with Session(engine) as db:
            if is_initialized(db):
                if not credentials:
                    raise HTTPException(status_code=401, detail="系统已初始化，导入数据包需登录")
                username = decode_access_token(credentials.credentials)
                if not username:
                    raise HTTPException(status_code=401, detail="Token 无效")
                user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
                if not user:
                    raise HTTPException(status_code=401, detail="用户不存在")
                if not _is_admin_user(db, user):
                    raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    except HTTPException:
        raise
    except Exception:
        # fresh deployment may have no schema yet; treat as uninitialized
        pass

    filename = (file.filename or "").lower()
    if not filename.endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=400, detail="仅支持导入 .db/.sqlite 数据包")

    raw = await file.read()
    if len(raw) < 1024:
        raise HTTPException(status_code=400, detail="数据包无效")
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="数据包超过 200MB")

    tmp_dir = Path(tempfile.gettempdir()) / "ems-import"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"import-{uuid4().hex}.db"
    try:
        if not raw.startswith(b"SQLite format 3\x00"):
            raise HTTPException(status_code=400, detail="数据包不是有效的 SQLite 数据库")
        with open(tmp_path, "wb") as fp:
            fp.write(raw)

        _validate_import_sqlite(tmp_path)

        engine.dispose()
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(tmp_path)) as src_conn:
                with sqlite3.connect(str(db_path)) as dst_conn:
                    src_conn.backup(dst_conn)
        except sqlite3.OperationalError as exc:
            raise HTTPException(status_code=500, detail="数据库正在被占用，请关闭并发操作后重试") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="导入写入失败，请稍后重试") from exc

        try:
            with sqlite3.connect(str(db_path)) as conn:
                user_count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0)
                if user_count <= 0:
                    raise HTTPException(status_code=400, detail="导入包无有效账号数据")
        except HTTPException:
            if db_path.exists():
                db_path.unlink()
            raise
        except Exception as exc:
            _safe_unlink(db_path)
            raise HTTPException(status_code=400, detail="导入后校验失败，请确认数据包正确") from exc
    finally:
        _safe_unlink(tmp_path)

    return {"ok": True, "initialized": True}


@app.get("/api/export/machine-ledger")
def export_machine_ledger(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> StreamingResponse:
    rows = db.scalars(select(MachineLedger).where(MachineLedger.project_id == project.id).order_by(MachineLedger.id.desc())).all()
    kw = keyword.strip().lower()
    stream = io.StringIO()
    stream.write('<html><head><meta charset="utf-8"></head><body>')
    stream.write('<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;width:100%;">')
    stream.write('<tr><th colspan="6" style="text-align:center;font-size:16px;">机械台账</th></tr>')
    stream.write('<tr>')
    for title in ["序号", "施工日期", "名称", "规格", "台班", "备注"]:
        stream.write(f'<th style="text-align:center;padding:4px 2ch;white-space:nowrap;">{html.escape(title)}</th>')
    stream.write('</tr>')

    filtered_rows: list[MachineLedger] = []
    for row in rows:
        if kw and kw not in f"{row.name} {row.spec} {row.remark}".lower():
            continue
        filtered_rows.append(row)

    for index, r in enumerate(filtered_rows, start=1):
        row_values = [
            f"{index:02d}",
            r.use_date or "",
            r.name,
            r.spec,
            _qty_text(Decimal(r.shift_count)) if r.shift_count is not None else "",
            r.remark,
        ]
        stream.write('<tr>')
        for value in row_values:
            text = html.escape(f"{value or ''}")
            stream.write(f'<td style="text-align:center;padding:4px 2ch;white-space:nowrap;">{text}</td>')
        stream.write('</tr>')

    stream.write('</table></body></html>')

    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.ms-excel; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=machine-ledger.xls"
    return response


IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_CONTENT_TYPES = IMAGE_CONTENT_TYPES | {"application/pdf"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_CONSTRUCTION_LOG_PHOTOS = 30
MAX_IMAGE_EDGE = 1920
IMAGE_WEBP_QUALITY = 82


def _target_project_id_for_attachment(db: Session, order_type: str, order_id: int) -> int:
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


def _compress_image_to_webp(content: bytes) -> tuple[bytes, str, str]:
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
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(status_code=400, detail="图片格式无法识别") from e

    return output.getvalue(), ".webp", "image/webp"


def _normalize_machine_photo_filenames(db: Session) -> None:
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
        day8 = _date8_from_text(base_date)

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


def _normalize_attachment_storage(db: Session) -> None:
    rows = db.scalars(
        select(Attachment)
        .where(Attachment.is_deleted.is_(False))
        .order_by(Attachment.created_at.asc(), Attachment.id.asc())
    ).all()
    if not rows:
        return

    uploads_root = _uploads_root()
    changed = False
    photo_daily_seq: dict[tuple[int, str, str], int] = {}
    for row in rows:
        try:
            project_id = _target_project_id_for_attachment(db, row.order_type, row.order_id)
            project = db.get(Project, project_id)
        except HTTPException:
            continue

        project_name = _safe_fs_name(project.name if project else f"工程{project_id}", f"工程{project_id}")
        bucket = _attachment_bucket(row.order_type, row.content_type)
        rel_dir = Path(project_name) / bucket

        is_photo = row.content_type in IMAGE_CONTENT_TYPES and row.order_type in {"construction_log", "machine_ledger"}
        if is_photo:
            day8 = _attachment_photo_day8(db, row.order_type, row.order_id)
            seq_key = (project_id, row.order_type, day8)
            next_seq = photo_daily_seq.get(seq_key, 1)
            ext = Path(row.filename or "").suffix.lower() or (".webp" if row.content_type == "image/webp" else ".jpg")
            desired_filename = _photo_filename_by_rule(row.order_type, day8, next_seq, ext)
            photo_daily_seq[seq_key] = next_seq + 1
        else:
            desired_filename = _safe_fs_name(_filename_from_content_type(row.filename or "file", row.content_type), "file")

        rel_stored, full_target = _alloc_attachment_target(
            db,
            rel_dir,
            desired_filename,
            current_attachment_id=row.id,
            current_stored_name=row.stored_name,
        )

        old_path = _resolve_attachment_disk_path(row)
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
        row.path = str(uploads_root / Path(rel_stored))
        changed = True

    if changed:
        db.commit()


@app.post("/api/attachments/upload")
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

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件超过10MB")

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
        if order_type == "construction_log":
            project = db.get(Project, target_project_id)
            project_name = _safe_fs_name(project.name if project else f"工程{target_project_id}", f"工程{target_project_id}")
            seq = _next_photo_seq(db, project_name, order_type, day8)
            display_name = _photo_filename_by_rule(order_type, day8, seq, ext)
        elif order_type == "machine_ledger":
            project = db.get(Project, target_project_id)
            project_name = _safe_fs_name(project.name if project else f"工程{target_project_id}", f"工程{target_project_id}")
            seq = _next_photo_seq(db, project_name, order_type, day8)
            display_name = _photo_filename_by_rule(order_type, day8, seq, ext)
        else:
            stem = Path(display_name).stem or "photo"
            display_name = f"{stem}.webp"
    else:
        ext = Path(display_name).suffix or ".bin"

    project = db.get(Project, target_project_id)
    project_name = _safe_fs_name(project.name if project else f"工程{target_project_id}", f"工程{target_project_id}")
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


@app.get("/api/attachments")
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
            "id": r.id,
            "filename": r.filename,
            "content_type": r.content_type,
            "size": r.size,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/api/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
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
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded}"
    return response


@app.get("/api/attachments/{attachment_id}/preview")
def preview_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
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
    response.headers["Content-Disposition"] = f"inline; filename*=UTF-8''{encoded}"
    return response


@app.delete("/api/attachments/{attachment_id}")
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
    db.commit()
    return {"ok": True}


@app.post("/api/admin/attachments/cleanup")
def cleanup_deleted_attachments(
    retention_days: int = Query(default=0, ge=0, le=3650),
    db: Session = Depends(get_db),
    _: User = Depends(_require_admin),
) -> dict:
    return _cleanup_deleted_attachments(db, retention_days=retention_days)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/site-photos")
def list_site_photos(
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    rows = db.execute(
        select(Attachment, ConstructionLog)
        .join(
            ConstructionLog,
            and_(Attachment.order_type == "construction_log", Attachment.order_id == ConstructionLog.id),
        )
        .where(
            Attachment.is_deleted.is_(False),
            Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
            ConstructionLog.project_id == project.id,
        )
        .order_by(ConstructionLog.log_date.desc(), Attachment.id.desc())
    ).all()

    machine_rows = db.execute(
        select(Attachment, MachineLedger)
        .join(
            MachineLedger,
            and_(Attachment.order_type == "machine_ledger", Attachment.order_id == MachineLedger.id),
        )
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
        for attachment, log in rows
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
    result.sort(key=lambda x: (x.get("log_date", ""), x.get("id", 0)), reverse=True)
    return result


frontend_dist_dir = Path(settings.frontend_dist_dir)
app.mount("/assets", StaticFiles(directory=frontend_dist_dir / "assets", check_dir=False), name="frontend-assets")


@app.get("/site-icon.svg", include_in_schema=False)
def frontend_site_icon() -> FileResponse:
    icon_path = frontend_dist_dir / "site-icon.svg"
    if not icon_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(icon_path)


@app.get("/pwa-192.png", include_in_schema=False)
def frontend_pwa_icon_192() -> FileResponse:
    icon_path = frontend_dist_dir / "pwa-192.png"
    if not icon_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(icon_path)


@app.get("/pwa-512.png", include_in_schema=False)
def frontend_pwa_icon_512() -> FileResponse:
    icon_path = frontend_dist_dir / "pwa-512.png"
    if not icon_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(icon_path)


@app.get("/pwa-512-maskable.png", include_in_schema=False)
def frontend_pwa_icon_512_maskable() -> FileResponse:
    icon_path = frontend_dist_dir / "pwa-512-maskable.png"
    if not icon_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(icon_path)


@app.get("/manifest.webmanifest", include_in_schema=False)
def frontend_manifest() -> FileResponse:
    file_path = frontend_dist_dir / "manifest.webmanifest"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(file_path)


@app.get("/sw.js", include_in_schema=False)
def frontend_sw() -> FileResponse:
    file_path = frontend_dist_dir / "sw.js"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(file_path)


@app.get("/workbox-{hash_part}.js", include_in_schema=False)
def frontend_workbox(hash_part: str) -> FileResponse:
    filename = f"workbox-{hash_part}.js"
    file_path = frontend_dist_dir / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(file_path)


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_app(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    index_path = frontend_dist_dir / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="前端资源未构建")

    if full_path and full_path != "index.html":
        requested_path = (frontend_dist_dir / full_path).resolve()
        base_path = frontend_dist_dir.resolve()
        if requested_path.is_file() and base_path in requested_path.parents:
            return FileResponse(requested_path)

    return FileResponse(index_path)
