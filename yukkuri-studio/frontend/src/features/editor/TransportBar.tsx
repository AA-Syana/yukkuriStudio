import { formatClock } from "./timelineMath";
import { useTime, type TimeStore } from "./usePlayback";

interface Props {
  store: TimeStore;
  totalMs: number;
  playing: boolean;
  canPrev: boolean;
  canNext: boolean;
  onToggle: () => void;
  onPrev: () => void;
  onNext: () => void;
  onSeek: (ms: number) => void;
}

/** 再生・停止、前後のセリフへの移動、現在の再生時間と全体の長さ。 */
export default function TransportBar(p: Props) {
  const t = useTime(p.store);
  return (
    <div className="transport">
      <button onClick={p.onPrev} disabled={!p.canPrev} aria-label="前のセリフへ" title="前のセリフへ">⏮</button>
      <button className="primary" onClick={p.onToggle} aria-label={p.playing ? "停止" : "再生"} title="再生/停止 (スペースキー)">
        {p.playing ? "⏸ 停止" : "▶ 再生"}
      </button>
      <button onClick={p.onNext} disabled={!p.canNext} aria-label="次のセリフへ" title="次のセリフへ">⏭</button>
      <input
        className="grow" type="range" min={0} max={Math.max(p.totalMs, 1)} step={10} value={Math.min(t, p.totalMs)}
        onChange={(e) => p.onSeek(Number(e.target.value))} aria-label="再生位置"
      />
      <span className="clock">{formatClock(t)} / {formatClock(p.totalMs)}</span>
    </div>
  );
}
