from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Character, Dialogue, Project
from ..schemas import CharacterCreate, CharacterOut, CharacterUpdate
from .deps import get_project_or_404

router = APIRouter(prefix="/api/projects/{project_id}/characters", tags=["characters"])


def _get_character(project: Project, character_id: str) -> Character:
    for c in project.characters:
        if c.id == character_id:
            return c
    raise HTTPException(404, "キャラクターが見つかりません")


def _ensure_unique_name(project: Project, name: str, exclude_id: str | None = None) -> None:
    # シナリオの話者名とキャラクターを名前で対応付けるため、重複は許可しない
    if any(c.name == name and c.id != exclude_id for c in project.characters):
        raise HTTPException(409, f"「{name}」という名前のキャラクターは既に存在します")


@router.get("", response_model=list[CharacterOut])
def list_characters(project: Project = Depends(get_project_or_404)):
    return project.characters


@router.post("", response_model=CharacterOut, status_code=201)
def create_character(
    body: CharacterCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    _ensure_unique_name(project, body.name)
    character = Character(project_id=project.id, **body.model_dump())
    db.add(character)
    db.commit()
    return character


@router.patch("/{character_id}", response_model=CharacterOut)
def update_character(
    character_id: str,
    body: CharacterUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    character = _get_character(project, character_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes:
        _ensure_unique_name(project, changes["name"], exclude_id=character.id)
    for key, value in changes.items():
        setattr(character, key, value)
    db.commit()
    return character


@router.delete("/{character_id}", status_code=204)
def delete_character(
    character_id: str,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    character = _get_character(project, character_id)
    # セリフは消さず、話者を「未指定」に戻す
    db.execute(update(Dialogue).where(Dialogue.character_id == character.id).values(character_id=None))
    db.delete(character)
    db.commit()
