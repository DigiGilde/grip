"""Stored documents get an owner: the one object a document belongs to.

Revision ID: 0016_document_owner
Revises: 0015_outgoing_invoice
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_document_owner"
down_revision: str | None = "0015_outgoing_invoice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stored_document",
        sa.Column("owner_kind", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "stored_document",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # The documents that exist are signed quotes; each belongs to the
    # acceptance that refers to it.
    op.execute(
        """
        UPDATE stored_document AS d
        SET owner_kind = 'quote_acceptance', owner_id = a.id
        FROM quote_acceptance AS a
        WHERE a.document_ref = 'stored_document:' || d.id::text
        """
    )
    op.create_check_constraint(
        op.f("ck_stored_document_owner_complete"),
        "stored_document",
        "(owner_kind IS NULL) = (owner_id IS NULL)",
    )
    op.create_index(
        "ix_stored_document_owner",
        "stored_document",
        ["owner_kind", "owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stored_document_owner", table_name="stored_document")
    op.drop_constraint(
        op.f("ck_stored_document_owner_complete"), "stored_document", type_="check"
    )
    op.drop_column("stored_document", "owner_id")
    op.drop_column("stored_document", "owner_kind")
