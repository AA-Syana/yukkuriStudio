"""共通の依存関係。ログイン中のユーザーと、そのユーザーが所有するデータの取得。

他人のデータは「存在しない」(404)として扱う。403にすると、IDの存在を推測できてしまうため。
"""
from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import SessionLocal, get_db
from ..models import Asset, Character, Dialogue, GenerationJob, Project, Script, TimelineItem, User
from ..providers.registry import Providers, build_providers
from ..services.auth_service import user_from_token
from ..storage.local import LocalStorage


def get_storage() -> LocalStorage:
    return LocalStorage(settings.storage_dir)


@lru_cache
def _providers() -> Providers:
    return build_providers(settings.voice_provider, settings.image_provider, settings.llm_provider)


def get_providers() -> Providers:
    return _providers()


def get_session_factory() -> Callable[[], Session]:
    """バックグラウンドジョブ用。リクエストとは別のDBセッションを作るために使う。"""
    return SessionLocal


# ---- 認証 ----
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    user = user_from_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "ログインが必要です")
    return user


# ---- 所有者チェック付きの取得 ----
def get_project_or_404(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(404, "プロジェクトが見つかりません")
    return project


def get_script_or_404(script_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Script:
    script = db.get(Script, script_id)
    if script is None or script.project.user_id != user.id:
        raise HTTPException(404, "台本が見つかりません")
    return script


def get_timeline_item_or_404(item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TimelineItem:
    item = db.get(TimelineItem, item_id)
    dialogue = db.get(Dialogue, item.dialogue_id) if item is not None else None
    if item is None or dialogue is None or dialogue.script.project.user_id != user.id:
        raise HTTPException(404, "タイムライン項目が見つかりません")
    return item


def get_dialogue_or_404(dialogue_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Dialogue:
    dialogue = db.get(Dialogue, dialogue_id)
    if dialogue is None or dialogue.script.project.user_id != user.id:
        raise HTTPException(404, "セリフが見つかりません")
    return dialogue


def get_character_or_404(character_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Character:
    """ライブラリ・プロジェクト用コピーのどちらでも、自分のキャラクターなら取得できる(画像や音声の生成用)。"""
    character = db.get(Character, character_id)
    if character is None or character.user_id != user.id:
        raise HTTPException(404, "キャラクターが見つかりません")
    return character


def get_library_character_or_404(character: Character = Depends(get_character_or_404)) -> Character:
    """ライブラリのキャラクターだけ(キャラクター管理画面のAPI用)。"""
    if character.project_id is not None:
        raise HTTPException(404, "キャラクターが見つかりません")
    return character


def get_project_character_or_404(character_id: str, project: Project = Depends(get_project_or_404)) -> Character:
    character = next((c for c in project.characters if c.id == character_id), None)
    if character is None:
        raise HTTPException(404, "キャラクターが見つかりません")
    return character


def get_asset_or_404(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    owner_id = None
    if asset is not None:
        if asset.dialogue_id:
            d = db.get(Dialogue, asset.dialogue_id)
            owner_id = d.script.project.user_id if d else None
        elif asset.character_id:
            c = db.get(Character, asset.character_id)
            owner_id = c.user_id if c else None
    if asset is None or owner_id != user.id:
        raise HTTPException(404, "ファイルが見つかりません")
    return asset


def get_job_or_404(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "ジョブが見つかりません")
    return job
