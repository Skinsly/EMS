import os
import secrets
import warnings
from pathlib import Path


class Settings:
    app_name: str = "Material Stock System"
    secret_key: str
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
    idempotency_ttl_hours: int = int(os.getenv("IDEMPOTENCY_TTL_HOURS", "168"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    data_dir: str = os.getenv("DATA_DIR", "data")
    db_path: str = os.getenv("DB_PATH", "app.db")
    uploads_dir: str = os.getenv("UPLOADS_DIR", "uploads")
    frontend_dist_dir: str = os.getenv("FRONTEND_DIST_DIR", "frontend-dist")
    deleted_attachment_retention_days: int = int(os.getenv("DELETED_ATTACHMENT_RETENTION_DAYS", "30"))

    def __init__(self) -> None:
        env_secret = os.getenv("SECRET_KEY")
        if env_secret:
            self.secret_key = env_secret
            return

        data_dir = Path(self.data_dir)
        secret_file = data_dir / ".secret_key"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            if secret_file.exists():
                persisted_secret = secret_file.read_text(encoding="utf-8").strip()
                if persisted_secret:
                    self.secret_key = persisted_secret
                    warnings.warn(
                        f"[安全提示] 未设置 SECRET_KEY，已复用 {secret_file} 中的本地密钥。生产环境请设置固定强密钥。",
                        stacklevel=2,
                    )
                    return

            self.secret_key = secrets.token_urlsafe(48)
            secret_file.write_text(self.secret_key, encoding="utf-8")
            warnings.warn(
                f"[安全提示] 未设置 SECRET_KEY，已生成并保存到 {secret_file}。生产环境请设置固定强密钥。",
                stacklevel=2,
            )
        except OSError:
            self.secret_key = secrets.token_urlsafe(48)
            warnings.warn(
                "[安全警告] 未设置 SECRET_KEY 且本地密钥文件不可用，当前使用启动时随机密钥。重启后登录状态会失效；生产环境请务必设置固定强密钥。",
                stacklevel=2,
            )

    @property
    def database_url(self) -> str:
        db_path = Path(self.db_path)
        if not db_path.is_absolute():
            db_path = Path(self.data_dir) / db_path
        return f"sqlite:///{db_path.as_posix()}"


settings = Settings()
