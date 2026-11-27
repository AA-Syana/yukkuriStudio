"""DBモデル(Ver.2.0)。時間はすべて整数ミリ秒(_ms)で保持する。

テーブルの変更は必ず Alembic のマイグレーションで行う(backend/alembic/versions)。

仕様書との意図的な差異:
  - 時間の列は `_ms` を付けて単位を明示している(duration → duration_ms など)
  - character_assets は assets に統合している(assets.character_id / dialogue_id のどちらかを持つ)
  - キャラクターは「ライブラリ(project_id が空)」と「プロジェクト用のコピー(project_id あり)」を同じ表に持つ。
    「編集画面(プロジェクト側)の状態を優先し、ライブラリの編集は次回以降の制作から反映する」という要件のため。
    仕様書の project_characters(紐づけ表)は、この方式では不要になるので作っていない。
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.database import Base

# PostgreSQLではJSONB、SQLite(テスト)では通常のJSON
JsonType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class UserSession(Base):
    """ログインセッション。DBにはトークンのハッシュだけを保存する。"""

    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    video: Mapped[Optional["Video"]] = relationship(uselist=False, cascade="all, delete-orphan")
    scripts: Mapped[list["Script"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Script.created_at"
    )
    # このプロジェクトで使うキャラクター。ライブラリから追加した時点のコピーで、以降はプロジェクト側の状態が優先される
    characters: Mapped[list["Character"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Character.created_at", lazy="selectin"
    )
    jobs: Mapped[list["GenerationJob"]] = relationship(cascade="all, delete", passive_deletes=True)
    timeline_items: Mapped[list["TimelineItem"]] = relationship(cascade="all, delete", passive_deletes=True)
    edit_histories: Mapped[list["EditHistory"]] = relationship(cascade="all, delete", passive_deletes=True)


    @property
    def script_count(self) -> int:
        return len(self.scripts)

    @property
    def character_count(self) -> int:
        return len(self.characters)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))  # storage root からの相対パス
    duration_ms: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _created()


class Script(Base):
    __tablename__ = "scripts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    project: Mapped["Project"] = relationship(back_populates="scripts")
    dialogues: Mapped[list["Dialogue"]] = relationship(
        back_populates="script", cascade="all, delete-orphan", order_by="Dialogue.order_index"
    )


class Character(Base):
    """キャラクター。2種類の行を同じ表に持つ。

      ライブラリのキャラクター: project_id が空。キャラクター管理画面で作る(ユーザーの持ち物)
      プロジェクト用のコピー:   project_id あり。ライブラリから追加した時点のコピーで、source_character_id に元を覚える

    セリフの話者(dialogues.character_id)は、プロジェクト用のコピーを指す。ライブラリを編集・削除しても
    コピーには影響しない(次にプロジェクトへ追加するときから、新しい内容が反映される)。
    """

    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_characters_project_name"),  # project_id が空(ライブラリ)は対象外
        # ライブラリ内での名前の重複を禁止する(部分インデックス)
        Index(
            "uq_characters_library_name", "user_id", "name", unique=True,
            postgresql_where=sql_text("project_id IS NULL"), sqlite_where=sql_text("project_id IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    appearance: Mapped[str] = mapped_column(Text, default="")  # 自由記述
    appearance_details: Mapped[dict] = mapped_column(JsonType, default=dict)  # constants.APPEARANCE_FIELDS のキー
    speaking_style: Mapped[str] = mapped_column(Text, default="")
    voice_settings: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    project: Mapped[Optional["Project"]] = relationship(back_populates="characters")
    # このキャラクターから作られたコピー(参照のみ。ライブラリを消してもコピーは残る)
    copies: Mapped[list["Character"]] = relationship(foreign_keys="Character.source_character_id", viewonly=True)
    # 画像(表情差分)と音声サンプル。meta["expression"] が表情キー
    assets: Mapped[list["Asset"]] = relationship(
        cascade="all, delete", foreign_keys="Asset.character_id", lazy="selectin"
    )

    @property
    def is_library(self) -> bool:
        return self.project_id is None

    @property
    def images(self) -> list[dict]:
        return [
            {"expression": a.meta.get("expression"), "asset_id": a.id, "source": a.meta.get("source", "generated")}
            for a in self.assets
            if a.asset_type == "image"
        ]

    @property
    def voice_sample_asset_id(self) -> Optional[str]:
        a = next((a for a in self.assets if a.asset_type == "voice_sample"), None)
        return a.id if a else None

    @property
    def voice_sample_stale(self) -> Optional[bool]:
        """音声サンプルが無ければNone。生成後に声の設定が変わっていればTrue。"""
        a = next((a for a in self.assets if a.asset_type == "voice_sample"), None)
        if a is None:
            return None
        return (a.meta.get("voice_settings") or {}) != (self.voice_settings or {})

    @property
    def project_count(self) -> int:
        """(ライブラリ用)このキャラクターをコピーして使っているプロジェクトの数。"""
        return len({c.project_id for c in self.copies}) if self.is_library else 0


class Dialogue(Base):
    """セリフ。dialogue_id(=id)が音声・画像・字幕を結びつけるキーになる。

    is_user_edited: ユーザーが手動で触ったセリフ。AIの再生成/再解析で勝手に上書きしないための印。
    simultaneous_group: 同じ値を持つセリフは「同時会話」として扱う(UI操作で設定)。
    speaker_name: シナリオに書かれた話者名。キャラクター未登録の間も残り、登録時に紐づけ直せる。
    """

    __tablename__ = "dialogues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    script_id: Mapped[str] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    speaker_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    emotion: Mapped[str] = mapped_column(String(30), default="neutral")
    start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generation_status: Mapped[str] = mapped_column(String(30), default="pending")
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    simultaneous_group: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # 時間を手動で指定したセリフ。自動配置(レイアウト)で動かさない
    timing_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))

    # 一覧取得時のN+1を避けるため selectin で読み込む
    script: Mapped["Script"] = relationship(back_populates="dialogues")
    character: Mapped[Optional["Character"]] = relationship(lazy="selectin")
    assets: Mapped[list["Asset"]] = relationship(
        cascade="all, delete", foreign_keys="Asset.dialogue_id", lazy="selectin"
    )
    suggestion_row: Mapped[Optional["DialogueSuggestion"]] = relationship(
        uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def audio_asset(self) -> Optional["Asset"]:
        return next((a for a in self.assets if a.asset_type == "audio"), None)

    @property
    def audio_asset_id(self) -> Optional[str]:
        a = self.audio_asset
        return a.id if a else None

    @property
    def audio_duration_ms(self) -> Optional[int]:
        a = self.audio_asset
        return a.meta.get("duration_ms") if a else None

    @property
    def audio_stale(self) -> Optional[bool]:
        """音声が無い場合はNone。生成後にセリフ・感情・声の設定が変わっていればTrue(再生成が必要)。"""
        a = self.audio_asset
        if a is None:
            return None
        voice = (self.character.voice_settings if self.character else None) or {}
        m = a.meta
        return not (
            m.get("text") == self.text
            and m.get("emotion") == self.emotion
            and (m.get("voice_settings") or {}) == voice
        )

    @property
    def suggestion(self) -> Optional[str]:
        return self.suggestion_row.text if self.suggestion_row else None

    @property
    def timing_stale(self) -> bool:
        """時間が未配置、または音声の長さと食い違っている(自動配置のやり直しが必要)。手動指定のセリフは対象外。"""
        if self.start_ms is None or self.end_ms is None:
            return True
        if self.timing_locked:
            return False
        duration = self.audio_duration_ms
        return duration is not None and (self.end_ms - self.start_ms) != max(100, duration)


class Asset(Base):
    """生成・アップロードされた音声/画像。dialogue_id(セリフの音声) か character_id(キャラクターの画像・音声サンプル)のどちらかを持つ。"""

    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dialogue_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dialogues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(30))  # audio / image / voice_sample
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)


class TimelineItem(Base):
    """タイムライン上の1項目。Phase 3 では自動配置の結果(音声・立ち絵・字幕)を保持する。

    1つのセリフにつき track_type ごとに最大1件。位置は画面に対する割合(0.0〜1.0、項目の中心)。
    """

    __tablename__ = "timeline_items"
    __table_args__ = (UniqueConstraint("dialogue_id", "track_type", name="uq_timeline_items_dialogue_track"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dialogue_id: Mapped[str] = mapped_column(ForeignKey("dialogues.id", ondelete="CASCADE"))
    track_type: Mapped[str] = mapped_column(String(30))  # audio / character / subtitle
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)
    scale: Mapped[float] = mapped_column(Float, default=1.0)
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    playback_speed: Mapped[float] = mapped_column(Float, default=1.0)
    # --- Phase 4 ---
    font_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 字幕。空なら既定(1080p換算で40)
    expression: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # 立ち絵。空ならセリフの感情に従う
    text_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 字幕。空ならセリフのテキスト
    # 開始/終了を手で変えた項目。自動配置でも動かさない
    times_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))


class GenerationJob(Base):
    """AI生成ジョブ。キャラクター単体の生成(画像・音声サンプル)にはプロジェクトが無いので project_id は空でよい。"""

    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # --- Phase 5 ---
    params: Mapped[Optional[dict]] = mapped_column(JsonType, nullable=True)  # 実行時の設定(書き出しの画質など)。再実行でも使う
    result: Mapped[Optional[dict]] = mapped_column(JsonType, nullable=True)  # 結果(書き出したファイル、警告など)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class EditHistory(Base):
    """編集履歴(元に戻す/やり直し用)。before_data / after_data は、影響を受けたセリフと項目の状態の丸ごとの記録。

    seq: プロジェクト内の通し番号。undone: 「元に戻す」済み(やり直し待ち)。新しい編集をすると、やり直し待ちは破棄する。
    """

    __tablename__ = "edit_histories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    operation_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    before_data: Mapped[dict] = mapped_column(JsonType, default=dict)
    after_data: Mapped[dict] = mapped_column(JsonType, default=dict)
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"))
    undone: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    created_at: Mapped[datetime] = _created()


class DialogueSuggestion(Base):
    """AI解析が出したセリフの改善案(1セリフにつき最新の1件)。"""

    __tablename__ = "dialogue_suggestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dialogue_id: Mapped[str] = mapped_column(ForeignKey("dialogues.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
