import { useCallback, useEffect, useRef, useState } from "react";
import { messageOf } from "../../api/client";
import { projectCharactersApi } from "../../api/characters";
import { generationApi } from "../../api/generation";
import { projectsApi } from "../../api/projects";
import { scriptsApi } from "../../api/scripts";
import { timelineApi } from "../../api/timeline";
import { videosApi } from "../../api/videos";
import { useRunner } from "../../hooks/useRunner";
import type {
  Character, Dialogue, Emotion, HistoryState, Job, Project, Script, Timeline, TimelineItemPatch, VideoInfo,
} from "../../types";
import { useJobs } from "../jobs/useJobs";
import { MIN_DURATION_MS } from "./timelineMath";

const NO_HISTORY: HistoryState = { can_undo: false, can_redo: false, undo_label: null, redo_label: null };

/** 動画編集画面のデータと操作。編集はその場でサーバーに保存し、保存後に最新の状態を取得し直す。 */
export function useEditor(projectId: string, initialScriptId: string | null) {
  const [project, setProject] = useState<Project | null>(null);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [scriptId, setScriptId] = useState<string | null>(null);
  const [dialogues, setDialogues] = useState<Dialogue[]>([]);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [video, setVideo] = useState<VideoInfo | null>(null);
  const [history, setHistory] = useState<HistoryState>(NO_HISTORY);
  const [loading, setLoading] = useState(true);
  const { busy, error, setError, clearError, run } = useRunner();
  const activeRef = useRef<string | null>(null); // 台本の切り替え中に、古い読み込み結果で上書きしないための印

  const reloadScript = useCallback(async () => {
    const id = activeRef.current;
    if (!id) return;
    const [ds, tl, h] = await Promise.all([scriptsApi.listDialogues(id), scriptsApi.timeline(id), timelineApi.history(projectId)]);
    if (activeRef.current !== id) return;
    setDialogues(ds);
    setTimeline(tl);
    setHistory(h);
  }, [projectId]);

  const reloadAll = useCallback(async () => {
    const chars = await projectCharactersApi.list(projectId);
    setCharacters(chars);
    await reloadScript();
  }, [projectId, reloadScript]);

  const jobs = useJobs(async () => {
    try {
      await reloadAll();
    } catch (e) {
      setError(messageOf(e));
    }
  });
  const { resume } = jobs;

  useEffect(() => {
    setLoading(true);
    (async () => {
      const [p, list, chars, v] = await Promise.all([
        projectsApi.get(projectId), scriptsApi.list(projectId), projectCharactersApi.list(projectId), videosApi.get(projectId),
      ]);
      setProject(p);
      setScripts(list);
      setCharacters(chars);
      setVideo(v);
      const first = list.find((s) => s.id === initialScriptId) ?? list[0] ?? null;
      activeRef.current = first?.id ?? null;
      setScriptId(first?.id ?? null);
      await reloadScript();
      resume(await generationApi.listJobs(projectId));
    })()
      .catch((e) => setError(messageOf(e)))
      .finally(() => setLoading(false));
    // initialScriptId は初回表示にだけ使う
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  /** 保存してから、最新の状態を取得し直す共通の流れ。 */
  const edit = (fn: () => Promise<unknown>) =>
    run(async () => {
      await fn();
      await reloadScript();
    });

  const startJob = (start: () => Promise<Job>) =>
    run(async () => {
      void jobs.track(await start());
    });

  return {
    project, scripts, scriptId, dialogues, timeline, characters, video, history, loading, busy, error, clearError,
    jobs: jobs.jobs,
    retryJob: (job: Job) => run(() => jobs.retry(job)),
    dismissFinishedJobs: jobs.dismissFinished,

    selectScript: (id: string) =>
      run(async () => {
        activeRef.current = id;
        setScriptId(id);
        setDialogues([]);
        setTimeline(null);
        await reloadScript();
      }),
    reload: () => run(reloadAll),

    layout: (overwriteLocked: boolean) =>
      run(async () => {
        if (!scriptId) return;
        await scriptsApi.layout(scriptId, { gap_ms: 300, start_ms: 0, overwrite_locked: overwriteLocked });
        await reloadScript();
      }),
    updateItem: (itemId: string, patch: TimelineItemPatch) => edit(() => timelineApi.updateItem(itemId, patch)),
    moveDialogue: (dialogueId: string, start: number, end: number) =>
      edit(() => scriptsApi.updateDialogue(dialogueId, { start_ms: start, end_ms: end })),
    /** 音声の長さに合わせて、このセリフの終了時間だけを直す(他のセリフは動かさない)。 */
    fitToAudio: (d: Dialogue) =>
      edit(() =>
        scriptsApi.updateDialogue(d.id, {
          start_ms: d.start_ms!,
          end_ms: d.start_ms! + Math.max(MIN_DURATION_MS, d.audio_duration_ms ?? 0),
        }),
      ),
    undo: () => edit(() => timelineApi.undo(projectId)),
    redo: () => edit(() => timelineApi.redo(projectId)),

    regenerateVoice: (dialogueId: string) => startJob(() => generationApi.regenerateVoice(dialogueId)),
    generateImage: (characterId: string, expression: Emotion) => startJob(() => generationApi.generateImage(characterId, expression)),
  };
}
