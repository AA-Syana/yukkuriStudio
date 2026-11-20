import os

# app を import する前に、DBをSQLiteへ向ける(PostgreSQLドライバ無しでもテストできるようにする)
os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.api.deps import get_storage  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.storage.local import LocalStorage  # noqa: E402


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    storage = LocalStorage(tmp_path / "storage")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage] = lambda: storage
    yield TestClient(app)  # with を使わない → lifespan(本番DBへのcreate_all)は走らない
    app.dependency_overrides.clear()


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"name": "テスト"}).json()
