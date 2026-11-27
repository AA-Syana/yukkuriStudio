// バックエンドのスキーマ(app/schemas)に対応する型。時間はすべてミリ秒。
export interface User {
  id: string;
  email: string;
}

export interface Project {
  id: string;
  title: string;
  description: string;
  status: string;
  script_count: number;
  character_count: number;
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
  title: string;
  content: string;
  version: number;
  created_at: string;
  updated_at: string;
}

// 感情 = 立ち絵の表情。バックエンドの constants.EMOTIONS と同じ
export const EMOTIONS = ["neutral", "happy", "angry", "surprised", "sad"] as const;
export type Emotion = (typeof EMOTIONS)[number];
export const EMOTION_LABELS: Record<Emotion, string> = {
  neutral: "通常",
  happy: "笑顔",
  angry: "怒り",
  surprised: "驚き",
  sad: "悲しみ",
};

// 外見の入力項目。バックエンドの constants.APPEARANCE_FIELDS と同じキー
export const APPEARANCE_FIELDS = {
  gender: "性別・外見のイメージ",
  hair_style: "髪型",
  hair_color: "髪色",
  outfit: "服装",
  eye_color: "目の色",
  mood: "雰囲気",
  other: "その他の特徴",
} as const;
export type AppearanceKey = keyof typeof APPEARANCE_FIELDS;

export interface VoiceSettings {
  pitch?: number;
  speed?: number;
}

export interface CharacterImage {
  expression: Emotion;
  asset_id: string;
  source: "generated" | "uploaded";
}

/** project_id が null ならライブラリ(キャラクター管理画面)、あればそのプロジェクト用のコピー。 */
export interface Character {
  id: string;
  project_id: string | null;
  source_character_id: string | null;
  name: string;
  description: string;
  personality: string;
  appearance: string;
  appearance_details: Partial<Record<AppearanceKey, string>>;
  speaking_style: string;
  voice_settings: VoiceSettings;
  images: CharacterImage[];
  voice_sample_asset_id: string | null;
  voice_sample_stale: boolean | null;
  project_count: number;
  created_at: string;
  updated_at: string;
}

// 編集フォームで扱う項目(画像・音声サンプルは専用のAPIで更新する)
export type CharacterInput = Pick<
  Character,
  "name" | "description" | "personality" | "appearance" | "appearance_details" | "speaking_style" | "voice_settings"
>;

export interface Dialogue {
  id: string; // dialogue_id
  script_id: string;
  character_id: string | null;
  speaker_name: string | null; // 台本に書かれた話者名(キャラクター未登録でも残る)
  order_index: number;
  text: string;
  emotion: Emotion;
  start_ms: number | null;
  end_ms: number | null;
  generation_status: string;
  is_user_edited: boolean;
  simultaneous_group: string | null;
  audio_asset_id: string | null;
  audio_duration_ms: number | null;
  audio_stale: boolean | null; // 生成後にセリフ・感情・声の設定が変わった(再生成が必要)
  suggestion: string | null; // AI解析の改善案
  timing_locked: boolean; // 時間を手動指定している(自動配置で動かさない)
  timing_stale: boolean; // 未配置、または音声の長さとずれている(再配置が必要)
}

export type DialoguePatch = Partial<
  Pick<Dialogue, "text" | "character_id" | "emotion" | "start_ms" | "end_ms" | "timing_locked">
>;

export interface LayoutOptions {
  gap_ms: number;
  start_ms: number;
  overwrite_locked: boolean;
}

export type TrackType = "audio" | "character" | "subtitle";

export interface TimelineItem {
  id: string;
  dialogue_id: string;
  track_type: TrackType;
  start_ms: number;
  end_ms: number;
  position_x: number; // 画面に対する割合(0〜1、項目の中心)
  position_y: number;
  scale: number;
  volume: number;
  playback_speed: number;
  font_size: number | null; // 字幕の文字サイズ(1080p換算のpx)。null なら既定
  expression: Emotion | null; // 立ち絵の表情。null ならセリフの感情に従う
  text_override: string | null; // 字幕テキスト。null ならセリフのテキスト
  times_edited: boolean; // 開始/終了を手で変えた(自動配置で動かさない)
  text: string; // セリフのテキスト
  speaker_name: string | null;
  character_id: string | null;
  emotion: Emotion; // セリフの感情(表情の既定)
  audio_asset_id: string | null;
  audio_duration_ms: number | null;
}

export type TimelineItemPatch = Partial<
  Pick<
    TimelineItem,
    | "start_ms" | "end_ms" | "position_x" | "position_y" | "scale" | "volume" | "playback_speed"
    | "font_size" | "expression" | "text_override"
  >
>;

export interface HistoryState {
  can_undo: boolean;
  can_redo: boolean;
  undo_label: string | null;
  redo_label: string | null;
}

export interface Timeline {
  script_id: string;
  total_ms: number;
  items: TimelineItem[];
  warnings: string[];
}

export interface LayoutResult {
  dialogues: Dialogue[];
  timeline: Timeline;
}

export interface UnknownSpeaker {
  name: string;
  count: number;
  library_character_id: string | null; // ライブラリに同名のキャラクターがあればそのID
}

export interface ParseResult {
  dialogues: Dialogue[];
  unknown_speakers: UnknownSpeaker[];
  speakerless_lines: number;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job {
  id: string;
  project_id: string | null; // キャラクター単体の生成ではプロジェクトなし
  job_type: string;
  target_id: string | null;
  status: JobStatus;
  progress: number;
  error: string | null;
  created_at: string;
}

export const isActive = (job: Job) => job.status === "queued" || job.status === "running";

// ---- 動画の書き出し(Phase 5) ----
export interface RenderOptions {
  script_id: string | null;
  height: 480 | 720 | 1080 | null; // null = 元動画と同じ(元動画が無ければ1080)
  include_original_audio: boolean;
  original_volume: number;
}

export interface RenderFile {
  job_id: string;
  script_id: string;
  finished_at: string;
  size_bytes: number;
  width: number;
  height: number;
  duration_ms: number;
  warnings: string[];
}

export interface RenderStatus {
  job: Job | null; // 直近の書き出し(実行中・失敗も含む)
  last_success: RenderFile | null; // ダウンロードできる最新の書き出し
}
