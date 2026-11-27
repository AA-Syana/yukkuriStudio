import type { Job, RenderOptions, RenderStatus } from "../types";
import { http } from "./client";

export const renderApi = {
  start: (projectId: string, options: RenderOptions) => http.post<Job>(`/projects/${projectId}/render`, options),
  status: (projectId: string) => http.get<RenderStatus>(`/projects/${projectId}/render-status`),
  // ログインのCookieが付くので、リンクのままダウンロードできる
  downloadUrl: (projectId: string) => `/api/projects/${projectId}/download`,
};
