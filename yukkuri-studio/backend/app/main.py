from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (テーブル定義を読み込む)
from .api import assets, auth, characters, dialogues, generation, projects, render, scripts, timeline, videos
from .core.config import settings
from .core.database import SessionLocal, engine
from .services.jobs import fail_interrupted_jobs

BACKEND_DIR = Path(__file__).resolve().parents[1]


def ensure_schema_ready() -> None:
    """DBが最新のマイグレーションまで適用済みかを確認する。未適用のまま動かすと実行時に分かりにくいエラーになるため、起動時に止める。"""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise RuntimeError(
            "データベースのスキーマが最新ではありません"
            f"(適用済み: {current or 'なし'} / 必要: {head})。"
            "backend フォルダで `alembic upgrade head` を実行してください。"
            "Phase 2 以前のDBを使っていた場合は、DBを作り直す必要があります(README参照)。"
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    ensure_schema_ready()
    with SessionLocal() as db:
        fail_interrupted_jobs(db)  # 前回の終了時に実行中だったジョブを、再実行できる状態にする
    yield


app = FastAPI(title="AI Yukkuri Studio API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Cookieを使うため "*" は使えない。許可するオリジンを明示する
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, projects, scripts, dialogues, characters, assets, generation, render, timeline, videos):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
