import type { Project } from "../types";
import { http } from "./client";

export const projectsApi = {
  list: () => http.get<Project[]>("/projects"),
  get: (id: string) => http.get<Project>(`/projects/${id}`),
  create: (name: string) => http.post<Project>("/projects", { name }),
  rename: (id: string, name: string) => http.patch<Project>(`/projects/${id}`, { name }),
  remove: (id: string) => http.del(`/projects/${id}`),
};
