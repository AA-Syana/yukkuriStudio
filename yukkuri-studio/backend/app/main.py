from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (テーブル定義を読み込む)
from .api import characters, dialogues, projects, scripts, videos
from .core.config import settings
from .core.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    # Phase 1は開発用に create_all で作成する。スキーマが固まったらAlembicに移行する。
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Yukkuri Studio API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (projects, videos, scripts, dialogues, characters):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
