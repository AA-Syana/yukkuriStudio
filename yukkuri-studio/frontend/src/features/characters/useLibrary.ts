import { useCallback, useEffect, useState } from "react";
import { messageOf } from "../../api/client";
import { libraryApi } from "../../api/characters";
import { generationApi } from "../../api/generation";
import { useRunner } from "../../hooks/useRunner";
import type { Character, CharacterInput } from "../../types";
import { useJobs } from "../jobs/useJobs";
import { makeCharacterOps } from "./characterOps";

/** キャラクター管理画面(ライブラリ)の状態とAPI呼び出し。 */
export function useLibrary() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const { busy, error, setError, clearError, run } = useRunner();

  const reload = useCallback(async () => setCharacters(await libraryApi.list()), []);

  // 生成ジョブが終わったら、画像・音声サンプルの最新状態を取得し直す
  const jobs = useJobs(async () => {
    try {
      await reload();
    } catch (e) {
      setError(messageOf(e));
    }
  });
  const { resume } = jobs;

  useEffect(() => {
    reload()
      .then(() => generationApi.listJobs())
      .then((all) => resume(all.filter((j) => j.project_id === null))) // キャラクター単体の生成だけを追跡する
      .catch((e) => setError(messageOf(e)))
      .finally(() => setLoading(false));
  }, [reload, resume, setError]);

  const patch = useCallback(
    (id: string, update: (c: Character) => Character) => setCharacters((prev) => prev.map((c) => (c.id === id ? update(c) : c))),
    [],
  );
  const ops = makeCharacterOps({ run, track: jobs.track, patch });

  return {
    characters, loading, busy, error, clearError, ops,
    jobs: jobs.jobs,
    retryJob: (job: Parameters<typeof jobs.retry>[0]) => run(() => jobs.retry(job)),
    dismissFinishedJobs: jobs.dismissFinished,

    create: (input: Partial<CharacterInput> & { name: string }) =>
      run(async () => {
        const c = await libraryApi.create(input);
        setCharacters((prev) => [...prev, c]);
        return c;
      }),
    update: (id: string, input: Partial<CharacterInput>) =>
      run(async () => {
        const c = await libraryApi.update(id, input);
        patch(id, () => c);
      }),
    remove: (id: string) =>
      run(async () => {
        await libraryApi.remove(id);
        setCharacters((prev) => prev.filter((c) => c.id !== id));
      }),
  };
}
