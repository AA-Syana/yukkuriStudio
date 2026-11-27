import { useState } from "react";
import { renderApi } from "../../api/render";
import ErrorBanner from "../../components/ErrorBanner";
import type { RenderOptions } from "../../types";
import { formatClock } from "../editor/timelineMath";
import { useRender } from "./useRender";

interface Props {
  projectId: string;
  scriptId: string | null;
  hasVideo: boolean;
  hasTimeline: boolean; // タイムラインに配置済みの項目がある
  includeOriginalAudio: boolean; // プレビューの「元動画の音」と同じ設定を使う
  onIncludeOriginalAudio: (v: boolean) => void;
}

const SIZES: { value: string; label: string }[] = [
  { value: "", label: "元動画と同じ（元動画が無ければ1080p）" },
  { value: "1080", label: "1080p（1920×1080）" },
  { value: "720", label: "720p（1280×720）" },
  { value: "480", label: "480p（854×480・速い）" },
];

const formatSize = (bytes: number) => (bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`);

/** MP4への書き出し。進捗を表示し、できあがったらダウンロードできる。 */
export default function RenderPanel(props: Props) {
  const { projectId, scriptId, hasVideo, hasTimeline } = props;
  const r = useRender(projectId);
  const [height, setHeight] = useState("");
  const job = r.status?.job ?? null;
  const done = r.status?.last_success ?? null;
  const failed = job?.status === "failed";

  const start = () =>
    void r.start({
      script_id: scriptId,
      height: (height ? Number(height) : null) as RenderOptions["height"],
      include_original_audio: props.includeOriginalAudio,
      original_volume: 1,
    });

  return (
    <div className="card render-panel">
      <strong>MP4に書き出す</strong>
      <p className="muted small">
        いま編集している内容（時間・音量・再生速度・立ち絵の位置とサイズ・表情・字幕）が反映されます。
        書き出しには動画の長さに応じた時間がかかります。
      </p>
      <ErrorBanner message={r.error} onClose={r.clearError} />
      <div className="row">
        <label className="small">
          出力サイズ{" "}
          <select value={height} onChange={(e) => setHeight(e.target.value)} disabled={r.active} aria-label="出力サイズ">
            {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label className="small">
          <input
            type="checkbox" checked={props.includeOriginalAudio} disabled={!hasVideo || r.active}
            onChange={(e) => props.onIncludeOriginalAudio(e.target.checked)}
          />{" "}
          元動画の音を含める
        </label>
        <button className="primary" disabled={!hasTimeline || !scriptId || r.active || r.starting} onClick={start}>
          {done ? "もう一度書き出す" : "MP4を書き出す"}
        </button>
      </div>
      {!hasTimeline && <p className="muted small">先に「タイミングを自動配置」を実行してください。</p>}

      {r.active && job && (
        <div className="render-progress">
          <progress max={100} value={job.progress} aria-label="書き出しの進捗" />
          <span className="small">{job.status === "queued" ? "順番待ち…" : `書き出し中… ${job.progress}%`}</span>
        </div>
      )}
      {failed && job && (
        <div className="warning">
          <strong>書き出しに失敗しました</strong>
          <p className="small">{job.error}</p>
          <button onClick={() => void r.retry()} disabled={r.starting}>もう一度試す</button>
        </div>
      )}

      {done && (
        <div className="render-done">
          <p>
            <strong>最新の書き出し</strong>：{new Date(done.finished_at).toLocaleString("ja-JP")} ・ {done.width}×{done.height} ・{" "}
            {formatClock(done.duration_ms)} ・ {formatSize(done.size_bytes)}
          </p>
          <p><a className="button primary" href={renderApi.downloadUrl(projectId)} download>MP4をダウンロード</a></p>
          {done.warnings.length > 0 && (
            <div className="warning">
              <strong>書き出し時の注意</strong>
              <ul>{done.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          )}
          <p className="muted small">この書き出し以降に編集した内容は含まれません。編集したら、もう一度書き出してください。</p>
        </div>
      )}
    </div>
  );
}
