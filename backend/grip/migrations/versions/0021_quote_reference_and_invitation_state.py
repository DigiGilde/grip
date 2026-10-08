"""Quote reference with a counter per year; state of a signing invitation.

Existing quotes get a reference in order of issue, per year.

Revision ID: 0021_quote_reference
Revises: 0020_period_source
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_quote_reference"
down_revision: str | None = "0020_period_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quote_reference_counter",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("year", name=op.f("pk_quote_reference_counter")),
    )
    op.add_column("quote", sa.Column("reference", sa.String(length=40), nullable=True))
    op.create_index(op.f("ix_quote_reference"), "quote", ["reference"], unique=False)

    op.add_column(
        "quote_invitation",
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "quote_invitation",
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "quote_invitation",
        sa.Column("withdrawn_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_quote_invitation_withdrawn_by_id_person"),
        "quote_invitation",
        "person",
        ["withdrawn_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Quotes issued before references existed get one in order of issue. The
    # prefix is that of the instance at the moment of migrating. Their frozen
    # content is not touched: the reference of an older quote lives in this
    # column only, and its hash stays what it was.
    from grip.services.quote_reference import reference_prefix

    prefix = reference_prefix()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            WITH numbered AS (
                SELECT id,
                       extract(year from issued_at)::int AS year,
                       row_number() OVER (
                           PARTITION BY extract(year from issued_at)
                           ORDER BY issued_at, created_at, id
                       ) AS number
                FROM quote
            )
            UPDATE quote
            SET reference = :prefix || '-' || numbered.year || '-'
                            || lpad(numbered.number::text, 4, '0')
            FROM numbered
            WHERE quote.id = numbered.id
            """
        ),
        {"prefix": prefix},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO quote_reference_counter (year, last_number)
            SELECT extract(year from issued_at)::int, count(*)
            FROM quote
            GROUP BY 1
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_quote_invitation_withdrawn_by_id_person"),
        "quote_invitation",
        type_="foreignkey",
    )
    op.drop_column("quote_invitation", "withdrawn_by_id")
    op.drop_column("quote_invitation", "withdrawn_at")
    op.drop_column("quote_invitation", "opened_at")
    op.drop_index(op.f("ix_quote_reference"), table_name="quote")
    op.drop_column("quote", "reference")
    op.drop_table("quote_reference_counter")
