"""パスワードのハッシュ化と、セッショントークンの生成。"""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# ユーザーが存在しないときも同じ時間をかけて検証し、メールの登録有無を応答時間から推測されにくくする
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        ok = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """DBにはトークンそのものではなくハッシュを保存する(DBが漏れても、そのままセッションに使えない)。"""
    return hashlib.sha256(token.encode()).hexdigest()
