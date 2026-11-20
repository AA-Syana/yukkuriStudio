from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Dialogue, Project, new_id
from ..schemas import DialogueCreate, DialogueIds, DialogueOut, DialogueUpdate
from .deps import get_project_or_404

router = APIRouter(prefix="/api/projects/{project_id}/dialogues", tags=["dialogues"])


def _get_dialogue(project: Project, dialogue_id: str, db: Session) -> Dialogue:
    d = db.get(Dialogue, dialogue_id)
    if d is None or d.script_id != project.script.id:
        raise HTTPException(404, "セリフが見つかりません")
    return d


def _ensure_character(project: Project, character_id: str | None) -> None:
    if character_id is not None and all(c.id != character_id for c in project.characters):
        raise HTTPException(422, "指定されたキャラクターはこのプロジェクトにありません")


def _get_many(project: Project, ids: list[str], db: Session) -> list[Dialogue]:
    unique = set(ids)
    rows = db.scalars(
        select(Dialogue).where(Dialogue.id.in_(unique), Dialogue.script_id == project.script.id)
    ).all()
    if len(rows) != len(unique):
        raise HTTPException(404, "存在しないセリフが含まれています")
    return list(rows)


@router.get("", response_model=list[DialogueOut])
def list_dialogues(project: Project = Depends(get_project_or_404)):
    return project.script.dialogues


@router.post("", response_model=DialogueOut, status_code=201)
def create_dialogue(
    body: DialogueCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    _ensure_character(project, body.character_id)
    next_index = max((d.order_index for d in project.script.dialogues), default=-1) + 1
    dialogue = Dialogue(
        script_id=project.script.id,
        order_index=next_index,
        is_user_edited=True,
        **body.model_dump(),
    )
    db.add(dialogue)
    db.commit()
    return dialogue


# 固定パス(/group, /ungroup)は /{dialogue_id} より先に定義する
@router.post("/group", response_model=list[DialogueOut])
def group_dialogues(
    body: DialogueIds,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    """選択したセリフを「同時会話」としてまとめる(同じ simultaneous_group を付与)。"""
    if len(set(body.dialogue_ids)) < 2:
        raise HTTPException(422, "同時会話にするには2つ以上のセリフを選択してください")
    items = _get_many(project, body.dialogue_ids, db)
    group_id = new_id()
    for d in items:
        d.simultaneous_group = group_id
        d.is_user_edited = True
    db.commit()
    return items


@router.post("/ungroup", response_model=list[DialogueOut])
def ungroup_dialogues(
    body: DialogueIds,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    items = _get_many(project, body.dialogue_ids, db)
    for d in items:
        d.simultaneous_group = None
    db.commit()
    return items


@router.patch("/{dialogue_id}", response_model=DialogueOut)
def update_dialogue(
    dialogue_id: str,
    body: DialogueUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    dialogue = _get_dialogue(project, dialogue_id, db)
    changes = body.model_dump(exclude_unset=True)
    if "text" in changes and changes["text"] is None:
        changes.pop("text")
    if "character_id" in changes:
        _ensure_character(project, changes["character_id"])
    for key, value in changes.items():
        setattr(dialogue, key, value)
    if dialogue.start_ms is not None and dialogue.end_ms is not None and dialogue.end_ms < dialogue.start_ms:
        raise HTTPException(422, "終了時間は開始時間以降にしてください")
    dialogue.is_user_edited = True  # 手動編集の印。再解析で勝手に上書きされない
    db.commit()
    return dialogue


@router.delete("/{dialogue_id}", status_code=204)
def delete_dialogue(
    dialogue_id: str,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    db.delete(_get_dialogue(project, dialogue_id, db))
    db.commit()
