"""add smart proxies

Revision ID: 0004_smart_proxies
Revises: 0003_traffic_snapshots
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_smart_proxies"
down_revision: str | None = "0003_traffic_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "smart_proxies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("proxy_type", sa.String(length=20), nullable=False),
        sa.Column("listen_host", sa.String(length=64), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("source_mode", sa.String(length=32), nullable=False),
        sa.Column("subscription_ids", sa.JSON(), nullable=False),
        sa.Column("country_codes", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("node_ids", sa.JSON(), nullable=False),
        sa.Column("protocol_types", sa.JSON(), nullable=False),
        sa.Column("health_check_url", sa.String(length=255), nullable=False),
        sa.Column("health_check_interval", sa.Integer(), nullable=False),
        sa.Column("tolerance", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80)),
        sa.Column("password", sa.String(length=120)),
        sa.Column("ip_whitelist", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_applied_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_smart_proxies_enabled", "smart_proxies", ["enabled"])
    op.create_index("ix_smart_proxies_id", "smart_proxies", ["id"])
    op.create_index("ix_smart_proxies_name", "smart_proxies", ["name"])
    op.create_index("ix_smart_proxies_port", "smart_proxies", ["port"], unique=True)
    op.create_index("ix_smart_proxies_proxy_type", "smart_proxies", ["proxy_type"])
    op.create_index("ix_smart_proxies_scenario", "smart_proxies", ["scenario"])
    op.create_index("ix_smart_proxies_source_mode", "smart_proxies", ["source_mode"])
    op.create_index("ix_smart_proxies_status", "smart_proxies", ["status"])
    op.create_index("ix_smart_proxies_strategy", "smart_proxies", ["strategy"])


def downgrade() -> None:
    op.drop_table("smart_proxies")
