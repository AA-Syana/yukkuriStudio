import type {
  Dialogue, DialoguePatch, LayoutOptions, LayoutResult, ParseResult, Script, Timeline, UnknownSpeaker,
} from "../types";
import { http } from "./client";

export const scriptsApi = {
  list: (projectId: string) => http.get<Script[]>(`/projects/${projectId}/scripts`),
  get: (id: string) => http.get<Script>(`/scripts/${id}`),
  create: (projectId: string, title = "") => http.post<Script>(`/projects/${projectId}/scripts`, { title }),
  update: (id: string, patch: { title?: string; content?: string }) => http.put<Script>(`/scripts/${id}`, patch),
  remove: (id: string) => http.del(`/scripts/${id}`),
  parse: (id: string, force: boolean) => http.post<ParseResult>(`/scripts/${id}/parse`, { force }),
  unknownSpeakers: (id: string) => http.get<UnknownSpeaker[]>(`/scripts/${id}/unknown-speakers`),

  listDialogues: (scriptId: string) => http.get<Dialogue[]>(`/scripts/${scriptId}/dialogues`),
  addDialogue: (scriptId: string, text: string, character_id: string | null) =>
    http.post<Dialogue>(`/scripts/${scriptId}/dialogues`, { text, character_id }),
  updateDialogue: (id: string, patch: DialoguePatch) => http.put<Dialogue>(`/dialogues/${id}`, patch),
  deleteDialogue: (id: string) => http.del(`/dialogues/${id}`),
  group: (scriptId: string, ids: string[]) =>
    http.post<Dialogue[]>(`/scripts/${scriptId}/dialogues/group`, { dialogue_ids: ids }),
  layout: (scriptId: string, options: LayoutOptions) =>
    http.post<LayoutResult>(`/scripts/${scriptId}/layout`, options),
  timeline: (scriptId: string) => http.get<Timeline>(`/scripts/${scriptId}/timeline`),
  ungroup: (scriptId: string, ids: string[]) =>
    http.post<Dialogue[]>(`/scripts/${scriptId}/dialogues/ungroup`, { dialogue_ids: ids }),
};
