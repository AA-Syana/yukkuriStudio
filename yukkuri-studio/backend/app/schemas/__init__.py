"""APIの入出力スキーマ(Pydantic)。DBモデルをそのまま外に出さない。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("空にはできません")
    return value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- projects ----
class ProjectCreate(BaseModel):
    name: str = Field(max_length=200)
    _strip = field_validator("name")(_strip_required)


class ProjectUpdate(ProjectCreate):
    pass


class ProjectOut(ORMModel):
    id: str
    name: str
    status: str
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
class CharacterCreate(BaseModel):
    name: str = Field(max_length=100)
    appearance: str = ""
    personality: str = ""
    speaking_style: str = ""
    voice_settings: dict[str, Any] = Field(default_factory=dict)
    _strip = field_validator("name")(_strip_required)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    appearance: str | None = None
    personality: str | None = None
    speaking_style: str | None = None
    voice_settings: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _strip_required(v) if v is not None else v


class CharacterOut(ORMModel):
    id: str
    project_id: str
    name: str
    appearance: str
    personality: str
    speaking_style: str
    voice_settings: dict[str, Any]


# ---- script / dialogues ----
class ScriptOut(ORMModel):
    id: str
    project_id: str
    raw_text: str
    version: int


class ScriptUpdate(BaseModel):
    raw_text: str


class ParseRequest(BaseModel):
    force: bool = False


class DialogueOut(ORMModel):
    id: str  # dialogue_id
    character_id: str | None
    order_index: int
    text: str
    emotion: str
    start_ms: int | None
    end_ms: int | None
    generation_status: str
    is_user_edited: bool
    simultaneous_group: str | None


class ParseResult(BaseModel):
    dialogues: list[DialogueOut]
    created_characters: list[CharacterOut]


class DialogueCreate(BaseModel):
    text: str
    character_id: str | None = None
    emotion: str = "neutral"
    _strip = field_validator("text")(_strip_required)


class DialogueUpdate(BaseModel):
    text: str | None = None
    character_id: str | None = None
    emotion: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def _text(cls, v: str | None) -> str | None:
        return _strip_required(v) if v is not None else v

    @model_validator(mode="after")
    def _range(self):
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("終了時間は開始時間以降にしてください")
        return self


class DialogueIds(BaseModel):
    dialogue_ids: list[str] = Field(min_length=1)
