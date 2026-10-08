"""The text of a quote: a draft per assignment, and where each text came from.

Revision ID: 0029_quote_draft
Revises: 0028_mail_outbox
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_quote_draft"
down_revision: str | None = "0028_mail_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quote_draft",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_quote_draft_assignment_id_assignment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["person.id"],
            name=op.f("fk_quote_draft_updated_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("assignment_id", name=op.f("pk_quote_draft")),
    )
    # Per section of an issued quote: written by a person, a standard text,
    # or drafted with a language model (which model, when, and that a person
    # settled it). Kept with the quote, outside its content.
    op.add_column(
        "quote",
        sa.Column("prose_provenance", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quote", "prose_provenance")
    op.drop_table("quote_draft")
