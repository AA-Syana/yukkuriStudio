"""環境変数から読み込むアプリ設定。(.env ファイルは読み込まない。値は環境変数で渡す)"""
import os
from pathlib import Path


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://yukkuri:yukkuri@localhost:5432/yukkuri"
    )
    storage_dir: Path = Path(os.getenv("STORAGE_DIR", "../storage")).resolve()
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "2048")) * 1024 * 1024

    # AIエンジンの選択。実APIのプロバイダーを追加したら、ここで切り替える(例: VOICE_PROVIDER=voicevox)
    voice_provider: str = os.getenv("VOICE_PROVIDER", "mock")
    image_provider: str = os.getenv("IMAGE_PROVIDER", "mock")
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")

    # MP4書き出し(Phase 5)
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    render_font_path: str = os.getenv("RENDER_FONT_PATH", "")  # 字幕用の日本語フォント。空なら自動で探す

    # 認証
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "yukkuri_session")
    session_days: int = int(os.getenv("SESSION_DAYS", "14"))
    cookie_secure: bool = _flag("COOKIE_SECURE", False)  # HTTPSで公開するときは true にする
    allow_registration: bool = _flag("ALLOW_REGISTRATION", True)
    login_max_failures: int = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
    login_window_seconds: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "600"))


settings = Settings()
