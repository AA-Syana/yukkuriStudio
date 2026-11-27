"""キャラクターのAPI。

  ライブラリ(キャラクター管理画面): /api/characters
  プロジェクト用のコピー(台本の編集画面): /api/projects/{project_id}/characters

プロジェクトへ追加した時点でライブラリの内容がコピーされ、以降は別物になる。
ライブラリを編集・削除しても、すでに追加済みのコピーには影響しない。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.database import get_db
from ..models import Character, Project, User
from ..schemas import CharacterCreate, CharacterOut, CharacterUpdate, ProjectCharacterAdd
from ..services import character_service as svc
from ..storage.local import LocalStorage
from .deps import (
    get_current_user, get_library_character_or_404, get_project_character_or_404, get_project_or_404, get_storage,
)

router = APIRouter(tags=["characters"])

NAME_CONFLICT_LIBRARY = "同じ名前のキャラクターが既にあります"
NAME_CONFLICT_PROJECT = "同じ名前のキャラクターが、このプロジェクトに既にあります"


# ---------------- ライブラリ ----------------
@router.get("/api/characters", response_model=list[CharacterOut])
def list_library(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Character)
        .where(Character.user_id == user.id, Character.project_id.is_(None))
        .options(selectinload(Character.copies))
        .order_by(Character.created_at)
    ).all()


@router.post("/api/characters", response_model=CharacterOut, status_code=201)
def create_library_character(body: CharacterCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return svc.create_library_character(db, user, body.model_dump())
    except svc.NameConflict:
        raise HTTPException(409, NAME_CONFLICT_LIBRARY)


@router.get("/api/characters/{character_id}", response_model=CharacterOut)
def get_library_character(character: Character = Depends(get_library_character_or_404)):
    return character


@router.put("/api/characters/{character_id}", response_model=CharacterOut)
def update_library_character(
    body: CharacterUpdate,
    character: Character = Depends(get_library_character_or_404),
    db: Session = Depends(get_db),
):
    """ライブラリのキャラクターを編集する。すでにプロジェクトへ追加したコピーには反映されない。"""
    try:
        return svc.update_character(db, character, body.model_dump(exclude_unset=True, exclude_none=True))
    except svc.NameConflict:
        raise HTTPException(409, NAME_CONFLICT_LIBRARY)


@router.delete("/api/characters/{character_id}", status_code=204)
def delete_library_character(
    character: Character = Depends(get_library_character_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    """ライブラリから削除する。プロジェクトに追加済みのコピーは残る。"""
    svc.delete_library_character(db, storage, character)


# ---------------- プロジェクト用のコピー ----------------
@router.get("/api/projects/{project_id}/characters", response_model=list[CharacterOut])
def list_project_characters(project: Project = Depends(get_project_or_404)):
    return project.characters


@router.post("/api/projects/{project_id}/characters", response_model=CharacterOut)
def add_character_to_project(
    body: ProjectCharacterAdd,
    project: Project = Depends(get_project_or_404),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    """ライブラリのキャラクターを、現在の内容でコピーしてプロジェクトに追加する(追加済みなら既存のコピーを返す)。"""
    source = db.get(Character, body.source_character_id)
    if source is None or source.user_id != user.id or source.project_id is not None:
        raise HTTPException(404, "ライブラリにキャラクターが見つかりません")
    try:
        copy, _ = svc.add_character_to_project(db, storage, project, source)
    except svc.NameConflict:
        raise HTTPException(409, NAME_CONFLICT_PROJECT)
    return copy


@router.put("/api/projects/{project_id}/characters/{character_id}", response_model=CharacterOut)
def update_project_character(
    body: CharacterUpdate,
    character: Character = Depends(get_project_character_or_404),
    db: Session = Depends(get_db),
):
    """このプロジェクトのキャラクターを編集する。ライブラリや他のプロジェクトには影響しない。"""
    try:
        return svc.update_character(db, character, body.model_dump(exclude_unset=True, exclude_none=True))
    except svc.NameConflict:
        raise HTTPException(409, NAME_CONFLICT_PROJECT)


@router.delete("/api/projects/{project_id}/characters/{character_id}", status_code=204)
def remove_project_character(
    character: Character = Depends(get_project_character_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    """プロジェクトからキャラクターを外す。セリフは残り、話者は「未登録」になる。ライブラリは消えない。"""
    svc.remove_character_from_project(db, storage, character)
