import os
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FileCategory, Project, ProjectFile, User
from ..security import verify_password
from .attachments import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_SIZE,
    alloc_attachment_target,
    resolve_attachment_disk_path,
    safe_fs_name,
    safe_remove_uploaded_file,
    uploads_root,
)

DEFAULT_CATEGORY_NAMES = ["施工方案", "签证单", "甲供材料", "乙供材料", "退库单", "图纸", "其他"]


def ensure_default_categories(db: Session, project_id: int) -> None:
    exists = db.scalar(select(FileCategory.id).where(FileCategory.project_id == project_id).limit(1))
    if exists:
        return
    rows = [
        FileCategory(project_id=project_id, name=name, sort_order=index)
        for index, name in enumerate(DEFAULT_CATEGORY_NAMES, start=1)
    ]
    db.add_all(rows)
    db.commit()


def list_categories(db: Session, project: Project) -> list[dict]:
    ensure_default_categories(db, project.id)
    file_counts = dict(
        db.execute(
            select(ProjectFile.category_id, func.count(ProjectFile.id))
            .where(ProjectFile.project_id == project.id, ProjectFile.is_deleted.is_(False))
            .group_by(ProjectFile.category_id)
        ).all()
    )
    rows = db.scalars(
        select(FileCategory)
        .where(FileCategory.project_id == project.id)
        .order_by(FileCategory.sort_order.asc(), FileCategory.id.asc())
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "sort_order": row.sort_order,
            "file_count": int(file_counts.get(row.id, 0) or 0),
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in rows
    ]


