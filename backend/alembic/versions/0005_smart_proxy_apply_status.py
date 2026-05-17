"""track smart proxy config apply state

Revision ID: 0005_smart_proxy_apply_status
Revises: 0004_smart_proxies
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_smart_proxy_apply_status"
down_revision: str | None = "0004_smart_proxies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "smart_proxies",
        sa.Column("config_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.execute(
        "UPDATE smart_proxies "
        "SET config_updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
        "WHERE config_updated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("smart_proxies", "config_updated_at")
