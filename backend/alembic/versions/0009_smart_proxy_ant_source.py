"""add ant source fields to smart proxies

Revision ID: 0009_smart_proxy_ant_source
Revises: 0008_ant_proxy_states
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_smart_proxy_ant_source"
down_revision: str | None = "0008_ant_proxy_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "smart_proxies",
        sa.Column("data_source", sa.String(length=32), nullable=False, server_default="subscription"),
    )
    op.add_column("smart_proxies", sa.Column("ant_node_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("smart_proxies", sa.Column("ant_strategy_node_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.create_index(op.f("ix_smart_proxies_data_source"), "smart_proxies", ["data_source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_smart_proxies_data_source"), table_name="smart_proxies")
    op.drop_column("smart_proxies", "ant_strategy_node_ids")
    op.drop_column("smart_proxies", "ant_node_ids")
    op.drop_column("smart_proxies", "data_source")
