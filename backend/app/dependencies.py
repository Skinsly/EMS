from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Project, User, UserProjectAccess
from .security import decode_access_token

security = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")

    username = decode_access_token(credentials.credentials)
    if not username:
        raise HTTPException(status_code=401, detail="Token 无效")

    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def is_admin_user(db: Session, user: User) -> bool:
    first_user_id = db.scalar(select(User.id).where(User.is_active.is_(True)).order_by(User.id.asc()).limit(1))
    return bool(first_user_id and int(first_user_id) == int(user.id))


def require_admin(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    if not is_admin_user(db, current_user):
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    return current_user


def require_project(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    x_project_id: str | None = Header(default=None),
) -> Project:
    if not x_project_id:
        raise HTTPException(status_code=400, detail="请先选择工程")
    try:
        project_id = int(x_project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="工程参数无效") from exc
    project = db.get(Project, project_id)
    if not project or not project.is_active:
        raise HTTPException(status_code=400, detail="工程不存在或已停用")
    if not is_admin_user(db, current_user):
        access = db.scalar(
            select(UserProjectAccess.id).where(
                UserProjectAccess.user_id == current_user.id,
                UserProjectAccess.project_id == project.id,
            )
        )
        if not access:
            raise HTTPException(status_code=403, detail="无权访问该工程")
    return project
