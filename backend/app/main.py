import json
import re
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, case, func, literal, or_, select, text, union_all
from sqlalchemy.orm import Session

from .config import settings
from .bootstrap import create_initial_admin, is_initialized
from .database import Base, engine, get_db
from .dependencies import (
    require_admin as _require_admin,
    require_project as _require_project,
    require_user as _require_user,
    security,
)
from .idempotency import cleanup_expired_idempotency
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
    StockInCreate,
    StockOutCreate,
    TokenResponse,
)
from .services.exports import (
    build_inventory_export,
    build_machine_ledger_export,
    build_stock_records_export,
)
from .services.bootstrap_import import (
    import_bootstrap_package_file,
    resolve_db_path as _resolve_db_path_from_config,
)
from .services.stock_flow import (
    commit_stock_draft as _commit_stock_draft,
    correct_stock_record as _correct_stock_record,
    create_stock_in as _create_stock_in,
    create_stock_out as _create_stock_out,
    load_stock_draft as _load_stock_draft,
    stock_draft_type_or_400 as _stock_draft_type_or_400,
)
from .services.logs_and_ledger import (
    create_construction_log as _create_construction_log,
    delete_construction_log as _delete_construction_log,
    list_construction_logs as _list_construction_logs,
    machine_ledger_create as _machine_ledger_create,
    machine_ledger_delete as _machine_ledger_delete,
    machine_ledger_list as _machine_ledger_list,
    machine_ledger_update as _machine_ledger_update,
    update_construction_log as _update_construction_log,
)
from .services.materials_inventory import (
    create_material as _create_material,
    delete_inventory_rows as _delete_inventory_rows,
    delete_materials as _delete_materials,
    inventory_list as _inventory_list,
    list_materials as _list_materials,
    update_material as _update_material,
)
from .services.projects import delete_project_cascade as _delete_project_cascade
from .services.attachments import (
    ALLOWED_CONTENT_TYPES,
    IMAGE_CONTENT_TYPES,
    MAX_CONSTRUCTION_LOG_PHOTOS,
    MAX_UPLOAD_SIZE,
    alloc_attachment_target as _alloc_attachment_target,
    attachment_bucket as _attachment_bucket,
    attachment_photo_day8 as _attachment_photo_day8,
    cleanup_deleted_attachments as _cleanup_deleted_attachments,
    compress_image_to_webp as _compress_image_to_webp,
    filename_from_content_type as _filename_from_content_type,
    next_photo_seq as _next_photo_seq,
    normalize_attachment_storage as _normalize_attachment_storage,
    normalize_machine_photo_filenames as _normalize_machine_photo_filenames,
    photo_filename_by_rule as _photo_filename_by_rule,
    resolve_attachment_disk_path as _resolve_attachment_disk_path,
    safe_fs_name as _safe_fs_name,
    target_project_id_for_attachment as _target_project_id_for_attachment,
)
from .security import create_access_token, get_password_hash, verify_password

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
    return _resolve_db_path_from_config(settings.data_dir, settings.db_path)


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


def _dec(v: Decimal) -> str:
    return f"{v:.3f}"


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
    password_ok = verify_password(payload.password, current_user.password_hash)
    confirm_ok = payload.confirm_text.strip() == DELETE_PROJECT_ACK_PHRASE
    if not confirm_ok:
        raise HTTPException(status_code=400, detail=f"确认短语不正确，请输入：{DELETE_PROJECT_ACK_PHRASE}")
    return _delete_project_cascade(
        project_id=project_id,
        db=db,
        password_ok=password_ok,
        confirm_ok=confirm_ok,
    )


@app.post("/api/construction-logs")
def create_construction_log(
    payload: ConstructionLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _create_construction_log(payload, db, current_user, project)


@app.get("/api/construction-logs")
def list_construction_logs(
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    return _list_construction_logs(db, project)


@app.put("/api/construction-logs/{log_id}")
def update_construction_log(
    log_id: int,
    payload: ConstructionLogUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _update_construction_log(log_id, payload, db, project)


@app.delete("/api/construction-logs/{log_id}")
def delete_construction_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _delete_construction_log(log_id, db, project)


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
    return _create_material(payload, db, project)


@app.get("/api/materials")
def list_materials(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    return _list_materials(keyword, db, project)


@app.put("/api/materials/{material_id}")
def update_material(
    material_id: int,
    payload: MaterialUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _update_material(material_id, payload, db, project)


@app.post("/api/materials/delete")
def delete_materials(
    payload: MaterialDeleteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _delete_materials(payload, db, project)


@app.post("/api/stock-in")
def create_stock_in(
    payload: StockInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    x_idempotency_key: str | None = Header(default=None),
) -> dict:
    return _create_stock_in(payload, db, current_user, project, x_idempotency_key)


@app.post("/api/stock-out")
def create_stock_out(
    payload: StockOutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
    x_idempotency_key: str | None = Header(default=None),
) -> dict:
    return _create_stock_out(payload, db, current_user, project, x_idempotency_key)


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
    return _commit_stock_draft(draft_type, db, current_user, project)


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
    return _correct_stock_record(payload, db, current_user, project)


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
    return build_stock_records_export(rows, kind)


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
    return _inventory_list(keyword, db, project)


@app.get("/api/machine-ledger")
def machine_ledger_list(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> list[dict]:
    return _machine_ledger_list(keyword, db, project)


@app.post("/api/machine-ledger")
def machine_ledger_create(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _machine_ledger_create(payload, db, project)


@app.put("/api/machine-ledger/{row_id}")
def machine_ledger_update(
    row_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _machine_ledger_update(row_id, payload, db, project)


@app.post("/api/machine-ledger/delete")
def machine_ledger_delete(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _machine_ledger_delete(payload, db, project)


@app.post("/api/inventory/delete")
def delete_inventory_rows(
    payload: InventoryDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _delete_inventory_rows(
        payload=payload,
        db=db,
        project=project,
        password_ok=verify_password(payload.password, current_user.password_hash),
    )


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
    return build_inventory_export(rows)


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
    return await import_bootstrap_package_file(
        file=file,
        credentials=credentials,
        data_dir=settings.data_dir,
        db_path_config=settings.db_path,
    )


@app.get("/api/export/machine-ledger")
def export_machine_ledger(
    keyword: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> StreamingResponse:
    rows = db.scalars(select(MachineLedger).where(MachineLedger.project_id == project.id).order_by(MachineLedger.id.desc())).all()
    return build_machine_ledger_export(rows, keyword=keyword)


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
