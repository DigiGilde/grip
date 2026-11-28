"""Tasks of the instance itself: a case that is neither assignment nor vacancy.

The beheerder's task about messages that do not arrive at another instance
belongs to the instance (ADR 0061). Such a task names no assignment and no
vacancy.

Revision ID: 0050_instance_tasks
Revises: 0049_delivery_trouble
Create Date: 2026-11-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050_instance_tasks"
down_revision: str | None = "0049_delivery_trouble"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATCHES = (
    "(case_kind = 'assignment' AND assignment_id IS NOT NULL"
    " AND vacancy_id IS NULL)"
    " OR (case_kind = 'vacancy' AND vacancy_id IS NOT NULL)"
)


def _constraints(kinds: str, matches: str) -> None:
    op.drop_constraint(op.f("ck_task_case_kind_valid"), "task", type_="check")
    op.drop_constraint(op.f("ck_task_case_matches_kind"), "task", type_="check")
    op.drop_constraint(op.f("ck_task_case_case_kind_valid"), "task_case", type_="check")
    op.create_check_constraint(
        op.f("ck_task_case_kind_valid"), "task", f"case_kind IN ({kinds})"
    )
    op.create_check_constraint(op.f("ck_task_case_matches_kind"), "task", matches)
    op.create_check_constraint(
        op.f("ck_task_case_case_kind_valid"), "task_case", f"case_kind IN ({kinds})"
    )


def upgrade() -> None:
    _constraints(
        "'assignment', 'vacancy', 'instance'",
        f"{_MATCHES} OR (case_kind = 'instance' AND assignment_id IS NULL"
        " AND vacancy_id IS NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM task WHERE case_kind = 'instance'")
    op.execute("DELETE FROM task_case WHERE case_kind = 'instance'")
    _constraints("'assignment', 'vacancy'", _MATCHES)
