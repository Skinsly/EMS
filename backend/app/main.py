from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .frontend_static import register_frontend_static, router as frontend_router
from . import routers_attachments, routers_assets, routers_core, routers_logs, routers_progress, routers_stock
from .dependencies import require_admin as _require_admin
from .startup import cors_origins as _cors_origins, lifespan, resolve_db_path_from_settings as _resolve_db_path


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routers_core.router)
app.include_router(routers_logs.router)
app.include_router(routers_progress.router)
app.include_router(routers_assets.router)
app.include_router(routers_stock.router)
app.include_router(routers_attachments.router)


@app.get("/api/export/database")
def export_database(_: object = Depends(_require_admin)) -> FileResponse:
    db_path = _resolve_db_path()
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="数据库文件不存在")
    return FileResponse(path=str(db_path), filename="app.db", media_type="application/octet-stream")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


register_frontend_static(app, Path(settings.frontend_dist_dir))
app.include_router(frontend_router)
