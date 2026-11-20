"""DBモデル。時間はすべて整数ミリ秒(_ms)で保持する。

Phase 1で実際にAPIが使うのは projects / videos / scripts / dialogues / characters。
assets / timeline_items / generation_jobs / edit_histories / users は
後続Phaseのためにテーブル定義のみ先に用意している。
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.database import Base

# PostgreSQLではJSONB、SQLite(テスト)では通常のJSON
JsonType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Phase 6まで未使用。projects.user_id をnull可にして後付けできるようにしてある。"""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    video: Mapped[Optional["Video"]] = relationship(uselist=False, cascade="all, delete-orphan")
    script: Mapped[Optional["Script"]] = relationship(uselist=False, cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship(
        cascade="all, delete-orphan", order_by="Character.created_at"
    )


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))  # storage root からの相対パス
    duration_ms: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Script(Base):
    __tablename__ = "scripts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)

    dialogues: Mapped[list["Dialogue"]] = relationship(
        cascade="all, delete-orphan", order_by="Dialogue.order_index"
    )


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(100))
    appearance: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    speaking_style: Mapped[str] = mapped_column(Text, default="")
    voice_settings: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Dialogue(Base):
    """セリフ。dialogue_id(=id)が音声・画像・字幕を結びつけるキーになる。

    is_user_edited: ユーザーが手動で触ったセリフ。AIの再生成/再解析で勝手に上書きしないための印。
    simultaneous_group: 同じ値を持つセリフは「同時会話」として扱う(UI操作で設定)。
    """

    __tablename__ = "dialogues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    script_id: Mapped[str] = mapped_column(ForeignKey("scripts.id"))
    character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    emotion: Mapped[str] = mapped_column(String(30), default="neutral")
    start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generation_status: Mapped[str] = mapped_column(String(30), default="pending")
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    simultaneous_group: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dialogue_id: Mapped[Optional[str]] = mapped_column(ForeignKey("dialogues.id"), nullable=True)
    character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(30))  # audio / image / subtitle
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)


class TimelineItem(Base):
    __tablename__ = "timeline_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dialogue_id: Mapped[str] = mapped_column(ForeignKey("dialogues.id"))
    track_id: Mapped[str] = mapped_column(String(64))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    position: Mapped[dict] = mapped_column(JsonType, default=dict)
    scale: Mapped[float] = mapped_column(Float, default=1.0)
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    playback_speed: Mapped[float] = mapped_column(Float, default=1.0)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    job_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EditHistory(Base):
    __tablename__ = "edit_histories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    operation: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
