import sqlite3
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bootstrap import is_initialized
from ..database import engine
from ..dependencies import is_admin_user
from ..models import User
from ..security import decode_access_token, verify_password


def resolve_db_path(data_dir: str, db_path_config: str) -> Path:
    db_path = Path(db_path_config)
    if not db_path.is_absolute():
        db_path = Path(data_dir) / db_path
    return db_path


def safe_unlink(path: Path) -> None:
    for _ in range(6):
        try:
            if path.exists():
                path.unlink()
            return
        except PermissionError:
            time.sleep(0.12)
        except FileNotFoundError:
            return


def validate_import_sqlite(db_file: Path) -> None:
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


def ensure_import_permission(credentials: HTTPAuthorizationCredentials | None, admin_password: str) -> None:
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
                if not is_admin_user(db, user):
                    raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
                if not verify_password((admin_password or "").strip(), user.password_hash):
                    raise HTTPException(status_code=400, detail="管理员密码错误")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="导入权限校验失败") from exc


async def import_bootstrap_package_file(
    file: UploadFile,
    credentials: HTTPAuthorizationCredentials | None,
    data_dir: str,
    db_path_config: str,
    admin_password: str = "",
) -> dict:
    db_path = resolve_db_path(data_dir, db_path_config)
    ensure_import_permission(credentials, admin_password)

    filename = (file.filename or "").lower()
    if not filename.endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=400, detail="仅支持导入 .db/.sqlite 数据包")

    tmp_dir = Path(tempfile.gettempdir()) / "ems-import"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"import-{uuid4().hex}.db"
    try:
        max_bytes = 200 * 1024 * 1024
        total_size = 0
        head = b""
        with open(tmp_path, "wb") as fp:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if len(head) < 16:
                    need = 16 - len(head)
                    head += chunk[:need]
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise HTTPException(status_code=400, detail="数据包超过 200MB")
                fp.write(chunk)

        if total_size < 1024:
            raise HTTPException(status_code=400, detail="数据包无效")
        if not head.startswith(b"SQLite format 3\x00"):
            raise HTTPException(status_code=400, detail="数据包不是有效的 SQLite 数据库")

        validate_import_sqlite(tmp_path)

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
            safe_unlink(db_path)
            raise HTTPException(status_code=400, detail="导入后校验失败，请确认数据包正确") from exc
    finally:
        safe_unlink(tmp_path)

    return {"ok": True, "initialized": True}
