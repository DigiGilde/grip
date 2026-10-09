"""Records people edit in forms count their own changes.

A form sends the version it started from with a save; a save on top of
someone else's change is refused (grip.services.stale).

Revision ID: 0038_record_version
Revises: 0037_stored_document_made_from
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_record_version"
down_revision: str | None = "0037_stored_document_made_from"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "assignment",
    "budget_line",
    "allocation",
    "month_close",
    "cost_item",
    "invoice_line",
    "cost_coverage",
    "rate_card",
    "rate_band",
    "scale_band",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "version")
