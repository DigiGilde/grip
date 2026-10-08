"""Period source: a budget line follows the assignment, inzet follows its line.

Revision ID: 0020_period_source
Revises: 0019_person_roles
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_period_source"
down_revision: str | None = "0019_person_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_PERSONNEL = (
    "kind <> 'personnel' OR (fte IS NOT NULL AND rate_category IS NOT NULL "
    "AND start_date IS NOT NULL AND end_date IS NOT NULL "
    "AND amount_cents IS NULL AND year IS NULL)"
)
_NEW_PERSONNEL = (
    "kind <> 'personnel' OR (fte IS NOT NULL AND rate_category IS NOT NULL "
    "AND amount_cents IS NULL AND year IS NULL)"
)


def upgrade() -> None:
    op.add_column(
        "budget_line",
        sa.Column(
            "period_source", sa.String(length=12), server_default="own", nullable=False
        ),
    )
    op.add_column(
        "allocation",
        sa.Column(
            "period_source", sa.String(length=12), server_default="own", nullable=False
        ),
    )
    # A line whose dates equal those of its assignment follows it from now
    # on; every other line keeps a period of its own.
    op.execute(
        """
        UPDATE budget_line AS line
        SET period_source = 'assignment'
        FROM assignment
        WHERE assignment.id = line.assignment_id
          AND line.kind = 'personnel'
          AND line.start_date IS NOT NULL
          AND line.start_date = assignment.start_date
          AND line.end_date = assignment.end_date
        """
    )
    # The same one level down: inzet with the dates of its line follows it.
    op.execute(
        """
        UPDATE allocation
        SET period_source = 'line'
        FROM budget_line AS line
        WHERE line.id = allocation.budget_line_id
          AND allocation.start_date = line.start_date
          AND allocation.end_date = line.end_date
        """
    )
    op.drop_constraint(
        op.f("ck_budget_line_personnel_fields"), "budget_line", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_budget_line_personnel_fields"), "budget_line", _NEW_PERSONNEL
    )
    op.create_check_constraint(
        op.f("ck_budget_line_period_source_valid"),
        "budget_line",
        "period_source IN ('assignment', 'own')",
    )
    op.create_check_constraint(
        op.f("ck_budget_line_own_period_complete"),
        "budget_line",
        "kind <> 'personnel' OR period_source = 'assignment' "
        "OR (start_date IS NOT NULL AND end_date IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_budget_line_period_whole"),
        "budget_line",
        "(start_date IS NULL) = (end_date IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_allocation_period_source_valid"),
        "allocation",
        "period_source IN ('line', 'own')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_allocation_period_source_valid"), "allocation", type_="check"
    )
    op.drop_constraint(
        op.f("ck_budget_line_period_whole"), "budget_line", type_="check"
    )
    op.drop_constraint(
        op.f("ck_budget_line_own_period_complete"), "budget_line", type_="check"
    )
    op.drop_constraint(
        op.f("ck_budget_line_period_source_valid"), "budget_line", type_="check"
    )
    # Lines without a period cannot exist in the older schema.
    op.execute(
        "DELETE FROM budget_line WHERE kind = 'personnel' AND start_date IS NULL"
    )
    op.drop_constraint(
        op.f("ck_budget_line_personnel_fields"), "budget_line", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_budget_line_personnel_fields"), "budget_line", _OLD_PERSONNEL
    )
    op.drop_column("allocation", "period_source")
    op.drop_column("budget_line", "period_source")
