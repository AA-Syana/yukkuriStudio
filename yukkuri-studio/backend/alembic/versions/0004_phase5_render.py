"""Phase 5: generation_jobs に params(実行時の設定)と result(結果)を追加

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("params", JSON, nullable=True))
        batch.add_column(sa.Column("result", JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_column("result")
        batch.drop_column("params")
