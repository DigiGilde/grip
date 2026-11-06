"""Peer: whether it is an example instance (ADR 0054).

Revision ID: 0044_peer_is_example
Revises: 0043_cost_item_executor
Create Date: 2026-10-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_peer_is_example"
down_revision: str | None = "0043_cost_item_executor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "peer",
        sa.Column(
            "is_example",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("peer", "is_example")
