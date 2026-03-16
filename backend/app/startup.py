import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine
from .idempotency import cleanup_expired_idempotency
from .models import Project, User, UserProjectAccess, Warehouse
from .services.attachments import (
    cleanup_deleted_attachments,
    normalize_attachment_storage,
    normalize_machine_photo_filenames,
)
from .services.project_files import ensure_all_projects_default_categories

PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")
DELETE_PROJECT_ACK_PHRASE = "我已知晓删除后不可恢复"


def cors_origins() -> list[str]:
    values = [v.strip() for v in settings.cors_origins.split(",") if v.strip()]
    return values or ["http://localhost:5173", "http://127.0.0.1:5173"]


def validate_password_strength(password: str) -> bool:
    return bool(PASSWORD_RULE.match(password))


def ensure_dirs() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)


def resolve_db_path_from_settings() -> Path:
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = Path(settings.data_dir) / db_path
    return db_path


def seed_data(db: Session) -> None:
    warehouse = db.scalar(select(Warehouse).where(Warehouse.name == "主仓库"))
    if not warehouse:
        db.add(Warehouse(name="主仓库"))
    db.commit()


def ensure_user_project_access(db: Session) -> None:
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    projects = db.scalars(select(Project).where(Project.is_active.is_(True))).all()
    if not users or not projects:
        return
    existing_pairs = {
        (int(row.user_id), int(row.project_id))
        for row in db.scalars(select(UserProjectAccess)).all()
    }
    changed = False
    for user in users:
        for project in projects:
            key = (int(user.id), int(project.id))
            if key in existing_pairs:
                continue
            db.add(UserProjectAccess(user_id=user.id, project_id=project.id))
            existing_pairs.add(key)
            changed = True
    if changed:
        db.commit()


def ensure_schema_updates() -> None:
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
        if not has_column("attachments", "deleted_at"):
            conn.execute(text("ALTER TABLE attachments ADD COLUMN deleted_at DATETIME"))
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
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS file_categories (
                  id INTEGER PRIMARY KEY,
                  project_id INTEGER NOT NULL,
                  name VARCHAR(64) NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  CONSTRAINT uq_file_category_project_name UNIQUE (project_id, name)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_file_categories_project_id ON file_categories(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_file_categories_name ON file_categories(name)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS project_files (
                  id INTEGER PRIMARY KEY,
                  project_id INTEGER NOT NULL,
                  category_id INTEGER NOT NULL,
                  filename VARCHAR(255) NOT NULL,
                  stored_name VARCHAR(400) NOT NULL UNIQUE,
                  path VARCHAR(400) NOT NULL,
                  content_type VARCHAR(100) NOT NULL,
                  size INTEGER NOT NULL,
                  remark VARCHAR(255) NOT NULL DEFAULT '',
                  uploaded_by VARCHAR(64) NOT NULL DEFAULT 'skins',
                  is_deleted BOOLEAN NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(category_id) REFERENCES file_categories(id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_files_project_id ON project_files(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_files_category_id ON project_files(category_id)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_project_access (
                  id INTEGER PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  project_id INTEGER NOT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  CONSTRAINT uq_user_project_access UNIQUE (user_id, project_id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_project_access_user_id ON user_project_access(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_project_access_project_id ON user_project_access(project_id)"))
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    Base.metadata.create_all(bind=engine)
    ensure_schema_updates()
    with Session(engine) as db:
        seed_data(db)
        ensure_user_project_access(db)
        ensure_all_projects_default_categories(db)
        cleanup_expired_idempotency(db)
        normalize_machine_photo_filenames(db)
        normalize_attachment_storage(db)
        cleanup_deleted_attachments(db)
    yield
