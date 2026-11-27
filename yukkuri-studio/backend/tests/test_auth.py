from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.core.config import settings
from app.models import User, UserSession

from conftest import PASSWORD


def _register(c, email="u@example.com", password=PASSWORD):
    return c.post("/api/auth/register", json={"email": email, "password": password})


def test_register_logs_in_and_me_works(anon):
    res = _register(anon, "  User@Example.com ")
    assert res.status_code == 201
    assert res.json()["email"] == "user@example.com"  # 前後の空白除去・小文字化
    assert "password" not in res.text
    assert anon.get("/api/auth/me").json()["email"] == "user@example.com"


def test_session_cookie_flags(anon):
    cookie = _register(anon).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie  # COOKIE_SECURE が false(開発用)の既定


def test_cookie_is_secure_when_configured(anon, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    assert "secure" in _register(anon).headers["set-cookie"].lower()


def test_password_is_stored_hashed(anon, Session):
    _register(anon)
    with Session() as db:
        user = db.query(User).one()
        assert PASSWORD not in user.password_hash and user.password_hash.startswith("$argon2")
        # セッションにはトークンそのものではなくハッシュだけを保存する
        token = anon.cookies.get(settings.session_cookie_name)
        assert db.query(UserSession).one().token_hash != token


def test_duplicate_email_is_rejected_case_insensitively(anon, make_client):
    make_client("dup@example.com")
    assert _register(anon, "DUP@example.com").status_code == 409


@pytest.mark.parametrize(
    "email,password",
    [("not-an-email", PASSWORD), ("a@b", PASSWORD), ("ok@example.com", "short"), ("ok@example.com", "x" * 129)],
)
def test_register_validation(anon, email, password):
    assert _register(anon, email, password).status_code == 422


def test_registration_can_be_closed(anon, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)
    assert _register(anon).status_code == 403


def test_login_and_wrong_credentials_look_identical(anon, make_client):
    make_client("known@example.com")
    wrong_pw = anon.post("/api/auth/login", json={"email": "known@example.com", "password": "wrong-password"})
    no_user = anon.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()  # アカウントの有無を推測させない
    assert anon.get("/api/auth/me").status_code == 401

    ok = anon.post("/api/auth/login", json={"email": "KNOWN@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and anon.get("/api/auth/me").status_code == 200


def test_login_is_throttled_after_repeated_failures(anon, make_client):
    make_client("t@example.com")
    for _ in range(settings.login_max_failures):
        assert anon.post("/api/auth/login", json={"email": "t@example.com", "password": "bad-password"}).status_code == 401
    # 回数を超えたら、正しいパスワードでも一時的に受け付けない
    res = anon.post("/api/auth/login", json={"email": "t@example.com", "password": PASSWORD})
    assert res.status_code == 429 and int(res.headers["retry-after"]) > 0


def test_successful_login_resets_failure_count(anon, make_client):
    make_client("r@example.com")
    for _ in range(settings.login_max_failures - 1):
        anon.post("/api/auth/login", json={"email": "r@example.com", "password": "bad-password"})
    assert anon.post("/api/auth/login", json={"email": "r@example.com", "password": PASSWORD}).status_code == 200
    assert anon.post("/api/auth/login", json={"email": "r@example.com", "password": "bad-password"}).status_code == 401


def test_logout_invalidates_the_session_on_the_server(client):
    token = client.cookies.get(settings.session_cookie_name)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    # Cookieを手元に残して再送しても、サーバー側で無効になっている
    client.cookies.set(settings.session_cookie_name, token)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client, Session):
    with Session() as db:
        db.execute(update(UserSession).values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_garbage_cookie_is_rejected(anon):
    anon.cookies.set(settings.session_cookie_name, "garbage")
    assert anon.get("/api/auth/me").status_code == 401


PROTECTED = [
    ("GET", "/api/projects"), ("POST", "/api/projects"), ("GET", "/api/projects/x"), ("PUT", "/api/projects/x"),
    ("DELETE", "/api/projects/x"), ("GET", "/api/projects/x/scripts"), ("POST", "/api/projects/x/scripts"),
    ("GET", "/api/scripts/x"), ("PUT", "/api/scripts/x"), ("DELETE", "/api/scripts/x"), ("POST", "/api/scripts/x/parse"),
    ("GET", "/api/scripts/x/dialogues"), ("POST", "/api/scripts/x/dialogues"), ("PUT", "/api/dialogues/x"),
    ("DELETE", "/api/dialogues/x"), ("POST", "/api/scripts/x/dialogues/group"), ("POST", "/api/scripts/x/dialogues/ungroup"),
    ("GET", "/api/scripts/x/unknown-speakers"), ("POST", "/api/scripts/x/layout"), ("GET", "/api/scripts/x/timeline"),
    ("PUT", "/api/timeline-items/x"), ("GET", "/api/projects/x/history"), ("POST", "/api/projects/x/history/undo"),
    ("POST", "/api/projects/x/history/redo"), ("POST", "/api/projects/x/render"),
    ("GET", "/api/projects/x/render-status"), ("GET", "/api/projects/x/download"),
    ("GET", "/api/characters"), ("POST", "/api/characters"), ("GET", "/api/characters/x"), ("PUT", "/api/characters/x"),
    ("DELETE", "/api/characters/x"), ("GET", "/api/projects/x/characters"), ("POST", "/api/projects/x/characters"),
    ("PUT", "/api/projects/x/characters/y"), ("DELETE", "/api/projects/x/characters/y"),
    ("POST", "/api/characters/x/images/upload"), ("DELETE", "/api/characters/x/images/y"),
    ("GET", "/api/assets/x/file"), ("POST", "/api/dialogues/x/regenerate"), ("POST", "/api/projects/x/generate"),
    ("POST", "/api/scripts/x/analyze"), ("POST", "/api/characters/x/generate-image"),
    ("POST", "/api/characters/x/generate-voice"), ("GET", "/api/generation-jobs"), ("GET", "/api/generation-jobs/x"),
    ("POST", "/api/generation-jobs/x/retry"), ("GET", "/api/projects/x/video"), ("GET", "/api/projects/x/video/stream"),
    ("POST", "/api/projects/x/video"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_data_endpoint_requires_login(anon, method, path):
    assert anon.request(method, path).status_code == 401, f"{method} {path} がログインなしで通ってしまう"


def test_all_routes_are_covered_by_the_login_list(anon):
    """APIにルートを足したのに、ログイン必須のテスト一覧(PROTECTED)へ追加し忘れていないか。"""
    import re

    from app.main import app

    public = {"/api/health", "/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/auth/me"}

    def shape(path: str) -> str:
        path = re.sub(r"\{[^}]+\}", "*", path)  # {project_id} など
        return "/".join("*" if seg in ("x", "y") else seg for seg in path.split("/"))  # 一覧側のダミーID

    covered = {(m, shape(p)) for m, p in PROTECTED}
    missing = []
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/") or path in public:
            continue
        for method in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
            if (method, shape(path)) not in covered:
                missing.append(f"{method} {path}")
    assert not missing, f"ログイン必須のテスト一覧に無いルート: {missing}"
