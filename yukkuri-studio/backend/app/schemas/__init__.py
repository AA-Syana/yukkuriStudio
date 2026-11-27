"""APIの入出力スキーマ(Pydantic)。DBモデルをそのまま外に出さない。"""
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import APPEARANCE_FIELDS, EMOTIONS

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_emotion(value: str | None) -> str | None:
    if value is not None and value not in EMOTIONS:
        raise ValueError(f"emotion は {', '.join(EMOTIONS)} のいずれかにしてください")
    return value


def _strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("空にはできません")
    return value


def _strip_optional(value: str | None) -> str | None:
    return _strip_required(value) if value is not None else value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("メールアドレスの形式が正しくありません")
        return v


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class UserOut(ORMModel):
    id: str
    email: str


# ---- projects ----
class ProjectCreate(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(default="", max_length=2000)
    _strip = field_validator("title")(_strip_required)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    _strip = field_validator("title")(_strip_optional)


class ProjectOut(ORMModel):
    id: str
    title: str
    description: str
    status: str
    script_count: int
    character_count: int
    created_at: datetime
    updated_at: datetime


# ---- videos ----
class VideoOut(ORMModel):
    id: str
    project_id: str
    original_filename: str
    duration_ms: int
    width: int
    height: int
    fps: float | None
    created_at: datetime


# ---- characters ----
def _check_details(value: dict[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return value
    unknown = set(value) - set(APPEARANCE_FIELDS)
    if unknown:
        raise ValueError(f"未対応の外見項目です: {', '.join(sorted(unknown))}")
    if any(len(v) > 200 for v in value.values()):
        raise ValueError("外見の各項目は200文字以内にしてください")
    return value


class CharacterCreate(BaseModel):
    name: str = Field(max_length=100)
    description: str = ""
    personality: str = ""
    appearance: str = ""
    appearance_details: dict[str, str] = Field(default_factory=dict)
    speaking_style: str = ""
    voice_settings: dict[str, Any] = Field(default_factory=dict)
    _strip = field_validator("name")(_strip_required)
    _details = field_validator("appearance_details")(_check_details)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    personality: str | None = None
    appearance: str | None = None
    appearance_details: dict[str, str] | None = None
    speaking_style: str | None = None
    voice_settings: dict[str, Any] | None = None
    _strip = field_validator("name")(_strip_optional)
    _details = field_validator("appearance_details")(_check_details)


class CharacterImageOut(BaseModel):
    expression: str
    asset_id: str
    source: str  # generated / uploaded


class CharacterOut(ORMModel):
    id: str
    project_id: str | None  # 空ならライブラリ、あればそのプロジェクト用のコピー
    source_character_id: str | None  # コピー元のライブラリのキャラクター(削除されていれば空)
    name: str
    description: str
    personality: str
    appearance: str
    appearance_details: dict[str, Any]
    speaking_style: str
    voice_settings: dict[str, Any]
    images: list[CharacterImageOut] = Field(default_factory=list)
    voice_sample_asset_id: str | None
    voice_sample_stale: bool | None
    project_count: int  # ライブラリのみ。コピーして使っているプロジェクトの数
    created_at: datetime
    updated_at: datetime


class ProjectCharacterAdd(BaseModel):
    source_character_id: str


# ---- scripts / dialogues ----
class ScriptCreate(BaseModel):
    title: str = Field(default="", max_length=100)
    content: str = ""


class ScriptUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    content: str | None = None


class ScriptOut(ORMModel):
    id: str
    project_id: str
    title: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime


class ParseRequest(BaseModel):
    force: bool = False


class DialogueOut(ORMModel):
    id: str  # dialogue_id
    script_id: str
    character_id: str | None
    speaker_name: str | None
    order_index: int
    text: str
    emotion: str
    start_ms: int | None
    end_ms: int | None
    generation_status: str
    is_user_edited: bool
    simultaneous_group: str | None
    audio_asset_id: str | None
    audio_duration_ms: int | None
    audio_stale: bool | None  # 生成後にセリフ・感情・声の設定が変わっていればTrue
    suggestion: str | None  # AI解析の改善案
    timing_locked: bool  # 時間を手動指定している(自動配置で動かさない)
    timing_stale: bool  # 未配置、または音声の長さとずれている(再配置が必要)


class UnknownSpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    count: int  # その話者のセリフ数
    library_character_id: str | None  # ライブラリに同名のキャラクターがあれば、そのID(「追加」ボタン用)


class ParseResult(BaseModel):
    dialogues: list[DialogueOut]
    unknown_speakers: list[UnknownSpeakerOut]  # プロジェクトに未登録の話者(警告)
    speakerless_lines: int  # 話者が決まらないセリフの数(最初の [話者] より前の行など)


class DialogueCreate(BaseModel):
    text: str
    character_id: str | None = None
    emotion: str = "neutral"
    _strip = field_validator("text")(_strip_required)
    _emotion = field_validator("emotion")(_check_emotion)


class DialogueUpdate(BaseModel):
    text: str | None = None
    character_id: str | None = None
    emotion: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    timing_locked: bool | None = None  # false にすると手動指定を解除する(次の自動配置で動く)
    _text = field_validator("text")(_strip_optional)
    _emotion = field_validator("emotion")(_check_emotion)

    @model_validator(mode="after")
    def _range(self):
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("終了時間は開始時間以降にしてください")
        return self


class DialogueIds(BaseModel):
    dialogue_ids: list[str] = Field(min_length=1)


# ---- generation jobs ----
class JobOut(ORMModel):
    id: str
    project_id: str | None  # キャラクター単体の生成(画像・音声サンプル)ではプロジェクトなし
    job_type: str
    target_id: str | None
    status: str  # queued / running / succeeded / failed
    progress: int
    error: str | None
    created_at: datetime


class ProjectGenerateRequest(BaseModel):
    script_id: str


class ImageGenerateRequest(BaseModel):
    expression: str | None = None  # 省略すると全表情を生成する
    _emotion = field_validator("expression")(_check_emotion)


# ---- timing / timeline (Phase 3) ----
class LayoutRequest(BaseModel):
    gap_ms: int = Field(default=300, ge=0, le=10_000)  # セリフ間の無音
    start_ms: int = Field(default=0, ge=0)
    overwrite_locked: bool = False  # trueなら手動指定の時間も振り直す


class TimelineItemOut(BaseModel):
    id: str
    dialogue_id: str
    track_type: str  # audio / character / subtitle
    start_ms: int
    end_ms: int
    position_x: float
    position_y: float
    scale: float
    volume: float
    playback_speed: float
    font_size: int | None  # 字幕の文字サイズ(1080p換算のpx)。空なら既定
    expression: str | None  # 立ち絵の表情。空ならセリフの感情に従う
    text_override: str | None  # 字幕テキスト。空ならセリフのテキスト
    times_edited: bool  # 開始/終了を手で変えた(自動配置で動かさない)
    text: str  # セリフのテキスト
    speaker_name: str | None
    character_id: str | None
    emotion: str  # セリフの感情(表情の既定)
    audio_asset_id: str | None
    audio_duration_ms: int | None


class TimelineItemUpdate(BaseModel):
    """送った項目だけを更新する。expression / text_override / font_size は null で「既定に戻す」。"""

    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    position_x: float | None = Field(default=None, ge=0, le=1)
    position_y: float | None = Field(default=None, ge=0, le=1)
    scale: float | None = Field(default=None, ge=0.1, le=5)
    volume: float | None = Field(default=None, ge=0, le=2)
    playback_speed: float | None = Field(default=None, ge=0.5, le=2)
    font_size: int | None = Field(default=None, ge=8, le=200)
    expression: str | None = None
    text_override: str | None = Field(default=None, max_length=500)
    _expression = field_validator("expression")(_check_emotion)

    @field_validator("text_override")
    @classmethod
    def _blank_is_default(cls, v: str | None) -> str | None:
        return v if v is None or v.strip() else None  # 空文字は「既定(セリフのテキスト)に戻す」


class HistoryStateOut(BaseModel):
    can_undo: bool
    can_redo: bool
    undo_label: str | None
    redo_label: str | None


class TimelineOut(BaseModel):
    script_id: str
    total_ms: int
    items: list[TimelineItemOut]
    warnings: list[str]


class LayoutOut(BaseModel):
    dialogues: list[DialogueOut]
    timeline: TimelineOut


# ---- render (Phase 5) ----
class RenderRequest(BaseModel):
    script_id: str | None = None  # 省略すると、プロジェクトの最初の台本
    height: int | None = None  # 出力の高さ(480/720/1080)。省略すると元動画と同じ(元動画が無ければ1080)
    include_original_audio: bool = True  # 元動画の音を含める
    original_volume: float = Field(default=1.0, ge=0, le=2)

    @field_validator("height")
    @classmethod
    def _height(cls, v: int | None) -> int | None:
        if v is not None and v not in (480, 720, 1080):
            raise ValueError("height は 480 / 720 / 1080 のいずれかにしてください")
        return v


class RenderFileOut(BaseModel):
    job_id: str
    script_id: str
    finished_at: datetime
    size_bytes: int
    width: int
    height: int
    duration_ms: int
    warnings: list[str]


class RenderStatusOut(BaseModel):
    job: JobOut | None  # 直近の書き出しジョブ(実行中・失敗も含む)
    last_success: RenderFileOut | None  # ダウンロードできる最新の書き出し結果
