from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import User
from ..schemas import LoginRequest, RegisterRequest, UserOut
from ..services import auth_service
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name, token,
        max_age=settings.session_days * 86400,
        httponly=True,  # JavaScriptから読めない(XSSでトークンを盗まれにくくする)
        samesite="lax",  # 他サイトからのPOST等にはCookieを付けない(CSRF対策)
        secure=settings.cookie_secure,  # HTTPS公開時は COOKIE_SECURE=true
        path="/",
    )


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{auth_service.normalize_email(email)}"


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(403, "現在、新規登録は受け付けていません")
    try:
        user = auth_service.register_user(db, body.email, body.password)
    except auth_service.EmailTaken:
        raise HTTPException(409, "このメールアドレスは既に登録されています")
    _set_cookie(response, auth_service.create_session(db, user))
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user = auth_service.authenticate(db, body.email, body.password, _throttle_key(request, body.email))
    except auth_service.TooManyAttempts as e:
        raise HTTPException(
            429, "ログインに失敗した回数が多すぎます。しばらくしてからやり直してください",
            headers={"Retry-After": str(e.retry_after)},
        )
    except auth_service.InvalidCredentials:
        raise HTTPException(401, "メールアドレスまたはパスワードが正しくありません")
    _set_cookie(response, auth_service.create_session(db, user))
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        auth_service.end_session(db, token)  # サーバー側でも無効化する
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
