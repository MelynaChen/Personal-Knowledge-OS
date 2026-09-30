"""Add sync recovery metadata.

Revision ID: 0002_sync_metadata
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_sync_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notion_objects", sa.Column("synced_content_hash", sa.String(length=64), nullable=True))
    op.add_column("sync_operations", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("sync_operations") as batch:
        batch.drop_column("last_error")
    with op.batch_alter_table("notion_objects") as batch:
        batch.drop_column("synced_content_hash")
