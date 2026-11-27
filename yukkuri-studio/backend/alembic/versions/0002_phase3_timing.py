"""Phase 3: dialogues.timing_locked と、timeline_items の一意制約

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dialogues") as batch:
        batch.add_column(sa.Column("timing_locked", sa.Boolean, nullable=False, server_default=sa.false()))
    with op.batch_alter_table("timeline_items") as batch:
        batch.create_unique_constraint("uq_timeline_items_dialogue_track", ["dialogue_id", "track_type"])


def downgrade() -> None:
    with op.batch_alter_table("timeline_items") as batch:
        batch.drop_constraint("uq_timeline_items_dialogue_track", type_="unique")
    with op.batch_alter_table("dialogues") as batch:
        batch.drop_column("timing_locked")
