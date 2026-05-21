"""add ant proxy state table

Revision ID: 0008_ant_proxy_states
Revises: 0007_smart_proxy_stability_priority
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_ant_proxy_states"
down_revision: str | None = "0007_smart_proxy_stability_priority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ant_proxy_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_ant_proxy_states_id"), "ant_proxy_states", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ant_proxy_states_id"), table_name="ant_proxy_states")
    op.drop_table("ant_proxy_states")
