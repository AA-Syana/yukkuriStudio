import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import JobPanel from "../features/jobs/JobPanel";
import EditPanel, { type EditTab } from "../features/editor/EditPanel";
import PreviewStage from "../features/editor/PreviewStage";
import TimelineEditor, { LANE_LABEL_PX, buildLanes } from "../features/editor/TimelineEditor";
import TransportBar from "../features/editor/TransportBar";
import RenderPanel from "../features/render/RenderPanel";
import { clamp, neighborStart } from "../features/editor/timelineMath";
import { useEditor } from "../features/editor/useEditor";
import { usePlayback } from "../features/editor/usePlayback";

const MIN_ZOOM = 10;
const MAX_ZOOM = 400;

/** 入力欄などにフォーカスがあるときは、キーボードショートカットを効かせない。 */
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(el.tagName) || el.isContentEditable);
}

/** 画面6: 動画編集。プレビュー・タイムライン・編集パネル(音声/画像/字幕)と、MP4への書き出し。 */
export default function EditorPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const ed = useEditor(projectId, params.get("script"));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<EditTab>("subtitle");
  const [pxPerSec, setPxPerSec] = useState(80);
  const [hiddenLanes, setHiddenLanes] = useState<Set<string>>(new Set());
  const [videoSound, setVideoSound] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const timelineWrap = useRef<HTMLDivElement>(null);
  const getVideo = useCallback(() => videoRef.current, []);

  const items = useMemo(() => ed.timeline?.items ?? [], [ed.timeline]);
  const totalMs = Math.max(ed.timeline?.total_ms ?? 0, ed.video?.duration_ms ?? 0);
  const playback = usePlayback({ items, totalMs, getVideo, videoSound });
  const { seek, toggle, pause, store } = playback;

  const selected = ed.dialogues.find((d) => d.id === selectedId) ?? null; // 削除などで無くなったセリフは選択なし
  const itemOf = (track: string) => items.find((i) => i.dialogue_id === selectedId && i.track_type === track);
  const character = selected?.character_id ? ed.characters.find((c) => c.id === selected.character_id) ?? null : null;
  const lanes = useMemo(() => buildLanes(ed.characters, ed.dialogues, items, ed.video), [ed.characters, ed.dialogues, items, ed.video]);
  const starts = useMemo(() => ed.dialogues.flatMap((d) => (d.start_ms === null ? [] : [d.start_ms])), [ed.dialogues]);

  const select = useCallback((dialogueId: string, track: "character" | "subtitle" | null) => {
    setSelectedId(dialogueId);
    if (track === "subtitle") setTab("subtitle");
    if (track === "character") setTab("image");
  }, []);

  const jump = (direction: "prev" | "next") => {
    const to = neighborStart(starts, store.get(), direction);
    if (to !== null) seek(to);
  };

  // キーボード: Ctrl+Z 元に戻す / Ctrl+Y・Ctrl+Shift+Z やり直し / スペース 再生・停止
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      if (mod && key === "z" && !e.shiftKey) { e.preventDefault(); if (ed.history.can_undo) void ed.undo(); }
      else if (mod && (key === "y" || (key === "z" && e.shiftKey))) { e.preventDefault(); if (ed.history.can_redo) void ed.redo(); }
      else if (!mod && e.key === " ") { e.preventDefault(); toggle(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ed, toggle]);

  // 画面を離れる・台本を切り替えるときは再生を止める
  useEffect(() => pause, [pause]);

  const fitZoom = () => {
    const width = (timelineWrap.current?.clientWidth ?? 800) - LANE_LABEL_PX - 24;
    setPxPerSec(clamp(width / Math.max(totalMs / 1000, 1), MIN_ZOOM, MAX_ZOOM));
  };
  const toggleLane = (id: string) =>
    setHiddenLanes((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  if (ed.loading) return <p>読み込み中…</p>;
  if (!ed.project) return <ErrorBanner message={ed.error ?? "プロジェクトが見つかりません"} />;
  const hasItems = items.length > 0;

  return (
    <section className="editor">
      <p><Link to={`/projects/${projectId}/script${ed.scriptId ? `?script=${ed.scriptId}` : ""}`}>← 台本・キャラクターに戻る</Link></p>
      <div className="row space-between">
        <h1>動画編集：{ed.project.title}</h1>
        <div className="row">
          <button onClick={() => void ed.undo()} disabled={ed.busy || !ed.history.can_undo} title={ed.history.undo_label ? `元に戻す：${ed.history.undo_label} (Ctrl+Z)` : "元に戻す (Ctrl+Z)"}>
            ↶ 元に戻す
          </button>
          <button onClick={() => void ed.redo()} disabled={ed.busy || !ed.history.can_redo} title={ed.history.redo_label ? `やり直し：${ed.history.redo_label} (Ctrl+Y)` : "やり直し (Ctrl+Y)"}>
            ↷ やり直し
          </button>
          <span className="muted small">編集内容は自動で保存されます</span>
        </div>
      </div>
      <ErrorBanner message={ed.error} onClose={ed.clearError} />
      <JobPanel jobs={ed.jobs} onRetry={(job) => void ed.retryJob(job)} onDismiss={ed.dismissFinishedJobs} />

      {ed.scripts.length > 1 && (
        <div className="tabs" role="tablist">
          {ed.scripts.map((sc) => (
            <button
              key={sc.id} role="tab" aria-selected={sc.id === ed.scriptId} className={sc.id === ed.scriptId ? "tab active" : "tab"}
              disabled={ed.busy}
              onClick={() => { pause(); seek(0); setSelectedId(null); setParams({ script: sc.id }, { replace: true }); void ed.selectScript(sc.id); }}
            >
              {sc.title || "（無題）"}
            </button>
          ))}
        </div>
      )}

      {ed.timeline && ed.timeline.warnings.length > 0 && (
        <div className="warning">
          <strong>確認してください</strong>
          <ul>{ed.timeline.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      {!ed.video && (
        <p className="notice">
          元動画がありません。黒い背景でプレビューします。元動画を使う場合は
          <Link to={`/projects/${projectId}/upload`}>アップロード</Link>してください。
        </p>
      )}

      <div className="editor-grid">
        <div className="editor-main">
          <PreviewStage
            projectId={projectId} video={ed.video} videoRef={videoRef} characters={ed.characters} dialogues={ed.dialogues}
            items={items} store={store} selectedDialogueId={selectedId}
            onSelect={select}
            onMoveCharacter={(itemId, x, y) => void ed.updateItem(itemId, { position_x: x, position_y: y })}
          />
          <TransportBar
            store={store} totalMs={totalMs} playing={playback.playing} canPrev canNext
            onToggle={toggle} onPrev={() => jump("prev")} onNext={() => jump("next")} onSeek={seek}
          />
          {ed.video && (
            <label className="small">
              <input type="checkbox" checked={videoSound} onChange={(e) => setVideoSound(e.target.checked)} /> 元動画の音を鳴らす
            </label>
          )}

          <div className="card" ref={timelineWrap}>
            <div className="row space-between">
              <strong>タイムライン</strong>
              <div className="row">
                <button disabled={ed.busy || !ed.scriptId || ed.dialogues.length === 0} onClick={() => void ed.layout(false)}
                  title="手動で調整した時間は動かしません">タイミングを自動配置</button>
                <button disabled={ed.busy || !hasItems}
                  onClick={() => window.confirm("手動で調整した時間も含めて、すべて自動配置し直します。(元に戻すで戻せます)\n続けますか？") && void ed.layout(true)}>
                  すべて振り直す
                </button>
                <span className="muted small">拡大</span>
                <button onClick={() => setPxPerSec((z) => clamp(z / 1.5, MIN_ZOOM, MAX_ZOOM))} aria-label="縮小">－</button>
                <input type="range" min={MIN_ZOOM} max={MAX_ZOOM} value={pxPerSec} onChange={(e) => setPxPerSec(Number(e.target.value))} aria-label="拡大率" />
                <button onClick={() => setPxPerSec((z) => clamp(z * 1.5, MIN_ZOOM, MAX_ZOOM))} aria-label="拡大">＋</button>
                <button onClick={fitZoom}>全体を表示</button>
              </div>
            </div>
            <div className="row lane-toggles">
              <span className="muted small">表示するレーン：</span>
              {lanes.map((l) => (
                <label key={l.id} className="small">
                  <input type="checkbox" checked={!hiddenLanes.has(l.id)} onChange={() => toggleLane(l.id)} /> {l.label}
                </label>
              ))}
            </div>
            {hasItems ? (
              <div className="tl-scroll">
                <TimelineEditor
                  characters={ed.characters} dialogues={ed.dialogues} items={items} video={ed.video} totalMs={totalMs}
                  pxPerSec={pxPerSec} hiddenLanes={hiddenLanes} selectedDialogueId={selectedId} store={store}
                  onSelect={select} onSeek={seek}
                  onMoveDialogue={(id, s, e) => void ed.moveDialogue(id, s, e)}
                  onMoveItem={(id, s, e) => void ed.updateItem(id, { start_ms: s, end_ms: e })}
                />
              </div>
            ) : (
              <p className="muted">まだ配置されていません。「タイミングを自動配置」を押してください（セリフが無い場合は、台本・キャラクター画面で台本を分割してください）。</p>
            )}
            <p className="muted small">
              ブロックをドラッグで移動、左右の端をドラッグで長さを変更。キャラクターのレーンは「セリフ全体」(音声・立ち絵・字幕が連動)、
              字幕レーンは「字幕だけ」の時間を変えます。オレンジの枠は手動で調整済みの印で、自動配置では動きません。
            </p>
          </div>

          <RenderPanel
            projectId={projectId} scriptId={ed.scriptId} hasVideo={!!ed.video} hasTimeline={hasItems}
            includeOriginalAudio={videoSound} onIncludeOriginalAudio={setVideoSound}
          />
        </div>

        <aside className="editor-side">
          <EditPanel
            tab={tab} onTab={setTab} dialogue={selected}
            audioItem={itemOf("audio")} characterItem={itemOf("character")} subtitleItem={itemOf("subtitle")}
            character={character} busy={ed.busy}
            onItem={(id, patch) => void ed.updateItem(id, patch)}
            onFitToAudio={(d) => void ed.fitToAudio(d)}
            onRegenerateVoice={(id) => void ed.regenerateVoice(id)}
            onGenerateImage={(cid, expr) => void ed.generateImage(cid, expr)}
            onLayout={() => void ed.layout(false)}
          />
        </aside>
      </div>
    </section>
  );
}
