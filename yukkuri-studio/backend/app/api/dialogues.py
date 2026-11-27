from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Dialogue, Script, new_id
from ..schemas import DialogueCreate, DialogueIds, DialogueOut, DialogueUpdate, UnknownSpeakerOut
from ..services.script_service import unknown_speakers_of
from ..services.history import record, snapshot_dialogues
from ..services.timing import sync_dialogue_items
from ..storage.local import LocalStorage
from .deps import get_dialogue_or_404, get_script_or_404, get_storage

router = APIRouter(tags=["dialogues"])


def _ensure_character(script: Script, character_id: str | None) -> None:
    """話者にできるのは、この台本のプロジェクトに追加済みのキャラクターだけ(ライブラリのものは不可)。"""
    if character_id is not None and all(c.id != character_id for c in script.project.characters):
        raise HTTPException(422, "指定されたキャラクターはこのプロジェクトにありません。先にプロジェクトへ追加してください")


def _get_many(script: Script, ids: list[str], db: Session) -> list[Dialogue]:
    unique = set(ids)
    rows = db.scalars(select(Dialogue).where(Dialogue.id.in_(unique), Dialogue.script_id == script.id)).all()
    if len(rows) != len(unique):
        raise HTTPException(404, "存在しないセリフが含まれています")
    return list(rows)


@router.get("/api/scripts/{script_id}/dialogues", response_model=list[DialogueOut])
def list_dialogues(script: Script = Depends(get_script_or_404)):
    return script.dialogues


@router.get("/api/scripts/{script_id}/unknown-speakers", response_model=list[UnknownSpeakerOut])
def list_unknown_speakers(script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)):
    """未登録の話者(警告用)。キャラクターを追加した後に、警告を最新にするために使う。"""
    return unknown_speakers_of(db, script)


@router.post("/api/scripts/{script_id}/dialogues", response_model=DialogueOut, status_code=201)
def create_dialogue(body: DialogueCreate, script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)):
    _ensure_character(script, body.character_id)
    character = next((c for c in script.project.characters if c.id == body.character_id), None)
    next_index = max((d.order_index for d in script.dialogues), default=-1) + 1
    dialogue = Dialogue(
        script_id=script.id,
        order_index=next_index,
        is_user_edited=True,
        speaker_name=character.name if character else None,
        **body.model_dump(),
    )
    db.add(dialogue)
    db.commit()
    db.refresh(dialogue)
    return dialogue


# 固定パス(/group, /ungroup)は /{dialogue_id} 系より先に定義する
@router.post("/api/scripts/{script_id}/dialogues/group", response_model=list[DialogueOut])
def group_dialogues(
    body: DialogueIds, script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)
):
    """選択したセリフを「同時会話」としてまとめる(同じ simultaneous_group を付与)。"""
    if len(set(body.dialogue_ids)) < 2:
        raise HTTPException(422, "同時会話にするには2つ以上のセリフを選択してください")
    items = _get_many(script, body.dialogue_ids, db)
    group_id = new_id()
    for d in items:
        d.simultaneous_group = group_id
        d.is_user_edited = True
    db.commit()
    return items


@router.post("/api/scripts/{script_id}/dialogues/ungroup", response_model=list[DialogueOut])
def ungroup_dialogues(
    body: DialogueIds, script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)
):
    items = _get_many(script, body.dialogue_ids, db)
    for d in items:
        d.simultaneous_group = None
    db.commit()
    return items


@router.put("/api/dialogues/{dialogue_id}", response_model=DialogueOut)
def update_dialogue(
    body: DialogueUpdate, dialogue: Dialogue = Depends(get_dialogue_or_404), db: Session = Depends(get_db)
):
    """送られた項目だけを更新する(部分更新)。"""
    changes = body.model_dump(exclude_unset=True)
    for key in ("text", "emotion"):  # NULLにできない項目にnullが来たら無視する
        if key in changes and changes[key] is None:
            changes.pop(key)
    if "character_id" in changes:
        _ensure_character(dialogue.script, changes["character_id"])
        character = next((c for c in dialogue.script.project.characters if c.id == changes["character_id"]), None)
        dialogue.speaker_name = character.name if character else dialogue.speaker_name
    has_start, has_end = changes.get("start_ms") is not None, changes.get("end_ms") is not None
    if has_start != has_end:
        raise HTTPException(422, "開始時間と終了時間は両方いっしょに指定してください")
    timing_edit = has_start or "timing_locked" in changes
    before = snapshot_dialogues(db, [dialogue]) if timing_edit else None  # 元に戻す用(変更前の状態)
    for key, value in changes.items():
        setattr(dialogue, key, value)
    if has_start:
        dialogue.timing_locked = True  # 時間を手で決めたので、自動配置で動かさない
    if dialogue.start_ms is not None and dialogue.end_ms is not None and dialogue.end_ms < dialogue.start_ms:
        raise HTTPException(422, "終了時間は開始時間以降にしてください")
    if has_start or "character_id" in changes:
        sync_dialogue_items(db, dialogue.script, [dialogue])
    if before is not None:
        record(db, dialogue.script.project_id, "dialogue:timing", "セリフの時間の変更", before,
               snapshot_dialogues(db, [dialogue]))
    if "text" in changes:
        dialogue.suggestion_row = None  # セリフが変わったので、古い改善案は破棄する
    dialogue.is_user_edited = True  # 手動編集の印。再解析で勝手に上書きされない
    db.commit()
    db.refresh(dialogue)  # 話者変更後の audio_stale などを正しく返すため
    return dialogue


@router.delete("/api/dialogues/{dialogue_id}", status_code=204)
def delete_dialogue(
    dialogue: Dialogue = Depends(get_dialogue_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    files = [a.file_path for a in dialogue.assets if a.file_path]
    db.delete(dialogue)
    db.commit()
    for path in files:  # DB削除が成功してから、音声ファイルを消す
        storage.delete(path)
