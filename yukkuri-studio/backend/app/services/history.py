"""編集履歴(元に戻す/やり直し)。

1回の編集で影響を受けたセリフについて、「セリフの時間 + そのセリフの全タイムライン項目」を丸ごと記録する。
元に戻す = 編集前の記録で上書き、やり直し = 編集後の記録で上書き。編集の種類ごとの逆操作を作らなくて済む。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import HISTORY_LIMIT
from ..models import Dialogue, EditHistory, TimelineItem
from .timing_plan import pick_redo, pick_undo

ITEM_FIELDS = (
    "id", "track_type", "start_ms", "end_ms", "position_x", "position_y", "scale", "volume",
    "playback_speed", "font_size", "expression", "text_override", "times_edited",
)


class HistoryError(Exception):
    pass


def _items_of(db: Session, dialogue_ids: list[str]) -> dict[str, list[TimelineItem]]:
    out: dict[str, list[TimelineItem]] = {i: [] for i in dialogue_ids}
    if dialogue_ids:
        for item in db.scalars(select(TimelineItem).where(TimelineItem.dialogue_id.in_(dialogue_ids))):
            out[item.dialogue_id].append(item)
    return out


def snapshot_dialogues(db: Session, dialogues: list[Dialogue]) -> dict:
    db.flush()  # 直前の変更を、項目の読み込みに反映させる
    items = _items_of(db, [d.id for d in dialogues])
    return {
        "dialogues": [
            {
                "id": d.id,
                "start_ms": d.start_ms,
                "end_ms": d.end_ms,
                "timing_locked": d.timing_locked,
                "items": [{f: getattr(i, f) for f in ITEM_FIELDS} for i in sorted(items[d.id], key=lambda x: x.track_type)],
            }
            for d in dialogues
        ]
    }


def record(db: Session, project_id: str, operation_type: str, label: str, before: dict, after: dict) -> None:
    """履歴を1件追加する。やり直し待ちの履歴は破棄し、古い履歴は上限を超えた分を消す。変化が無い操作は記録しない。"""
    if before == after or not before.get("dialogues"):
        return
    rows = list(db.scalars(select(EditHistory).where(EditHistory.project_id == project_id).order_by(EditHistory.seq)))
    for r in rows:
        if r.undone:
            db.delete(r)
    live = [r for r in rows if not r.undone]
    next_seq = max((r.seq for r in rows), default=0) + 1
    db.add(EditHistory(
        project_id=project_id, operation_type=operation_type, seq=next_seq, undone=False,
        target_id=None, before_data={**before, "label": label}, after_data={**after, "label": label},
    ))
    for r in live[: max(0, len(live) + 1 - HISTORY_LIMIT)]:
        db.delete(r)


def _restore(db: Session, project_id: str, snap: dict) -> int:
    restored = 0
    for ds in snap.get("dialogues", []):
        d = db.get(Dialogue, ds["id"])
        if d is None or d.script.project_id != project_id:
            continue  # 台本の作り直しなどで、もう存在しないセリフ
        d.start_ms, d.end_ms, d.timing_locked = ds["start_ms"], ds["end_ms"], ds["timing_locked"]
        for item in db.scalars(select(TimelineItem).where(TimelineItem.dialogue_id == d.id)):
            db.delete(item)
        db.flush()  # (dialogue_id, track_type) の一意制約のため、削除を先に反映する
        for it in ds["items"]:
            db.add(TimelineItem(project_id=project_id, dialogue_id=d.id, **it))
        restored += 1
    db.flush()
    return restored


def _rows(db: Session, project_id: str) -> list[EditHistory]:
    return list(db.scalars(select(EditHistory).where(EditHistory.project_id == project_id).order_by(EditHistory.seq)))


def state(db: Session, project_id: str) -> dict:
    rows = _rows(db, project_id)
    entries = [(r.seq, r.undone) for r in rows]
    by_seq = {r.seq: r for r in rows}
    u, r = pick_undo(entries), pick_redo(entries)
    return {
        "can_undo": u is not None,
        "can_redo": r is not None,
        "undo_label": by_seq[u].before_data.get("label") if u is not None else None,
        "redo_label": by_seq[r].after_data.get("label") if r is not None else None,
    }


def _apply(db: Session, project_id: str, undo: bool) -> None:
    rows = _rows(db, project_id)
    entries = [(r.seq, r.undone) for r in rows]
    seq = pick_undo(entries) if undo else pick_redo(entries)
    if seq is None:
        raise HistoryError("元に戻せる操作がありません" if undo else "やり直せる操作がありません")
    row = next(r for r in rows if r.seq == seq)
    if _restore(db, project_id, row.before_data if undo else row.after_data) == 0:
        db.delete(row)  # 対象のセリフがもう無い履歴は、使えないので捨てる
        db.flush()
        raise HistoryError("対象のセリフが見つからないため、この操作は戻せません(台本を作り直した可能性があります)")
    row.undone = undo


def undo(db: Session, project_id: str) -> None:
    _apply(db, project_id, True)


def redo(db: Session, project_id: str) -> None:
    _apply(db, project_id, False)

