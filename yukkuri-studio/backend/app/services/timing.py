"""タイミング配置(Phase 3)。セリフの開始/終了時間を決め、タイムライン項目(音声・立ち絵・字幕)へ反映する。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import TRACK_AUDIO, TRACK_CHARACTER, TRACK_SUBTITLE
from ..models import Dialogue, Script, TimelineItem
from .timing_plan import PlanInput, audio_item_end_ms, estimate_duration_ms, plan_layout

# 新しく作る項目の初期位置(画面に対する割合、項目の中心)
SUBTITLE_POSITION = (0.5, 0.9)
CHARACTER_Y = 0.6


def _character_x(script: Script, character_id: str) -> float:
    """立ち絵の初期のx位置。プロジェクトのキャラクターを左から均等に並べる。"""
    ids = [c.id for c in script.project.characters]
    if character_id not in ids:
        return 0.5
    return (ids.index(character_id) + 1) / (len(ids) + 1)


def _plan_input(d: Dialogue) -> PlanInput:
    audio = d.audio_duration_ms
    return PlanInput(
        id=d.id,
        order_index=d.order_index,
        duration_ms=audio if audio is not None else estimate_duration_ms(d.text),
        estimated=audio is None,
        group=d.simultaneous_group,
        locked=d.timing_locked,
        start_ms=d.start_ms,
        end_ms=d.end_ms,
    )


def sync_dialogue_items(
    db: Session, script: Script, dialogues: list[Dialogue], reset_edited: bool = False
) -> None:
    """セリフの時間に合わせて、タイムライン項目を作成・更新・削除する。

    位置・拡大率・音量・字幕設定などはユーザーの値を残す。開始/終了を手で変えた項目(times_edited)の時間も動かさない
    (reset_edited=True のときだけ、その印を外して振り直す)。音声項目の長さは、再生速度を反映する。
    """
    if not dialogues:
        return
    existing = {
        (i.dialogue_id, i.track_type): i
        for i in db.scalars(select(TimelineItem).where(TimelineItem.dialogue_id.in_([d.id for d in dialogues])))
    }
    for d in dialogues:
        wanted: dict[str, tuple[float, float]] = {}
        if d.start_ms is not None and d.end_ms is not None:
            if d.audio_asset is not None:
                wanted[TRACK_AUDIO] = (0.0, 0.0)
            if d.character_id is not None:
                wanted[TRACK_CHARACTER] = (_character_x(script, d.character_id), CHARACTER_Y)
            wanted[TRACK_SUBTITLE] = SUBTITLE_POSITION
        for track in (TRACK_AUDIO, TRACK_CHARACTER, TRACK_SUBTITLE):
            item = existing.get((d.id, track))
            if track not in wanted:
                if item is not None:
                    db.delete(item)
                continue
            if item is None:
                x, y = wanted[track]
                item = TimelineItem(project_id=script.project_id, dialogue_id=d.id, track_type=track,
                                    position_x=x, position_y=y, scale=1.0, volume=1.0, playback_speed=1.0,
                                    times_edited=False)
                db.add(item)
            elif reset_edited:
                item.times_edited = False
            if item.times_edited:
                continue
            item.start_ms, item.end_ms = d.start_ms, d.end_ms
            if track == TRACK_AUDIO and d.audio_duration_ms is not None:
                item.end_ms = audio_item_end_ms(d.start_ms, d.audio_duration_ms, item.playback_speed or 1.0)


def apply_layout(
    db: Session, script: Script, gap_ms: int, start_ms: int, overwrite_locked: bool
) -> int:
    """台本の全セリフの時間を自動配置して保存する。戻り値は「長さを見積もったセリフの数」。"""
    dialogues = list(script.dialogues)
    placements = {p.id: p for p in plan_layout(
        [_plan_input(d) for d in dialogues], gap_ms=gap_ms, start_ms=start_ms, overwrite_locked=overwrite_locked
    )}
    for d in dialogues:
        p = placements[d.id]
        d.start_ms, d.end_ms = p.start_ms, p.end_ms
        if overwrite_locked:
            d.timing_locked = False
    sync_dialogue_items(db, script, dialogues, reset_edited=overwrite_locked)
    db.flush()
    return sum(1 for p in placements.values() if p.estimated)


def item_to_dict(i: TimelineItem, d: Dialogue) -> dict:
    return {
        "id": i.id, "dialogue_id": i.dialogue_id, "track_type": i.track_type,
        "start_ms": i.start_ms, "end_ms": i.end_ms,
        "position_x": i.position_x, "position_y": i.position_y, "scale": i.scale,
        "volume": i.volume, "playback_speed": i.playback_speed,
        "font_size": i.font_size, "expression": i.expression, "text_override": i.text_override,
        "times_edited": i.times_edited,
        "text": d.text, "speaker_name": d.speaker_name, "character_id": d.character_id, "emotion": d.emotion,
        "audio_asset_id": d.audio_asset_id, "audio_duration_ms": d.audio_duration_ms,
    }


def build_timeline(db: Session, script: Script) -> dict:
    dialogues = {d.id: d for d in script.dialogues}
    items = []
    if dialogues:
        rows = db.scalars(select(TimelineItem).where(TimelineItem.dialogue_id.in_(list(dialogues))))
        items = sorted(rows, key=lambda i: (i.start_ms, dialogues[i.dialogue_id].order_index, i.track_type))
    out = [item_to_dict(i, dialogues[i.dialogue_id]) for i in items]
    total = max((i["end_ms"] for i in out), default=0)

    warnings: list[str] = []
    unplaced = sum(1 for d in dialogues.values() if d.start_ms is None or d.end_ms is None)
    if unplaced:
        warnings.append(f"{unplaced}件のセリフは時間が未配置です。「タイミングを自動配置」を実行してください。")
    estimated = sum(1 for d in dialogues.values() if d.audio_asset is None)
    if estimated:
        warnings.append(f"{estimated}件のセリフは音声が未生成のため、文字数から長さを見積もっています。音声生成後に再配置してください。")
    stale_audio = sum(1 for d in dialogues.values() if d.audio_stale)
    if stale_audio:
        warnings.append(f"{stale_audio}件のセリフは音声が古い(セリフ・感情・声の設定が変更済み)ため、再生成が必要です。")
    mismatch = sum(1 for d in dialogues.values() if d.timing_stale and d.start_ms is not None)
    if mismatch:
        warnings.append(f"{mismatch}件のセリフは音声の長さと配置がずれています。再配置すると揃います。")
    video = script.project.video
    if video is not None and total > video.duration_ms:
        warnings.append(f"配置の終わり({total}ms)が元動画の長さ({video.duration_ms}ms)を超えています。")
    return {"script_id": script.id, "total_ms": total, "items": out, "warnings": warnings}
