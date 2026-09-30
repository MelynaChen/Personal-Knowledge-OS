"""Add local daily task progress status.

Revision ID: 0003_task_status
Revises: 0002_sync_metadata
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_task_status"
down_revision = "0002_sync_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("status", sa.String(length=20),
                                     nullable=False, server_default="Not started"))


def downgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("status")
