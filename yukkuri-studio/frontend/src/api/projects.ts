import type { Project } from "../types";
import { http } from "./client";

export const projectsApi = {
  list: () => http.get<Project[]>("/projects"),
  get: (id: string) => http.get<Project>(`/projects/${id}`),
  create: (title: string, description: string) => http.post<Project>("/projects", { title, description }),
  update: (id: string, patch: { title?: string; description?: string }) => http.put<Project>(`/projects/${id}`, patch),
  remove: (id: string) => http.del(`/projects/${id}`),
};
