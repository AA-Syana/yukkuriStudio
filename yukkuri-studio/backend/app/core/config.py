"""環境変数から読み込むアプリ設定。"""
import os
from pathlib import Path


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://yukkuri:yukkuri@localhost:5432/yukkuri"
    )
    storage_dir: Path = Path(os.getenv("STORAGE_DIR", "../storage")).resolve()
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "2048")) * 1024 * 1024


settings = Settings()