def create_category(name: str, db: Session, project: Project) -> dict:
    ensure_default_categories(db, project.id)
    clean_name = safe_fs_name((name or "").strip(), "")
    if not clean_name:
        raise HTTPException(status_code=400, detail="分类名称不能为空")

    exists = db.scalar(
        select(FileCategory).where(
            FileCategory.project_id == project.id,
            func.lower(FileCategory.name) == clean_name.lower(),
        )
    )
    if exists:
        raise HTTPException(status_code=400, detail="分类名称已存在")

    max_sort = db.scalar(select(func.max(FileCategory.sort_order)).where(FileCategory.project_id == project.id))
    row = FileCategory(project_id=project.id, name=clean_name, sort_order=int(max_sort or 0) + 1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


def _relocate_category_files(db: Session, project: Project, category: FileCategory, new_name: str) -> int:
    files = db.scalars(
        select(ProjectFile)
        .where(
            ProjectFile.project_id == project.id,
            ProjectFile.category_id == category.id,
            ProjectFile.is_deleted.is_(False),
        )
        .order_by(ProjectFile.created_at.asc(), ProjectFile.id.asc())
    ).all()
    if not files:
        return 0

    project_dir = safe_fs_name(project.name or f"工程{project.id}", f"工程{project.id}")
    root = uploads_root()
    moved = 0
    for row in files:
        desired_name = safe_fs_name(row.filename or "file", "file")
        rel_stored, full_target = alloc_attachment_target(
            db,
            Path(project_dir) / "文件管理" / new_name,
            desired_name,
            current_attachment_id=row.id,
            current_stored_name=row.stored_name,
        )
        old_path = resolve_attachment_disk_path(row)
        if old_path and old_path.exists() and old_path.resolve() != full_target.resolve():
            full_target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(str(old_path), str(full_target))
            except OSError as exc:
                raise HTTPException(status_code=500, detail="分类重命名时文件迁移失败") from exc

        row.stored_name = rel_stored
        row.path = str(root / Path(rel_stored))
        moved += 1
    return moved


def rename_category(category_id: int, name: str, db: Session, project: Project) -> dict:
    ensure_default_categories(db, project.id)
    row = db.get(FileCategory, category_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="分类不存在")

    new_name = safe_fs_name((name or "").strip(), "")
    if not new_name:
        raise HTTPException(status_code=400, detail="分类名称不能为空")
    if new_name == row.name:
        return {"ok": True, "id": row.id, "name": row.name, "moved": 0}

    exists = db.scalar(
        select(FileCategory.id).where(
            FileCategory.project_id == project.id,
            FileCategory.id != row.id,
            func.lower(FileCategory.name) == new_name.lower(),
        )
    )
    if exists:
        raise HTTPException(status_code=400, detail="分类名称已存在")

    moved = _relocate_category_files(db, project, row, new_name)
    row.name = new_name
    db.commit()
    return {"ok": True, "id": row.id, "name": row.name, "moved": moved}


def _cleanup_empty_category_dirs(project_name: str, category_name: str) -> None:
    root = uploads_root()
    category_dir = root / Path(project_name) / "文件管理" / category_name
    try:
        if category_dir.exists() and category_dir.is_dir() and not any(category_dir.iterdir()):
            category_dir.rmdir()
        parent_dir = category_dir.parent
        if parent_dir.exists() and parent_dir.is_dir() and not any(parent_dir.iterdir()):
            parent_dir.rmdir()
    except OSError:
        return


def delete_category(
    category_id: int,
    password: str,
    delete_files_confirmed: bool,
    db: Session,
    current_user: User,
    project: Project,
) -> dict:
    ensure_default_categories(db, project.id)
    row = db.get(FileCategory, category_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="分类不存在")
    if not verify_password((password or "").strip(), current_user.password_hash):
        raise HTTPException(status_code=400, detail="登录密码错误")

    files = db.scalars(
        select(ProjectFile).where(
            ProjectFile.project_id == project.id,
            ProjectFile.category_id == row.id,
            ProjectFile.is_deleted.is_(False),
        )
    ).all()
    file_count = len(files)
    if file_count > 0 and not delete_files_confirmed:
        raise HTTPException(status_code=400, detail=f"该分类下还有 {file_count} 个文件，请确认是否一并删除")

    deleted_files = 0
    for item in files:
        if safe_remove_uploaded_file(item.path):
            deleted_files += 1
        db.delete(item)

    project_name = safe_fs_name(project.name or f"工程{project.id}", f"工程{project.id}")
    old_name = row.name
    db.delete(row)
    db.commit()
    _cleanup_empty_category_dirs(project_name, old_name)
    return {"ok": True, "deleted_files": deleted_files, "total_files": file_count}


async def upload_project_file(
    category_id: int,
    remark: str,
    file: UploadFile,
    db: Session,
    current_user: User,
    project: Project,
) -> dict:
    ensure_default_categories(db, project.id)
    category = db.get(FileCategory, category_id)
    if not category or category.project_id != project.id:
        raise HTTPException(status_code=404, detail="分类不存在")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="仅支持图片和PDF")

    display_name = safe_fs_name((file.filename or "").strip(), "file")
    project_name = safe_fs_name(project.name or f"工程{project.id}", f"工程{project.id}")
    rel_dir = Path(project_name) / "文件管理" / safe_fs_name(category.name, "其他")
    rel_stored, full_path = alloc_attachment_target(db, rel_dir, display_name)

    total_size = 0
    try:
        with open(full_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=400, detail="文件超过10MB")
                f.write(chunk)
    except HTTPException:
        safe_remove_uploaded_file(str(full_path))
        raise
    except Exception as exc:
        safe_remove_uploaded_file(str(full_path))
        raise HTTPException(status_code=500, detail="文件写入失败") from exc

    if total_size <= 0:
        safe_remove_uploaded_file(str(full_path))
        raise HTTPException(status_code=400, detail="文件内容为空")

    row = ProjectFile(
        project_id=project.id,
        category_id=category.id,
        filename=display_name,
        stored_name=rel_stored,
        content_type=content_type,
        size=total_size,
        remark=(remark or "").strip(),
        uploaded_by=current_user.username,
        path=str(full_path),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "filename": row.filename,
        "category_name": category.name,
    }


