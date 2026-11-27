import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, messageOf } from "../../api/client";
import { libraryApi, projectCharactersApi } from "../../api/characters";
import { generationApi } from "../../api/generation";
import { projectsApi } from "../../api/projects";
import { scriptsApi } from "../../api/scripts";
import { useRunner } from "../../hooks/useRunner";
import type {
  Character, CharacterInput, Dialogue, DialoguePatch, Job, LayoutOptions, Project, Script, UnknownSpeaker,
} from "../../types";
import { makeCharacterOps } from "../characters/characterOps";
import { useJobs } from "../jobs/useJobs";

/** 台本作成画面の状態とAPI呼び出し(UIコンポーネントからロジックを分離する)。 */
export function useScriptEditor(projectId: string, initialScriptId: string | null) {
  const [project, setProject] = useState<Project | null>(null);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [dialogues, setDialogues] = useState<Dialogue[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]); // このプロジェクトのキャラクター(コピー)
  const [library, setLibrary] = useState<Character[]>([]); // 追加元の候補(キャラクター管理のもの)
  const [unknown, setUnknown] = useState<UnknownSpeaker[]>([]);
  const [speakerless, setSpeakerless] = useState(0);
  const [layoutWarnings, setLayoutWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const { busy, error, setError, clearError, run } = useRunner();

  const activeRef = useRef<string | null>(null); // 画面の切り替え中に、古い読み込み結果で上書きしないための印
  const active = scripts.find((s) => s.id === activeId) ?? null;
  const dirty = active !== null && content !== active.content;

  /** 選択中の台本のセリフ・未登録の話者・プロジェクトのキャラクターを取得し直す。 */
  const refresh = useCallback(async () => {
    const id = activeRef.current;
    const [chars, lib, ds, unk] = await Promise.all([
      projectCharactersApi.list(projectId),
      libraryApi.list(),
      id ? scriptsApi.listDialogues(id) : Promise.resolve([] as Dialogue[]),
      id ? scriptsApi.unknownSpeakers(id) : Promise.resolve([] as UnknownSpeaker[]),
    ]);
    if (activeRef.current !== id) return;
    setCharacters(chars);
    setLibrary(lib);
    setDialogues(ds);
    setUnknown(unk);
  }, [projectId]);

  const jobs = useJobs(async () => {
    try {
      await refresh();
    } catch (e) {
      setError(messageOf(e));
    }
  });
  const { resume } = jobs;

  const select = useCallback(
    async (id: string | null, list?: Script[]) => {
      activeRef.current = id;
      setActiveId(id);
      setSpeakerless(0);
      setLayoutWarnings([]);
      const s = (list ?? scripts).find((x) => x.id === id);
      setContent(s?.content ?? "");
      setDialogues([]);
      await refresh();
    },
    [refresh, scripts],
  );

  useEffect(() => {
    setLoading(true);
    (async () => {
      const [p, list] = await Promise.all([projectsApi.get(projectId), scriptsApi.list(projectId)]);
      setProject(p);
      setScripts(list);
      const first = list.find((s) => s.id === initialScriptId) ?? list[0] ?? null;
      activeRef.current = first?.id ?? null;
      setActiveId(first?.id ?? null);
      setContent(first?.content ?? "");
      await refresh();
      resume(await generationApi.listJobs(projectId));
    })()
      .catch((e) => setError(messageOf(e)))
      .finally(() => setLoading(false));
    // initialScriptId は初回表示にだけ使う
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const replaceScript = (s: Script) => setScripts((prev) => prev.map((x) => (x.id === s.id ? s : x)));

  /** 編集中の内容を保存する。切り替え・分割の前に呼ぶ。 */
  const saveContent = async (): Promise<Script | undefined> => {
    if (!active) return undefined;
    if (!dirty) return active;
    const saved = await scriptsApi.update(active.id, { content });
    replaceScript(saved);
    return saved;
  };

  const startJob = (start: () => Promise<Job>) =>
    run(async () => {
      void jobs.track(await start());
    });

  const patchCharacter = useCallback(
    (id: string, update: (c: Character) => Character) => setCharacters((prev) => prev.map((c) => (c.id === id ? update(c) : c))),
    [],
  );
  const characterOps = makeCharacterOps({ run, track: jobs.track, patch: patchCharacter });

  const mergeDialogues = (updated: Dialogue[]) =>
    setDialogues((prev) => prev.map((d) => updated.find((u) => u.id === d.id) ?? d));

  return {
    project, scripts, active, activeId, content, setContent, dirty, dialogues, characters, library, unknown, speakerless,
    loading, busy, error, clearError,
    jobs: jobs.jobs,
    retryJob: (job: Job) => run(() => jobs.retry(job)),
    dismissFinishedJobs: jobs.dismissFinished,
    characterOps,

    // ---- 台本 ----
    selectScript: (id: string) =>
      run(async () => {
        await saveContent(); // 切り替えで入力が消えないよう、先に保存する
        await select(id);
      }),
    createScript: () =>
      run(async () => {
        await saveContent();
        const s = await scriptsApi.create(projectId);
        const list = [...scripts, s];
        setScripts(list);
        await select(s.id, list);
      }),
    renameScript: (title: string) =>
      run(async () => {
        if (active) replaceScript(await scriptsApi.update(active.id, { title }));
      }),
    deleteScript: () =>
      run(async () => {
        if (!active) return;
        await scriptsApi.remove(active.id);
        const list = scripts.filter((s) => s.id !== active.id);
        setScripts(list);
        await select(list[0]?.id ?? null, list);
      }),
    saveScript: () => run(async () => void (await saveContent())),

    /** 保存してセリフに分割する。手動編集済みのセリフがあれば "conflict" を返す。 */
    async parse(force: boolean): Promise<"ok" | "conflict" | "error"> {
      clearError();
      try {
        const saved = await saveContent();
        if (!saved) return "error";
        const result = await scriptsApi.parse(saved.id, force);
        setDialogues(result.dialogues);
        setUnknown(result.unknown_speakers);
        setSpeakerless(result.speakerless_lines);
        replaceScript(await scriptsApi.get(saved.id)); // 分割で上がった版数を反映する
        return "ok";
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) return "conflict";
        setError(messageOf(e));
        return "error";
      }
    },

    // ---- セリフ ----
    addDialogue: (text: string, characterId: string | null) =>
      run(async () => {
        if (!activeId) return;
        const d = await scriptsApi.addDialogue(activeId, text, characterId);
        setDialogues((prev) => [...prev, d]);
      }),
    updateDialogue: (id: string, patch: DialoguePatch) =>
      run(async () => {
        const d = await scriptsApi.updateDialogue(id, patch);
        setDialogues((prev) => prev.map((x) => (x.id === id ? d : x)));
      }),
    deleteDialogue: (id: string) =>
      run(async () => {
        await scriptsApi.deleteDialogue(id);
        setDialogues((prev) => prev.filter((x) => x.id !== id));
      }),
    group: (ids: string[]) => run(async () => activeId && mergeDialogues(await scriptsApi.group(activeId, ids))),
    ungroup: (ids: string[]) => run(async () => activeId && mergeDialogues(await scriptsApi.ungroup(activeId, ids))),

    /** セリフの時間を自動配置する。結果の警告(見積もり・未生成の音声など)を返す。 */
    layout: (options: LayoutOptions) =>
      run(async () => {
        if (!activeId) return;
        const result = await scriptsApi.layout(activeId, options);
        setDialogues(result.dialogues);
        setLayoutWarnings(result.timeline.warnings);
      }),
    layoutWarnings,

    generateVoice: (dialogueId: string) => startJob(() => generationApi.regenerateVoice(dialogueId)),
    generateAllVoices: () => startJob(() => generationApi.generateScriptVoices(projectId, activeId!)),
    analyze: () => startJob(() => generationApi.analyze(activeId!)),

    // ---- このプロジェクトのキャラクター(コピー) ----
    addFromLibrary: (sourceId: string) =>
      run(async () => {
        await projectCharactersApi.add(projectId, sourceId);
        await refresh(); // 話者名が一致するセリフが結びつき、未登録の警告も更新される
        setProject(await projectsApi.get(projectId));
      }),
    updateCharacter: (id: string, input: Partial<CharacterInput>) =>
      run(async () => {
        const c = await projectCharactersApi.update(projectId, id, input);
        patchCharacter(id, () => c);
        if (activeId) setDialogues(await scriptsApi.listDialogues(activeId)); // 声の設定が変わると「再生成が必要」の表示が変わる
      }),
    removeCharacter: (id: string) =>
      run(async () => {
        await projectCharactersApi.remove(projectId, id);
        await refresh();
        setProject(await projectsApi.get(projectId));
      }),
  };
}
