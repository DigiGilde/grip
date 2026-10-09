"""A vacancy text follows the facts of its vacancy until it is settled.

A draft names a fact by key; settling freezes the values. The settled row
keeps the draft it came from and the values that were filled in, so a later
change of a fact can be shown next to what the text says.

A vacancy for a known candidate gets no vacancy text unless someone chose to
write one.

Revision ID: 0041_text_facts
Revises: 0040_record_version_everywhere
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_text_facts"
down_revision: str | None = "0040_record_version_everywhere"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vacancy_text", sa.Column("keyed_body", sa.Text(), nullable=True))
    op.add_column(
        "vacancy_text",
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "vacancy",
        sa.Column(
            "wants_text", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    op.drop_column("vacancy", "wants_text")
    op.drop_column("vacancy_text", "facts")
    op.drop_column("vacancy_text", "keyed_body")
