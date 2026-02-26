import os
from pathlib import Path


class Settings:
    app_name: str = "Material Stock System"
    secret_key: str = os.getenv("SECRET_KEY", "change-this-in-production")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
    idempotency_ttl_hours: int = int(os.getenv("IDEMPOTENCY_TTL_HOURS", "168"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    data_dir: str = os.getenv("DATA_DIR", "data")
    db_path: str = os.getenv("DB_PATH", "app.db")
    uploads_dir: str = os.getenv("UPLOADS_DIR", "uploads")
    frontend_dist_dir: str = os.getenv("FRONTEND_DIST_DIR", "frontend-dist")
    deleted_attachment_retention_days: int = int(os.getenv("DELETED_ATTACHMENT_RETENTION_DAYS", "30"))

    @property
    def database_url(self) -> str:
        db_path = Path(self.db_path)
        if not db_path.is_absolute():
            db_path = Path(self.data_dir) / db_path
        return f"sqlite:///{db_path.as_posix()}"


settings = Settings()
