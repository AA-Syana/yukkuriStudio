from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..constants import MIN_DURATION_MS, TRACK_AUDIO, TRACK_CHARACTER, TRACK_SUBTITLE
from ..core.database import get_db
from ..models import Dialogue, Project, Script, TimelineItem
from ..schemas import HistoryStateOut, LayoutOut, LayoutRequest, TimelineItemOut, TimelineItemUpdate, TimelineOut
from ..services import history, timing
from ..services.timing_plan import audio_item_end_ms
from .deps import get_project_or_404, get_script_or_404, get_timeline_item_or_404

router = APIRouter(tags=["timeline"])

# 各トラックで意味のある編集項目(それ以外が送られたら422にして、効かない設定を黙って受け付けない)
ALLOWED_FIELDS = {
    TRACK_AUDIO: {"start_ms", "end_ms", "volume", "playback_speed"},
    TRACK_CHARACTER: {"start_ms", "end_ms", "position_x", "position_y", "scale", "expression"},
    TRACK_SUBTITLE: {"start_ms", "end_ms", "position_x", "position_y", "font_size", "text_override"},
}
NOT_NULLABLE = {"start_ms", "end_ms", "position_x", "position_y", "scale", "volume", "playback_speed"}
LABELS = {
    TRACK_AUDIO: "音声の編集", TRACK_CHARACTER: "立ち絵の編集", TRACK_SUBTITLE: "字幕の編集",
}


@router.post("/api/scripts/{script_id}/layout", response_model=LayoutOut)
def layout_script(body: LayoutRequest, script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)):
    """セリフの時間を自動配置し、字幕・立ち絵・音声のタイムライン項目へ反映する。

    手動で時間を指定したセリフ・項目は、overwrite_locked=true でない限り動かさない。
    """
    before = history.snapshot_dialogues(db, list(script.dialogues))
    timing.apply_layout(db, script, body.gap_ms, body.start_ms, body.overwrite_locked)
    after = history.snapshot_dialogues(db, list(script.dialogues))
    history.record(db, script.project_id, "layout", "タイミングの自動配置", before, after)
    db.commit()
    db.refresh(script)
    return {"dialogues": script.dialogues, "timeline": timing.build_timeline(db, script)}


@router.get("/api/scripts/{script_id}/timeline", response_model=TimelineOut)
def get_timeline(script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)):
    return timing.build_timeline(db, script)


@router.put("/api/timeline-items/{item_id}", response_model=TimelineItemOut)
def update_timeline_item(
    body: TimelineItemUpdate, item: TimelineItem = Depends(get_timeline_item_or_404), db: Session = Depends(get_db)
):
    """タイムライン項目(音声・立ち絵・字幕のどれか1つ)を編集する。送った項目だけを更新する。"""
    changes = body.model_dump(exclude_unset=True)
    for key in [k for k in changes if k in NOT_NULLABLE and changes[k] is None]:
        changes.pop(key)  # NULLにできない項目にnullが来たら無視する
    not_for_track = sorted(set(changes) - ALLOWED_FIELDS[item.track_type])
    if not_for_track:
        raise HTTPException(422, f"この項目({item.track_type})では変更できない設定です: {', '.join(not_for_track)}")

    dialogue: Dialogue = db.get(Dialogue, item.dialogue_id)
    before = history.snapshot_dialogues(db, [dialogue])
    for key, value in changes.items():
        setattr(item, key, value)
    if "start_ms" in changes or "end_ms" in changes:
        item.times_edited = True  # 手で決めた時間は、自動配置で動かさない
    if (
        item.track_type == TRACK_AUDIO and "playback_speed" in changes and "end_ms" not in changes
        and dialogue.audio_duration_ms is not None
    ):
        item.end_ms = audio_item_end_ms(item.start_ms, dialogue.audio_duration_ms, item.playback_speed)
    if item.end_ms - item.start_ms < MIN_DURATION_MS:
        raise HTTPException(422, f"表示時間は{MIN_DURATION_MS}ms以上にしてください(終了は開始より後にしてください)")
    dialogue.is_user_edited = True  # 台本の再分割で、手動編集の警告が出るようにする
    after = history.snapshot_dialogues(db, [dialogue])
    history.record(db, dialogue.script.project_id, f"item:{item.track_type}", LABELS[item.track_type], before, after)
    db.commit()
    db.refresh(item)
    return timing.item_to_dict(item, dialogue)


@router.get("/api/projects/{project_id}/history", response_model=HistoryStateOut)
def get_history(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return history.state(db, project.id)


def _undo_redo(project: Project, db: Session, undo: bool) -> dict:
    try:
        (history.undo if undo else history.redo)(db, project.id)
    except history.HistoryError as e:
        db.commit()  # 使えない履歴を捨てた場合は、その削除を残す
        raise HTTPException(409, str(e))
    db.commit()
    return history.state(db, project.id)


@router.post("/api/projects/{project_id}/history/undo", response_model=HistoryStateOut)
def undo_edit(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return _undo_redo(project, db, True)


@router.post("/api/projects/{project_id}/history/redo", response_model=HistoryStateOut)
def redo_edit(project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return _undo_redo(project, db, False)
