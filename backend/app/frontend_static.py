from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def register_frontend_static(app, frontend_dist_dir: Path) -> None:
    app.mount("/assets", StaticFiles(directory=frontend_dist_dir / "assets", check_dir=False), name="frontend-assets")


router = APIRouter(include_in_schema=False)


def _file_or_404(file_path: Path) -> FileResponse:
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="静态文件不存在")
    return FileResponse(file_path)


@router.get("/site-icon.svg")
def frontend_site_icon() -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / "site-icon.svg")


@router.get("/pwa-192.png")
def frontend_pwa_icon_192() -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / "pwa-192.png")


@router.get("/pwa-512.png")
def frontend_pwa_icon_512() -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / "pwa-512.png")


@router.get("/pwa-512-maskable.png")
def frontend_pwa_icon_512_maskable() -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / "pwa-512-maskable.png")


@router.get("/manifest.webmanifest")
def frontend_manifest() -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / "manifest.webmanifest")


@router.get("/sw.js")
def frontend_sw() -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / "sw.js")


@router.get("/workbox-{hash_part}.js")
def frontend_workbox(hash_part: str) -> FileResponse:
    from .config import settings

    return _file_or_404(Path(settings.frontend_dist_dir) / f"workbox-{hash_part}.js")


@router.get("/{full_path:path}")
def frontend_app(full_path: str) -> FileResponse:
    from .config import settings

    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    frontend_dist_dir = Path(settings.frontend_dist_dir)
    index_path = frontend_dist_dir / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="前端资源未构建")

    if full_path and full_path != "index.html":
        requested_path = (frontend_dist_dir / full_path).resolve()
        base_path = frontend_dist_dir.resolve()
        if requested_path.is_file() and base_path in requested_path.parents:
            return FileResponse(requested_path)

    return FileResponse(index_path)
