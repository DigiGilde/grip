"""Peer: whether the contract covers financial inspection.

Revision ID: 0006_peer_financial
Revises: 0005_stored_document
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_peer_financial"
down_revision: str | None = "0005_stored_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "peer",
        sa.Column(
            "financial_inspection",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("peer", "financial_inspection")
