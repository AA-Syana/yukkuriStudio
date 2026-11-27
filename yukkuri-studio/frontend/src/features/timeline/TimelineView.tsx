import { useMemo } from "react";
import type { Timeline, TrackType } from "../../types";
import { formatMs } from "../script/timeFormat";

const TRACKS: { type: TrackType; label: string }[] = [
  { type: "subtitle", label: "字幕" },
  { type: "character", label: "立ち絵" },
  { type: "audio", label: "音声" },
];

/** 配置結果の読み取り専用タイムライン。ドラッグ編集・プレビューは Phase 4 で実装する。 */
export default function TimelineView({ timeline }: { timeline: Timeline }) {
  const total = Math.max(timeline.total_ms, 1);
  const ticks = useMemo(() => {
    const step = total > 120_000 ? 30_000 : total > 30_000 ? 10_000 : 5_000;
    const out: number[] = [];
    for (let t = 0; t <= timeline.total_ms; t += step) out.push(t);
    return out;
  }, [timeline.total_ms, total]);

  if (timeline.items.length === 0) {
    return <p className="muted">まだ配置されていません。「台本・キャラクター」画面で「タイミングを自動配置」を実行してください。</p>;
  }
  return (
    <div className="timeline" aria-label="タイムライン">
      <div className="timeline-row">
        <div className="timeline-label" />
        <div className="timeline-lane ruler">
          {ticks.map((t) => (
            <span key={t} className="tick" style={{ left: `${(t / total) * 100}%` }}>{formatMs(t)}s</span>
          ))}
        </div>
      </div>
      {TRACKS.map(({ type, label }) => (
        <div className="timeline-row" key={type}>
          <div className="timeline-label">{label}</div>
          <div className="timeline-lane">
            {timeline.items.filter((i) => i.track_type === type).map((i) => (
              <div
                key={i.id}
                className={`timeline-block ${type}`}
                style={{ left: `${(i.start_ms / total) * 100}%`, width: `${Math.max(((i.end_ms - i.start_ms) / total) * 100, 0.5)}%` }}
                title={`${i.speaker_name ?? "話者未指定"}：${i.text}\n${formatMs(i.start_ms)}〜${formatMs(i.end_ms)}秒`}
              >
                {type === "subtitle" ? i.text : i.speaker_name ?? ""}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
