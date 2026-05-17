"""add smart proxy stability priority

Revision ID: 0007_smart_proxy_stability_priority
Revises: 0006_smart_proxy_strategy_nodes
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_smart_proxy_stability_priority"
down_revision: str | None = "0006_smart_proxy_strategy_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "smart_proxies",
        sa.Column("stability_priority", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("smart_proxies", "stability_priority")
