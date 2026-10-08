"""Assignment status verbally_agreed, with the note of the agreement.

Revision ID: 0010_verbal_agreement
Revises: 0009_quote_canonical
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_verbal_agreement"
down_revision: str | None = "0009_quote_canonical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = (
    "status IN ('draft', 'requested', 'quoted', 'accepted', 'in_progress', "
    "'completed', 'accounted', 'rejected', 'cancelled')"
)
_NEW = (
    "status IN ('draft', 'requested', 'quoted', 'verbally_agreed', "
    "'accepted', 'in_progress', 'completed', 'accounted', 'rejected', "
    "'cancelled')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_assignment_status_valid"), "assignment", type_="check")
    op.create_check_constraint(op.f("ck_assignment_status_valid"), "assignment", _NEW)
    op.add_column(
        "assignment", sa.Column("verbal_agreement_note", sa.Text(), nullable=True)
    )
    op.add_column(
        "assignment",
        sa.Column("verbal_agreement_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assignment", "verbal_agreement_at")
    op.drop_column("assignment", "verbal_agreement_note")
    # A verbal agreement is the contractor's own knowledge of a quoted
    # assignment, so that is what it falls back to.
    op.execute(
        "UPDATE assignment SET status = 'quoted' WHERE status = 'verbally_agreed'"
    )
    op.drop_constraint(op.f("ck_assignment_status_valid"), "assignment", type_="check")
    op.create_check_constraint(op.f("ck_assignment_status_valid"), "assignment", _OLD)
