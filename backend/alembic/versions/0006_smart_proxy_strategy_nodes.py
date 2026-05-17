"""add smart proxy strategy node selection

Revision ID: 0006_smart_proxy_strategy_nodes
Revises: 0005_smart_proxy_apply_status
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_smart_proxy_strategy_nodes"
down_revision: str | None = "0005_smart_proxy_apply_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "smart_proxies",
        sa.Column("strategy_node_ids", sa.JSON(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("smart_proxies", "strategy_node_ids")
