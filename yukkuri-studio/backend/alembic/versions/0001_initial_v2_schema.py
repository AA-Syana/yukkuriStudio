"""Ver.2.0 初期スキーマ(ユーザー・ログインセッション・プロジェクト・台本・キャラクター ほか)

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        _ts("created_at"),
        _ts("expires_at"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("fps", sa.Float, nullable=True),
        _ts("created_at"),
    )

    op.create_table(
        "scripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_scripts_project_id", "scripts", ["project_id"])

    # キャラクター: project_id が空=ライブラリ / あり=そのプロジェクト用のコピー(source_character_id がコピー元)
    op.create_table(
        "characters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("personality", sa.Text, nullable=False),
        sa.Column("appearance", sa.Text, nullable=False),
        sa.Column("appearance_details", JSON, nullable=False),
        sa.Column("speaking_style", sa.Text, nullable=False),
        sa.Column("voice_settings", JSON, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("project_id", "name", name="uq_characters_project_name"),
    )
    op.create_index("ix_characters_user_id", "characters", ["user_id"])
    op.create_index("ix_characters_project_id", "characters", ["project_id"])
    op.create_index("ix_characters_source_character_id", "characters", ["source_character_id"])
    # ライブラリ内の名前の重複を禁止する(project_id が空の行だけが対象の部分インデックス)
    op.create_index(
        "uq_characters_library_name", "characters", ["user_id", "name"], unique=True,
        postgresql_where=sa.text("project_id IS NULL"), sqlite_where=sa.text("project_id IS NULL"),
    )

    op.create_table(
        "dialogues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("script_id", sa.String(36), sa.ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("speaker_name", sa.String(100), nullable=True),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("emotion", sa.String(30), nullable=False),
        sa.Column("start_ms", sa.Integer, nullable=True),
        sa.Column("end_ms", sa.Integer, nullable=True),
        sa.Column("generation_status", sa.String(30), nullable=False),
        sa.Column("is_user_edited", sa.Boolean, nullable=False),
        sa.Column("simultaneous_group", sa.String(36), nullable=True),
    )
    op.create_index("ix_dialogues_script_id", "dialogues", ["script_id"])

    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialogue_id", sa.String(36), sa.ForeignKey("dialogues.id", ondelete="CASCADE"), nullable=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=True),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("metadata", JSON, nullable=False),
    )
    op.create_index("ix_assets_dialogue_id", "assets", ["dialogue_id"])
    op.create_index("ix_assets_character_id", "assets", ["character_id"])

    op.create_table(
        "timeline_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dialogue_id", sa.String(36), sa.ForeignKey("dialogues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_type", sa.String(30), nullable=False),
        sa.Column("start_ms", sa.Integer, nullable=False),
        sa.Column("end_ms", sa.Integer, nullable=False),
        sa.Column("position_x", sa.Float, nullable=False),
        sa.Column("position_y", sa.Float, nullable=False),
        sa.Column("scale", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("playback_speed", sa.Float, nullable=False),
    )
    op.create_index("ix_timeline_items_project_id", "timeline_items", ["project_id"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Integer, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_generation_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])

    op.create_table(
        "edit_histories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("before_data", JSON, nullable=False),
        sa.Column("after_data", JSON, nullable=False),
        _ts("created_at"),
    )
    op.create_index("ix_edit_histories_project_id", "edit_histories", ["project_id"])

    op.create_table(
        "dialogue_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialogue_id", sa.String(36), sa.ForeignKey("dialogues.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("text", sa.Text, nullable=False),
        _ts("created_at"),
    )


def downgrade() -> None:
    for table in (
        "dialogue_suggestions", "edit_histories", "generation_jobs", "timeline_items", "assets", "dialogues",
        "characters", "scripts", "videos", "projects", "sessions", "users",
    ):
        op.drop_table(table)
