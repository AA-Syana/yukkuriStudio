import { useCallback, useEffect, useState } from "react";
import { ApiError, messageOf } from "../../api/client";
import { scenarioApi } from "../../api/scenario";
import type { Character, CharacterInput, Dialogue, DialoguePatch, Script } from "../../types";

/** シナリオ画面の状態とAPI呼び出しをまとめたフック(UIコンポーネントからロジックを分離する)。 */
export function useScenario(projectId: string) {
  const [script, setScript] = useState<Script | null>(null);
  const [dialogues, setDialogues] = useState<Dialogue[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [s, d, c] = await Promise.all([
      scenarioApi.getScript(projectId),
      scenarioApi.listDialogues(projectId),
      scenarioApi.listCharacters(projectId),
    ]);
    setScript(s);
    setDialogues(d);
    setCharacters(c);
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    reload()
      .catch((e) => setError(messageOf(e)))
      .finally(() => setLoading(false));
  }, [reload]);

  /** 共通のエラー処理。失敗時はundefinedを返す。 */
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null);
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      setError(messageOf(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);

  const mergeDialogues = (updated: Dialogue[]) =>
    setDialogues((prev) => prev.map((d) => updated.find((u) => u.id === d.id) ?? d));

  return {
    script, dialogues, characters, loading, busy, error,
    clearError: () => setError(null),

    saveScript: (text: string) =>
      run(async () => setScript(await scenarioApi.saveScript(projectId, text))),

    /** テキストを保存してセリフに分割する。手動編集済みのセリフがあれば "conflict" を返す。 */
    async parse(text: string, force: boolean): Promise<"ok" | "conflict" | "error"> {
      setError(null);
      setBusy(true);
      try {
        setScript(await scenarioApi.saveScript(projectId, text));
        await scenarioApi.parse(projectId, force);
        await reload();
        return "ok";
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) return "conflict";
        setError(messageOf(e));
        return "error";
      } finally {
        setBusy(false);
      }
    },

    addDialogue: (text: string, characterId: string | null) =>
      run(async () => {
        const d = await scenarioApi.addDialogue(projectId, text, characterId);
        setDialogues((prev) => [...prev, d]);
      }),
    updateDialogue: (id: string, patch: DialoguePatch) =>
      run(async () => {
        const d = await scenarioApi.updateDialogue(projectId, id, patch);
        setDialogues((prev) => prev.map((x) => (x.id === id ? d : x)));
      }),
    deleteDialogue: (id: string) =>
      run(async () => {
        await scenarioApi.deleteDialogue(projectId, id);
        setDialogues((prev) => prev.filter((x) => x.id !== id));
      }),
    group: (ids: string[]) => run(async () => mergeDialogues(await scenarioApi.group(projectId, ids))),
    ungroup: (ids: string[]) => run(async () => mergeDialogues(await scenarioApi.ungroup(projectId, ids))),

    addCharacter: (name: string) =>
      run(async () => {
        const c = await scenarioApi.addCharacter(projectId, { name });
        setCharacters((prev) => [...prev, c]);
      }),
    updateCharacter: (id: string, input: Partial<CharacterInput>) =>
      run(async () => {
        const c = await scenarioApi.updateCharacter(projectId, id, input);
        setCharacters((prev) => prev.map((x) => (x.id === id ? c : x)));
      }),
    deleteCharacter: (id: string) =>
      run(async () => {
        await scenarioApi.deleteCharacter(projectId, id);
        setCharacters((prev) => prev.filter((x) => x.id !== id));
        setDialogues((prev) => prev.map((d) => (d.character_id === id ? { ...d, character_id: null } : d)));
      }),
  };
}
