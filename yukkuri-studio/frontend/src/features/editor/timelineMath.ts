/**
 * 動画編集画面の計算(画面の部品から切り離した純粋な関数)。DOM・Reactに依存しないので、単体で確認できる。
 * 時間はすべてミリ秒。
 */

export const MIN_DURATION_MS = 100;
export const SNAP_MS = 10;

export type DragMode = "move" | "start" | "end";
export interface Range {
  start: number;
  end: number;
}

const snap = (ms: number) => Math.round(ms / SNAP_MS) * SNAP_MS;

/** ドラッグ中の範囲。move=全体を動かす、start/end=片側の端を動かす。0未満・最小の長さ未満にはならない。 */
export function dragRange(mode: DragMode, original: Range, deltaMs: number): Range {
  const length = original.end - original.start;
  if (mode === "move") {
    const start = Math.max(0, snap(original.start + deltaMs));
    return { start, end: start + length };
  }
  if (mode === "start") {
    const start = Math.min(Math.max(0, snap(original.start + deltaMs)), original.end - MIN_DURATION_MS);
    return { start, end: original.end };
  }
  const end = Math.max(snap(original.end + deltaMs), original.start + MIN_DURATION_MS);
  return { start: original.start, end };
}

export const msToPx = (ms: number, pxPerSec: number) => (ms / 1000) * pxPerSec;
export const pxToMs = (px: number, pxPerSec: number) => (px / pxPerSec) * 1000;

/** ある時刻に表示される項目(開始以上・終了未満)。 */
export function activeAt<T extends Range>(items: T[], timeMs: number): T[] {
  return items.filter((i) => i.start <= timeMs && timeMs < i.end);
}

/**
 * 重なるブロックを、重ならない段(row)に振り分ける。同時会話のセリフを、同じレーン内で縦に並べて表示するため。
 * 戻り値は入力と同じ順番の段番号。
 */
export function assignRows(blocks: Range[]): { rows: number[]; rowCount: number } {
  const order = blocks.map((_, i) => i).sort((a, b) => blocks[a].start - blocks[b].start || blocks[a].end - blocks[b].end);
  const rowEnds: number[] = [];
  const rows = new Array<number>(blocks.length).fill(0);
  for (const i of order) {
    let row = rowEnds.findIndex((end) => end <= blocks[i].start);
    if (row === -1) {
      row = rowEnds.length;
      rowEnds.push(0);
    }
    rowEnds[row] = blocks[i].end;
    rows[i] = row;
  }
  return { rows, rowCount: Math.max(1, rowEnds.length) };
}

/** 前後のセリフの開始位置へ移動するための時刻を返す。無ければ null。 */
export function neighborStart(starts: number[], timeMs: number, direction: "prev" | "next"): number | null {
  const sorted = [...new Set(starts)].sort((a, b) => a - b);
  if (direction === "next") return sorted.find((s) => s > timeMs + 1) ?? null;
  // 「前へ」は、セリフの途中なら、そのセリフの頭へ戻る
  const before = sorted.filter((s) => s < timeMs - 300);
  return before.length ? before[before.length - 1] : null;
}

/** 音声ファイルの再生開始位置(秒)。再生速度ぶん、音声側の時間は速く進む。 */
export function audioOffsetSec(itemStartMs: number, timeMs: number, speed: number): number {
  return Math.max(0, ((timeMs - itemStartMs) / 1000) * speed);
}

/** 立ち絵に使う画像。指定の表情 → セリフの感情 → 平常 → 何かある画像、の順に探す。無ければ null。 */
export function pickImage<E extends string>(
  images: { expression: E; asset_id: string }[],
  expression: E | null,
  emotion: E,
  neutral: E,
): { expression: E; asset_id: string } | null {
  const by = (e: E | null) => (e ? images.find((i) => i.expression === e) : undefined);
  return by(expression) ?? by(emotion) ?? by(neutral) ?? images[0] ?? null;
}

/**
 * 同時に表示される字幕が重ならないよう、段(0が基準位置、1以上は上へずらす)を決める。
 * 位置がほぼ同じ(±0.05)字幕だけを重なりとみなす。
 */
export function subtitleStack<T extends { id: string; x: number; y: number }>(active: T[]): Map<string, number> {
  const result = new Map<string, number>();
  const placed: { x: number; y: number; level: number }[] = [];
  for (const s of active) {
    const used = new Set(placed.filter((p) => Math.abs(p.x - s.x) < 0.05 && Math.abs(p.y - s.y) < 0.05).map((p) => p.level));
    let level = 0;
    while (used.has(level)) level++;
    placed.push({ x: s.x, y: s.y, level });
    result.set(s.id, level);
  }
  return result;
}

/** 目盛りの間隔(ms)。拡大率に応じて、目盛りの間が 80px 以上になるようにする。 */
export function tickStepMs(pxPerSec: number): number {
  const candidates = [500, 1000, 2000, 5000, 10_000, 30_000, 60_000, 300_000];
  return candidates.find((c) => msToPx(c, pxPerSec) >= 80) ?? candidates[candidates.length - 1];
}

export function formatClock(ms: number): string {
  const total = Math.max(0, ms);
  const m = Math.floor(total / 60_000);
  const s = Math.floor((total % 60_000) / 1000);
  const tenth = Math.floor((total % 1000) / 100);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${tenth}`;
}

export const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);
