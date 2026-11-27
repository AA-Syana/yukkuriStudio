import { generationApi } from "../../api/generation";
import type { Character, Emotion, Job } from "../../types";

/**
 * キャラクターの画像・音声サンプルの操作。ライブラリでもプロジェクトのコピーでも同じAPIを使うので、
 * 両方の画面から共有する。状態の持ち方だけが画面ごとに違うため、更新用の関数を受け取る形にしている。
 */
export function makeCharacterOps(deps: {
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  track: (job: Job) => Promise<void>;
  patch: (id: string, update: (c: Character) => Character) => void;
}) {
  const { run, track, patch } = deps;
  const startJob = (start: () => Promise<Job>) =>
    run(async () => {
      void track(await start());
    });

  return {
    generateImage: (id: string, expression: Emotion | null) => startJob(() => generationApi.generateImage(id, expression)),
    generateVoiceSample: (id: string) => startJob(() => generationApi.generateVoiceSample(id)),
    uploadImage: (id: string, expression: Emotion, file: File) =>
      run(async () => {
        const updated = await generationApi.uploadImage(id, expression, file);
        patch(id, () => updated);
      }),
    deleteImage: (id: string, expression: Emotion) =>
      run(async () => {
        await generationApi.deleteImage(id, expression);
        patch(id, (c) => ({ ...c, images: c.images.filter((i) => i.expression !== expression) }));
      }),
  };
}

export type CharacterOps = ReturnType<typeof makeCharacterOps>;
