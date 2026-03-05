from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Project, User, UserProjectAccess
from .schemas import BootstrapInitRequest, TokenResponse
from .security import create_access_token, get_password_hash


def is_initialized(db: Session) -> bool:
    count = int(db.scalar(select(func.count()).select_from(User)) or 0)
    return count > 0


def create_initial_admin(db: Session, payload: BootstrapInitRequest) -> TokenResponse:
    row = User(
        username=payload.username.strip(),
        password_hash=get_password_hash(payload.password.strip()),
        must_change_password=False,
        is_active=True,
    )
    db.add(row)
    db.commit()

    projects = db.scalars(select(Project).where(Project.is_active.is_(True))).all()
    for project in projects:
        db.add(UserProjectAccess(user_id=row.id, project_id=project.id))
    db.commit()

    token = create_access_token(row.username)
    return TokenResponse(access_token=token, must_change_password=False)
