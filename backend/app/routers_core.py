from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .bootstrap import create_initial_admin, is_initialized
from .config import settings
from .database import get_db
from .dependencies import require_project as _require_project, require_user as _require_user, security
from .models import Project, User, UserProjectAccess
from .schemas import (
    BootstrapInitRequest,
    FileCategoryCreate,
    FileCategoryDeleteRequest,
    FileCategoryRename,
    LoginRequest,
    PasswordChangeRequest,
    ProjectCreate,
    ProjectDeleteRequest,
    TokenResponse,
)
from .security import create_access_token, get_password_hash, verify_password
from .services.bootstrap_import import import_bootstrap_package_file
from .services.project_files import (
    create_category as _create_file_category,
    delete_category as _delete_file_category,
    delete_project_file as _delete_project_file,
    download_project_file as _download_project_file,
    list_categories as _list_file_categories,
    list_project_files as _list_project_files,
    rename_category as _rename_file_category,
    upload_project_file as _upload_project_file,
)
from .services.projects import delete_project_cascade as _delete_project_cascade
from .startup import DELETE_PROJECT_ACK_PHRASE, ensure_dirs as _ensure_dirs, validate_password_strength as _validate_password_strength

router = APIRouter(prefix="/api")


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.scalar(select(func.count()).select_from(User)) == 0:
        raise HTTPException(status_code=403, detail="系统未初始化，请先创建管理员账号")
    user = db.scalar(select(User).where(User.username == payload.username, User.is_active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return TokenResponse(access_token=token, must_change_password=user.must_change_password)


@router.get("/bootstrap/status")
def bootstrap_status(db: Session = Depends(get_db)) -> dict:
    return {"initialized": is_initialized(db)}


@router.post("/bootstrap/init", response_model=TokenResponse)
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


@router.post("/auth/change-password")
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


@router.post("/projects")
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
        users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        existing_access = {
            int(uid)
            for uid in db.scalars(select(UserProjectAccess.user_id).where(UserProjectAccess.project_id == exists.id)).all()
        }
        for user in users:
            if int(user.id) not in existing_access:
                db.add(UserProjectAccess(user_id=user.id, project_id=exists.id))
        db.commit()
        db.refresh(exists)
        return {"id": exists.id}

    row = Project(name=name, start_date=payload.start_date.strip())
    db.add(row)
    db.flush()
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    for user in users:
        db.add(UserProjectAccess(user_id=user.id, project_id=row.id))
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), _: User = Depends(_require_user)) -> list[dict]:
    rows = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.id.desc())).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "start_date": p.start_date,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


@router.delete("/projects/{project_id}")
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
    return _delete_project_cascade(project_id=project_id, db=db, password_ok=password_ok, confirm_ok=confirm_ok)


@router.get("/file-categories")
def list_file_categories(db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> list[dict]:
    return _list_file_categories(db, project)


@router.post("/file-categories")
def create_file_category(payload: FileCategoryCreate, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _create_file_category(payload.name, db, project)


@router.put("/file-categories/{category_id}")
def rename_file_category(category_id: int, payload: FileCategoryRename, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _rename_file_category(category_id, payload.name, db, project)


@router.delete("/file-categories/{category_id}")
def delete_file_category(
    category_id: int,
    payload: FileCategoryDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return _delete_file_category(
        category_id=category_id,
        password=payload.password,
        delete_files_confirmed=payload.delete_files_confirmed,
        db=db,
        current_user=current_user,
        project=project,
    )


@router.post("/project-files/upload")
async def upload_project_file(
    category_id: int,
    remark: str = "",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> dict:
    return await _upload_project_file(
        category_id=category_id,
        remark=remark,
        file=file,
        db=db,
        current_user=current_user,
        project=project,
    )


@router.get("/project-files")
def list_project_files(keyword: str = "", category_id: int | None = None, page: int | None = None, page_size: int | None = None, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> list[dict] | dict:
    return _list_project_files(keyword=keyword, category_id=category_id, db=db, project=project, page=page, page_size=page_size)


def download_project_file(file_id: int, db: Session, project: Project, inline: bool) -> FileResponse:
    return _download_project_file(file_id=file_id, db=db, project=project, inline=inline)


@router.get("/project-files/{file_id}/download")
def download_project_file_route(
    file_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> FileResponse:
    return download_project_file(file_id, db, project, inline=False)


@router.get("/project-files/{file_id}/preview")
def preview_project_file_route(
    file_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_user),
    project: Project = Depends(_require_project),
) -> FileResponse:
    return download_project_file(file_id, db, project, inline=True)


@router.delete("/project-files/{file_id}")
def delete_project_file(file_id: int, db: Session = Depends(get_db), _: User = Depends(_require_user), project: Project = Depends(_require_project)) -> dict:
    return _delete_project_file(file_id=file_id, db=db, project=project)


@router.post("/bootstrap/import-package")
async def import_bootstrap_package(
    file: UploadFile = File(...),
    admin_password: str = Form(default=""),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    _ensure_dirs()
    return await import_bootstrap_package_file(
        file=file,
        credentials=credentials,
        data_dir=settings.data_dir,
        db_path_config=settings.db_path,
        admin_password=admin_password,
    )
