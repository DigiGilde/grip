"""A kept form remembers the values it was made from.

Revision ID: 0037_stored_document_made_from
Revises: 0036_billing_correction
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_stored_document_made_from"
down_revision: str | None = "0036_billing_correction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stored_document",
        sa.Column("made_from", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stored_document", "made_from")
