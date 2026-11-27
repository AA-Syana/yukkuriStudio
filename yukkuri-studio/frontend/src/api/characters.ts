import type { Character, CharacterInput } from "../types";
import { http } from "./client";

/** ライブラリ(キャラクター管理画面)のキャラクター。 */
export const libraryApi = {
  list: () => http.get<Character[]>("/characters"),
  create: (input: Partial<CharacterInput> & { name: string }) => http.post<Character>("/characters", input),
  update: (id: string, input: Partial<CharacterInput>) => http.put<Character>(`/characters/${id}`, input),
  remove: (id: string) => http.del(`/characters/${id}`),
};

/** プロジェクト用のコピー(台本の編集画面)。追加した時点のライブラリの内容がコピーされ、以降は別物になる。 */
export const projectCharactersApi = {
  list: (projectId: string) => http.get<Character[]>(`/projects/${projectId}/characters`),
  add: (projectId: string, sourceCharacterId: string) =>
    http.post<Character>(`/projects/${projectId}/characters`, { source_character_id: sourceCharacterId }),
  update: (projectId: string, id: string, input: Partial<CharacterInput>) =>
    http.put<Character>(`/projects/${projectId}/characters/${id}`, input),
  remove: (projectId: string, id: string) => http.del(`/projects/${projectId}/characters/${id}`),
};
