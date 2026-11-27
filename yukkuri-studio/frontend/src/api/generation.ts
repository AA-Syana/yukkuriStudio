import type { Character, Emotion, Job } from "../types";
import { http } from "./client";

/** 生成系のAPI。起動すると即座にJobが返り、完了は getJob で確認する。 */
export const generationApi = {
  regenerateVoice: (dialogueId: string) => http.post<Job>(`/dialogues/${dialogueId}/regenerate`, {}),
  generateScriptVoices: (projectId: string, scriptId: string) =>
    http.post<Job>(`/projects/${projectId}/generate`, { script_id: scriptId }),
  analyze: (scriptId: string) => http.post<Job>(`/scripts/${scriptId}/analyze`, {}),

  // キャラクターの画像・音声サンプル(ライブラリでもプロジェクトのコピーでも同じAPI)
  generateImage: (characterId: string, expression: Emotion | null) =>
    http.post<Job>(`/characters/${characterId}/generate-image`, { expression }),
  generateVoiceSample: (characterId: string) => http.post<Job>(`/characters/${characterId}/generate-voice`, {}),
  uploadImage(characterId: string, expression: Emotion, file: File) {
    const form = new FormData();
    form.append("expression", expression);
    form.append("file", file);
    return http.upload<Character>(`/characters/${characterId}/images/upload`, form);
  },
  deleteImage: (characterId: string, expression: Emotion) => http.del(`/characters/${characterId}/images/${expression}`),

  getJob: (jobId: string) => http.get<Job>(`/generation-jobs/${jobId}`),
  listJobs: (projectId?: string) => http.get<Job[]>(`/generation-jobs${projectId ? `?project_id=${projectId}` : ""}`),
  retryJob: (jobId: string) => http.post<Job>(`/generation-jobs/${jobId}/retry`, {}),

  // 音声・画像ファイルのURL。再生成するとasset_idが変わるので、ブラウザのキャッシュが古いまま残らない
  assetUrl: (assetId: string) => `/api/assets/${assetId}/file`,
};
