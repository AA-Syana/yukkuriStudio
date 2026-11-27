import { memo, useMemo, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { Character, Dialogue, TimelineItem, VideoInfo } from "../../types";
import { assignRows, dragRange, formatClock, msToPx, pxToMs, tickStepMs, type DragMode, type Range } from "./timelineMath";
import { useTime, type TimeStore } from "./usePlayback";

export const LANE_LABEL_PX = 104;
const ROW_PX = 28;

type Track = "character" | "subtitle";
interface Block extends Range {
  key: string;
  label: string;
  dialogueId: string;
  itemId: string | null; // null = セリフそのもの(時間を動かすと、そのセリフの項目がまとめて動く)
  track: Track | null;
  edited: boolean;
  movable: boolean;
}
interface Lane {
  id: string;
  label: string;
  className: string;
  blocks: Block[];
}

interface Props {
  characters: Character[];
  dialogues: Dialogue[];
  items: TimelineItem[];
  video: VideoInfo | null;
  totalMs: number;
  pxPerSec: number;
  hiddenLanes: Set<string>;
  selectedDialogueId: string | null;
  store: TimeStore;
  onSelect: (dialogueId: string, track: Track | null) => void;
  onMoveDialogue: (dialogueId: string, start: number, end: number) => void;
  onMoveItem: (itemId: string, start: number, end: number) => void;
  onSeek: (ms: number) => void;
}

/** レーンの一覧(画面の表示/非表示の切り替えにも使う)。 */
export function buildLanes(
  characters: Character[], dialogues: Dialogue[], items: TimelineItem[], video: VideoInfo | null,
): Lane[] {
  const lanes: Lane[] = [];
  if (video) {
    lanes.push({
      id: "video", label: "動画", className: "video",
      blocks: [{ key: "video", start: 0, end: video.duration_ms, label: video.original_filename, dialogueId: "", itemId: null, track: null, edited: false, movable: false }],
    });
  }
  const placed = dialogues.filter((d) => d.start_ms !== null && d.end_ms !== null);
  const toBlock = (d: Dialogue): Block => ({
    key: `d:${d.id}`, start: d.start_ms!, end: d.end_ms!, label: d.text, dialogueId: d.id, itemId: null,
    track: null, edited: d.timing_locked, movable: true,
  });
  for (const c of characters) {
    lanes.push({ id: `char:${c.id}`, label: c.name, className: "character", blocks: placed.filter((d) => d.character_id === c.id).map(toBlock) });
  }
  const unassigned = placed.filter((d) => d.character_id === null || !characters.some((c) => c.id === d.character_id));
  if (unassigned.length) lanes.push({ id: "char:none", label: "話者未登録", className: "character", blocks: unassigned.map(toBlock) });

  const byDialogue = new Map(dialogues.map((d) => [d.id, d]));
  lanes.push({
    id: "subtitle", label: "字幕", className: "subtitle",
    blocks: items.filter((i) => i.track_type === "subtitle" && byDialogue.has(i.dialogue_id)).map((i) => ({
      key: `i:${i.id}`, start: i.start_ms, end: i.end_ms, label: i.text_override ?? i.text, dialogueId: i.dialogue_id,
      itemId: i.id, track: "subtitle" as const, edited: i.times_edited, movable: true,
    })),
  });
  return lanes;
}

function Playhead({ store, pxPerSec }: { store: TimeStore; pxPerSec: number }) {
  const t = useTime(store);
  return <div className="tl-playhead" style={{ left: LANE_LABEL_PX + msToPx(t, pxPerSec) }} />;
}

function TimelineEditor(props: Props) {
  const { characters, dialogues, items, video, totalMs, pxPerSec, hiddenLanes, selectedDialogueId, store } = props;
  const [drag, setDrag] = useState<{ key: string; start: number; end: number } | null>(null);
  const lanes = useMemo(() => buildLanes(characters, dialogues, items, video), [characters, dialogues, items, video]);
  const widthPx = msToPx(Math.max(totalMs, 1000) + 2000, pxPerSec);
  const step = tickStepMs(pxPerSec);
  const ticks = useMemo(() => {
    const out: number[] = [];
    for (let t = 0; t <= totalMs + 2000; t += step) out.push(t);
    return out;
  }, [totalMs, step]);

  // 再生位置の指定: 目盛り・レーンの空きをクリック/ドラッグ
  const startSeek = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const seekTo = (clientX: number) => props.onSeek(pxToMs(clientX - el.getBoundingClientRect().left, pxPerSec));
    seekTo(e.clientX);
    const move = (ev: PointerEvent) => seekTo(ev.clientX);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const beginDrag = (e: ReactPointerEvent<HTMLElement>, block: Block, mode: DragMode) => {
    if (!block.dialogueId) return; // 動画ブロックは選択も編集もしない(クリックは再生位置の指定として扱われる)
    e.stopPropagation();
    e.preventDefault();
    props.onSelect(block.dialogueId, block.track);
    if (!block.movable) return;
    const x0 = e.clientX;
    const original = { start: block.start, end: block.end };
    let current: Range = original;
    const move = (ev: PointerEvent) => {
      current = dragRange(mode, original, pxToMs(ev.clientX - x0, pxPerSec));
      setDrag({ key: block.key, ...current });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setDrag(null);
      if (current.start === original.start && current.end === original.end) {
        props.onSeek(block.start); // ただのクリック: 選択して、再生位置をそのセリフの頭へ
      } else if (block.itemId) {
        props.onMoveItem(block.itemId, current.start, current.end);
      } else {
        props.onMoveDialogue(block.dialogueId, current.start, current.end);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div className="tl" aria-label="タイムライン">
      <div className="tl-inner" style={{ width: LANE_LABEL_PX + widthPx }}>
        <div className="tl-row">
          <div className="tl-label" />
          <div className="tl-track tl-ruler" style={{ width: widthPx }} onPointerDown={startSeek}>
            {ticks.map((t) => (
              <span key={t} className="tl-tick" style={{ left: msToPx(t, pxPerSec) }}>{formatClock(t).slice(0, 5)}</span>
            ))}
          </div>
        </div>

        {lanes.filter((l) => !hiddenLanes.has(l.id)).map((lane) => {
          const shown = lane.blocks.map((b) => (drag?.key === b.key ? { ...b, start: drag.start, end: drag.end } : b));
          const { rows, rowCount } = assignRows(shown);
          return (
            <div className="tl-row" key={lane.id}>
              <div className="tl-label" title={lane.label}>{lane.label}</div>
              <div className={`tl-track ${lane.className}`} style={{ width: widthPx, height: rowCount * ROW_PX + 4 }} onPointerDown={startSeek}>
                {shown.map((b, i) => {
                  const selected = b.dialogueId !== "" && b.dialogueId === selectedDialogueId;
                  return (
                    <div
                      key={b.key}
                      className={`tl-block ${lane.className} ${selected ? "selected" : ""} ${b.edited ? "edited" : ""} ${drag?.key === b.key ? "dragging" : ""}`}
                      style={{ left: msToPx(b.start, pxPerSec), width: Math.max(msToPx(b.end - b.start, pxPerSec), 6), top: 2 + rows[i] * ROW_PX, height: ROW_PX - 2 }}
                      title={`${b.label}\n${formatClock(b.start)} 〜 ${formatClock(b.end)}${b.edited ? "\n(手動で調整済み)" : ""}`}
                      onPointerDown={(e) => beginDrag(e, b, "move")}
                    >
                      {b.movable && <span className="tl-handle start" onPointerDown={(e) => beginDrag(e, b, "start")} />}
                      <span className="tl-block-text">{b.label}</span>
                      {b.movable && <span className="tl-handle end" onPointerDown={(e) => beginDrag(e, b, "end")} />}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
        <Playhead store={store} pxPerSec={pxPerSec} />
      </div>
    </div>
  );
}

export default memo(TimelineEditor);
