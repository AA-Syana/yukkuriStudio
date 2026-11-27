import os

# app を import する前に、DBをSQLiteへ向ける(PostgreSQLドライバ無しでもテストできるようにする)
os.environ["DATABASE_URL"] = "sqlite://"

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.api.deps import get_providers, get_session_factory, get_storage  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.registry import build_providers  # noqa: E402
from app.services import auth_service  # noqa: E402
from app.storage.local import LocalStorage  # noqa: E402

PASSWORD = "password123"


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    auth_service.throttle.clear_all()
    yield
    auth_service.throttle.clear_all()


@pytest.fixture
def providers():
    """全てモック。テストで個別の動作(失敗など)に差し替えたいときは monkeypatch で上書きする。"""
    return build_providers()


@pytest.fixture
def env(tmp_path, providers):
    """テスト用のDB・ストレージ。外部キー制約を有効にする(PostgreSQLと同じく、削除順の誤りをテストで検出するため)。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

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
    app.dependency_overrides[get_providers] = lambda: providers
    # バックグラウンドジョブも同じテスト用DBを使う(TestClientはレスポンス前にバックグラウンド処理を完了させる)
    app.dependency_overrides[get_session_factory] = lambda: Session
    yield SimpleNamespace(Session=Session, storage=storage)
    app.dependency_overrides.clear()


@pytest.fixture
def storage(env):
    return env.storage


@pytest.fixture
def Session(env):
    return env.Session


@pytest.fixture
def make_client(env):
    """登録・ログイン済みのクライアントを作る。クライアントごとにCookieが別なので、別ユーザーとして操作できる。"""

    def _make(email: str) -> TestClient:
        c = TestClient(app)  # with を使わない → lifespan(本番DBの確認)は走らない
        res = c.post("/api/auth/register", json={"email": email, "password": PASSWORD})
        assert res.status_code == 201, res.text
        return c

    return _make


@pytest.fixture
def client(make_client):
    return make_client("a@example.com")


@pytest.fixture
def other(make_client):
    """別のユーザー。データの分離(他人のデータが見えない・触れない)の確認に使う。"""
    return make_client("b@example.com")


@pytest.fixture
def anon(env):
    """ログインしていないクライアント。"""
    return TestClient(app)


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"title": "テスト"}).json()


@pytest.fixture
def script(client, project):
    """プロジェクト作成時に用意される最初の台本。"""
    return client.get(f"/api/projects/{project['id']}/scripts").json()[0]
