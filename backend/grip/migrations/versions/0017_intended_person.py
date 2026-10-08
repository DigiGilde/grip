"""Intended person on a budget line, and the reservation it makes.

Revision ID: 0017_intended_person
Revises: 0016_document_owner
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_intended_person"
down_revision: str | None = "0016_document_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "budget_line",
        sa.Column("intended_person_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_budget_line_intended_person_id_person"),
        "budget_line",
        "person",
        ["intended_person_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_budget_line_intended_person_id"),
        "budget_line",
        ["intended_person_id"],
    )
    op.add_column(
        "allocation",
        sa.Column(
            "from_budget",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("allocation", "from_budget")
    op.drop_index(op.f("ix_budget_line_intended_person_id"), table_name="budget_line")
    op.drop_constraint(
        op.f("fk_budget_line_intended_person_id_person"),
        "budget_line",
        type_="foreignkey",
    )
    op.drop_column("budget_line", "intended_person_id")
