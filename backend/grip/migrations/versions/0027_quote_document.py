"""Quote: the file is fixed once; when and how is recorded.

The columns for the reference to the stored file and its hash existed and
were unused for a quote. A quote from before this migration has no file; it
gets one the first time it is asked for, marked as fixed afterwards.

Revision ID: 0027_quote_document
Revises: 0026_event_stream
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_quote_document"
down_revision: str | None = "0026_event_stream"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quote",
        sa.Column("document_fixed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "quote", sa.Column("document_origin", sa.String(length=12), nullable=True)
    )
    # Nothing used these two columns for a quote; clear any stray value so
    # the rule "a file is fixed completely or not at all" holds from the start.
    op.execute("UPDATE quote SET document_ref = NULL, document_sha256 = NULL")
    op.create_check_constraint(
        op.f("ck_quote_document_origin_valid"),
        "quote",
        "document_origin IS NULL OR document_origin IN "
        "('issue', 'afterwards', 'received')",
    )
    op.create_check_constraint(
        op.f("ck_quote_document_complete"),
        "quote",
        "(document_ref IS NULL) = (document_sha256 IS NULL) "
        "AND (document_ref IS NULL) = (document_fixed_at IS NULL) "
        "AND (document_ref IS NULL) = (document_origin IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_quote_document_complete"), "quote", type_="check")
    op.drop_constraint(op.f("ck_quote_document_origin_valid"), "quote", type_="check")
    op.drop_column("quote", "document_origin")
    op.drop_column("quote", "document_fixed_at")
