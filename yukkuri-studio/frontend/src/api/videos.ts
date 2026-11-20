import type { VideoInfo } from "../types";
import { ApiError, http } from "./client";

export const videosApi = {
  // 動画未アップロード(404)は「まだ無い」だけなのでnullを返す
  async get(projectId: string): Promise<VideoInfo | null> {
    try {
      return await http.get<VideoInfo>(`/projects/${projectId}/video`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  upload(projectId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return http.upload<VideoInfo>(`/projects/${projectId}/video`, form);
  },
  streamUrl: (projectId: string) => `/api/projects/${projectId}/video/stream`,
};