def ensure_all_projects_default_categories(db: Session) -> None:
    project_ids = [int(pid) for pid in db.scalars(select(Project.id)).all()]
    changed = False
    for project_id in project_ids:
        exists = db.scalar(select(FileCategory.id).where(FileCategory.project_id == project_id).limit(1))
        if exists:
            continue
        rows = [
            FileCategory(project_id=project_id, name=name, sort_order=index)
            for index, name in enumerate(DEFAULT_CATEGORY_NAMES, start=1)
        ]
        db.add_all(rows)
        changed = True
    if changed:
        db.commit()


def list_project_files(
    keyword: str,
    category_id: int | None,
    db: Session,
    project: Project,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | dict:
    ensure_default_categories(db, project.id)
    stmt = (
        select(ProjectFile, FileCategory)
        .join(FileCategory, ProjectFile.category_id == FileCategory.id)
        .where(
            ProjectFile.project_id == project.id,
            ProjectFile.is_deleted.is_(False),
            FileCategory.project_id == project.id,
        )
        .order_by(ProjectFile.id.desc())
    )
    if category_id is not None:
        stmt = stmt.where(ProjectFile.category_id == int(category_id))

    if keyword.strip():
        kw = f"%{keyword.strip().lower()}%"
        stmt = stmt.where(
            func.lower(
                func.ifnull(ProjectFile.filename, "")
                + " "
                + func.ifnull(ProjectFile.remark, "")
                + " "
                + func.ifnull(FileCategory.name, "")
            ).like(kw)
        )

    if page is None and page_size is None:
        rows = db.execute(stmt).all()
        return [
            {
                "id": pf.id,
                "category_id": cat.id,
                "category_name": cat.name,
                "filename": pf.filename,
                "content_type": pf.content_type,
                "size": pf.size,
                "remark": pf.remark,
                "uploaded_by": pf.uploaded_by,
                "created_at": pf.created_at.isoformat() if pf.created_at else "",
            }
            for pf, cat in rows
        ]

    page_value = max(1, int(page or 1))
    page_size_value = max(1, min(100, int(page_size or 10)))
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    rows = db.execute(stmt.offset((page_value - 1) * page_size_value).limit(page_size_value)).all()
    items = [
        {
            "id": pf.id,
            "category_id": cat.id,
            "category_name": cat.name,
            "filename": pf.filename,
            "content_type": pf.content_type,
            "size": pf.size,
            "remark": pf.remark,
            "uploaded_by": pf.uploaded_by,
            "created_at": pf.created_at.isoformat() if pf.created_at else "",
        }
        for pf, cat in rows
    ]
    total_pages = max(1, (total + page_size_value - 1) // page_size_value)
    return {
        "items": items,
        "total": total,
        "page": page_value,
        "page_size": page_size_value,
        "total_pages": total_pages,
    }


def get_project_file_or_404(file_id: int, db: Session, project: Project) -> ProjectFile:
    row = db.get(ProjectFile, file_id)
    if not row or row.is_deleted or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="文件不存在")
    return row


def download_project_file(file_id: int, db: Session, project: Project, inline: bool = False) -> FileResponse:
    row = get_project_file_or_404(file_id, db, project)
    path = resolve_attachment_disk_path(row)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    response = FileResponse(path=str(path), filename=row.filename, media_type=row.content_type)
    encoded = quote(row.filename or "file")
    disposition = "inline" if inline else "attachment"
    response.headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded}"
    return response


def delete_project_file(file_id: int, db: Session, project: Project) -> dict:
    row = get_project_file_or_404(file_id, db, project)
    storage_key = (row.stored_name or "").strip() or (row.path or "").strip()
    disk_path = resolve_attachment_disk_path(row)
    should_remove_file = bool(storage_key and disk_path and disk_path.exists())
    if should_remove_file and not safe_remove_uploaded_file(storage_key):
        db.rollback()
        raise HTTPException(status_code=500, detail="文件删除失败，请重试")

    row.is_deleted = True
    db.commit()

    cat = db.get(FileCategory, row.category_id)
    if cat and cat.project_id == project.id:
        project_name = safe_fs_name(project.name or f"工程{project.id}", f"工程{project.id}")
        _cleanup_empty_category_dirs(project_name, cat.name)
    return {"ok": True}
