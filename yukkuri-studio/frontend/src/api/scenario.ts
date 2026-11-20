import type { Character, CharacterInput, Dialogue, DialoguePatch, ParseResult, Script } from "../types";
import { http } from "./client";

const base = (projectId: string) => `/projects/${projectId}`;

export const scenarioApi = {
  getScript: (pid: string) => http.get<Script>(`${base(pid)}/script`),
  saveScript: (pid: string, raw_text: string) => http.put<Script>(`${base(pid)}/script`, { raw_text }),
  parse: (pid: string, force: boolean) => http.post<ParseResult>(`${base(pid)}/script/parse`, { force }),

  listDialogues: (pid: string) => http.get<Dialogue[]>(`${base(pid)}/dialogues`),
  addDialogue: (pid: string, text: string, character_id: string | null) =>
    http.post<Dialogue>(`${base(pid)}/dialogues`, { text, character_id }),
  updateDialogue: (pid: string, id: string, patch: DialoguePatch) =>
    http.patch<Dialogue>(`${base(pid)}/dialogues/${id}`, patch),
  deleteDialogue: (pid: string, id: string) => http.del(`${base(pid)}/dialogues/${id}`),
  group: (pid: string, ids: string[]) => http.post<Dialogue[]>(`${base(pid)}/dialogues/group`, { dialogue_ids: ids }),
  ungroup: (pid: string, ids: string[]) => http.post<Dialogue[]>(`${base(pid)}/dialogues/ungroup`, { dialogue_ids: ids }),

  listCharacters: (pid: string) => http.get<Character[]>(`${base(pid)}/characters`),
  addCharacter: (pid: string, input: Partial<CharacterInput> & { name: string }) =>
    http.post<Character>(`${base(pid)}/characters`, input),
  updateCharacter: (pid: string, id: string, input: Partial<CharacterInput>) =>
    http.patch<Character>(`${base(pid)}/characters/${id}`, input),
  deleteCharacter: (pid: string, id: string) => http.del(`${base(pid)}/characters/${id}`),
};
