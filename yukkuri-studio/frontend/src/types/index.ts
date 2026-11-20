// バックエンドのスキーマ(app/schemas)に対応する型。時間はすべてミリ秒。
export interface Project {
  id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface VideoInfo {
  id: string;
  project_id: string;
  original_filename: string;
  duration_ms: number;
  width: number;
  height: number;
  fps: number | null;
  created_at: string;
}

export interface Script {
  id: string;
  project_id: string;
  raw_text: string;
  version: number;
}

export interface VoiceSettings {
  pitch?: number;
  speed?: number;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  appearance: string;
  personality: string;
  speaking_style: string;
  voice_settings: VoiceSettings;
}

export type CharacterInput = Omit<Character, "id" | "project_id">;

export interface Dialogue {
  id: string; // dialogue_id
  character_id: string | null;
  order_index: number;
  text: string;
  emotion: string;
  start_ms: number | null;
  end_ms: number | null;
  generation_status: string;
  is_user_edited: boolean;
  simultaneous_group: string | null;
}

export type DialoguePatch = Partial<Pick<Dialogue, "text" | "character_id" | "emotion" | "start_ms" | "end_ms">>;

export interface ParseResult {
  dialogues: Dialogue[];
  created_characters: Character[];
}
