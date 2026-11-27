"""Phase 4: timeline_items の編集項目(字幕サイズ・表情・字幕テキスト・時間の手動編集印)と、edit_histories の seq/undone

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("timeline_items") as batch:
        batch.add_column(sa.Column("font_size", sa.Integer, nullable=True))
        batch.add_column(sa.Column("expression", sa.String(30), nullable=True))
        batch.add_column(sa.Column("text_override", sa.Text, nullable=True))
        batch.add_column(sa.Column("times_edited", sa.Boolean, nullable=False, server_default=sa.false()))
    with op.batch_alter_table("edit_histories") as batch:
        batch.add_column(sa.Column("seq", sa.Integer, nullable=False, server_default="0"))
        batch.add_column(sa.Column("undone", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("edit_histories") as batch:
        batch.drop_column("undone")
        batch.drop_column("seq")
    with op.batch_alter_table("timeline_items") as batch:
        batch.drop_column("times_edited")
        batch.drop_column("text_override")
        batch.drop_column("expression")
        batch.drop_column("font_size")
