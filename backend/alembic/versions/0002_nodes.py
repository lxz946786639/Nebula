"""add persistent node pool

Revision ID: 0002_nodes
Revises: 0001_initial
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_nodes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("server", sa.String(length=255)),
        sa.Column("port", sa.String(length=32)),
        sa.Column("type", sa.String(length=64)),
        sa.Column("uuid", sa.String(length=255)),
        sa.Column("password", sa.String(length=255)),
        sa.Column("tls", sa.Boolean(), nullable=False),
        sa.Column("network", sa.String(length=64)),
        sa.Column("country", sa.String(length=80)),
        sa.Column("city", sa.String(length=120)),
        sa.Column("country_code", sa.String(length=16)),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("latency", sa.Integer()),
        sa.Column("source_subscription_id", sa.Integer()),
        sa.Column("source_subscription_name", sa.String(length=120)),
        sa.Column("source_group", sa.String(length=80)),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_nodes_country_code", "nodes", ["country_code"])
    op.create_index("ix_nodes_country", "nodes", ["country"])
    op.create_index("ix_nodes_enabled", "nodes", ["enabled"])
    op.create_index("ix_nodes_id", "nodes", ["id"])
    op.create_index("ix_nodes_identity", "nodes", ["identity"], unique=True)
    op.create_index("ix_nodes_name", "nodes", ["name"])
    op.create_index("ix_nodes_network", "nodes", ["network"])
    op.create_index("ix_nodes_server", "nodes", ["server"])
    op.create_index("ix_nodes_source_group", "nodes", ["source_group"])
    op.create_index("ix_nodes_source_subscription_id", "nodes", ["source_subscription_id"])
    op.create_index("ix_nodes_source_subscription_name", "nodes", ["source_subscription_name"])
    op.create_index("ix_nodes_type", "nodes", ["type"])


def downgrade() -> None:
    op.drop_table("nodes")
