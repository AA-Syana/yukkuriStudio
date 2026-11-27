"""タイミング配置の計算(純粋な関数。DBやWebに依存しないので、単体で確認しやすい)。

規則:
  - セリフを order_index 順に、前のセリフの終わり + gap_ms の位置へ並べる。
  - 長さは「生成済みの音声の長さ」。未生成なら文字数から見積もる(estimated=True)。
  - 同時会話(同じ group のセリフ)は、グループの最初のセリフと同じ開始時間に置く(重ねる)。
    後続の位置は、グループ内で一番遅く終わるセリフの後になる。
  - 手動で時間を指定したセリフ(locked)は、そのまま動かさない。後続は、そのセリフの後ろから続く。
    ただし時間は戻らない(後続が、すでに置いたセリフと重なることはない。同時会話を除く)。
"""
from dataclasses import dataclass

from ..constants import ESTIMATE_MIN_MS, ESTIMATE_MS_PER_CHAR, MIN_DURATION_MS


def estimate_duration_ms(text: str) -> int:
    chars = len("".join(text.split()))
    return max(ESTIMATE_MIN_MS, chars * ESTIMATE_MS_PER_CHAR)


@dataclass(frozen=True)
class PlanInput:
    id: str
    order_index: int
    duration_ms: int
    estimated: bool = False
    group: str | None = None
    locked: bool = False
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class Placement:
    id: str
    start_ms: int
    end_ms: int
    estimated: bool
    kept_locked: bool  # 手動指定のため動かさなかった


def plan_layout(
    items: list[PlanInput], gap_ms: int, start_ms: int = 0, overwrite_locked: bool = False
) -> list[Placement]:
    cursor = start_ms
    group_start: dict[str, int] = {}
    result: list[Placement] = []
    for item in sorted(items, key=lambda i: i.order_index):
        if item.locked and not overwrite_locked and item.start_ms is not None and item.end_ms is not None:
            start, end, kept = item.start_ms, item.end_ms, True
        else:
            kept = False
            if item.group is not None and item.group in group_start:
                start = group_start[item.group]
            else:
                start = cursor
                if item.group is not None:
                    group_start[item.group] = start
            end = start + max(MIN_DURATION_MS, item.duration_ms)
        result.append(Placement(item.id, start, end, item.estimated and not kept, kept))
        cursor = max(cursor, end + gap_ms)
    return result


# ---- Phase 4: 編集用の純粋な規則 ----
def audio_item_end_ms(start_ms: int, audio_duration_ms: int, speed: float) -> int:
    """再生速度を反映した、音声項目の終了時間。2倍速なら長さは半分。"""
    speed = speed if speed and speed > 0 else 1.0
    return start_ms + max(MIN_DURATION_MS, round(audio_duration_ms / speed))


def pick_undo(entries: list[tuple[int, bool]]) -> int | None:
    """元に戻す対象の履歴(seq)。まだ戻していない履歴のうち、一番新しいもの。entries は (seq, undone)。"""
    live = [seq for seq, undone in entries if not undone]
    return max(live) if live else None


def pick_redo(entries: list[tuple[int, bool]]) -> int | None:
    """やり直す対象の履歴(seq)。戻した履歴のうち、一番古いもの(=直前に戻したもの)。"""
    undone = [seq for seq, undone in entries if undone]
    return min(undone) if undone else None
