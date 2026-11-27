"""ユーザー登録・ログイン・セッション管理。"""
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.security import hash_password, hash_token, new_session_token, verify_password
from ..models import User, UserSession


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    """メール不明・パスワード違いを区別しない(アカウントの存在を推測されないため)。"""


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class LoginThrottle:
    """ログイン失敗の回数制限(メモリ上)。サーバーを再起動するとリセットされ、複数プロセスでは共有されない。
    本番で複数台構成にする場合は Redis 等へ置き換える。"""

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        window = settings.login_window_seconds
        recent = [t for t in self._failures.get(key, []) if now - t < window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) >= settings.login_max_failures:
                raise TooManyAttempts(retry_after=max(1, int(settings.login_window_seconds - (now - recent[0]))))

    def fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._recent(key, now)
            self._failures.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._failures.clear()


throttle = LoginThrottle()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, email: str, password: str) -> User:
    email = normalize_email(email)
    if db.scalar(select(User).where(User.email == email)):
        raise EmailTaken()
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 同時登録の競合
        db.rollback()
        raise EmailTaken()
    return user


def authenticate(db: Session, email: str, password: str, throttle_key: str) -> User:
    throttle.check(throttle_key)
    email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == email))
    # ユーザーが居なくても同じ時間をかけて検証する
    if not verify_password(user.password_hash if user else None, password) or user is None:
        throttle.fail(throttle_key)
        raise InvalidCredentials()
    throttle.reset(throttle_key)
    return user


def create_session(db: Session, user: User) -> str:
    db.execute(delete(UserSession).where(UserSession.expires_at < datetime.now(timezone.utc)))  # 期限切れの掃除
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    return token


def user_from_token(db: Session, token: str) -> User | None:
    row = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if row is None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)  # SQLiteは時刻のtzを保持しない
    if expires < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def end_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()
