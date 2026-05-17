"""add traffic snapshots

Revision ID: 0003_traffic_snapshots
Revises: 0002_nodes
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_traffic_snapshots"
down_revision: str | None = "0002_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traffic_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("upload", sa.Integer(), nullable=False),
        sa.Column("download", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("expire_at", sa.String(length=64)),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_traffic_snapshots_id", "traffic_snapshots", ["id"])


def downgrade() -> None:
    op.drop_table("traffic_snapshots")
