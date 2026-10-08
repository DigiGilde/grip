"""Tasks: the work on a case, what the engine remembers, and notes.

Revision ID: 0023_tasks
Revises: 0022_rate_card_validity
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_tasks"
down_revision: str | None = "0022_rate_card_validity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _person_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        ["person.id"],
        name=op.f(f"fk_{table}_{column}_person"),
        ondelete="SET NULL",
    )


def upgrade() -> None:
    op.create_table(
        "task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("case_kind", sa.String(20), nullable=False),
        _uuid("assignment_id"),
        _uuid("vacancy_id"),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("template_key", sa.String(80), nullable=True),
        sa.Column("plan_version", sa.String(40), nullable=True),
        sa.Column("repeat_key", sa.String(80), server_default="", nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("track", sa.String(20), nullable=False),
        sa.Column("subject_kind", sa.String(40), nullable=True),
        sa.Column("subject_id", sa.String(80), nullable=True),
        sa.Column("link", sa.String(500), nullable=True),
        _uuid("assignee_person_id"),
        sa.Column("assignee_role", sa.String(30), nullable=True),
        _uuid("assigned_by_id"),
        sa.Column("waiting_on", sa.String(120), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(10), server_default="todo", nullable=False),
        sa.Column("closing_fact", sa.String(80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("completed_by_id"),
        sa.Column("completed_by_fact", sa.String(80), nullable=True),
        _uuid("created_by_id"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "case_kind IN ('assignment', 'vacancy')",
            name=op.f("ck_task_case_kind_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('todo', 'doing', 'waiting', 'done', 'obsolete')",
            name=op.f("ck_task_status_valid"),
        ),
        sa.CheckConstraint(
            "origin IN ('plan', 'manual')", name=op.f("ck_task_origin_valid")
        ),
        sa.CheckConstraint(
            "(case_kind = 'assignment' AND assignment_id IS NOT NULL"
            " AND vacancy_id IS NULL)"
            " OR (case_kind = 'vacancy' AND vacancy_id IS NOT NULL)",
            name=op.f("ck_task_case_matches_kind"),
        ),
        sa.CheckConstraint(
            "(origin = 'plan') = (template_key IS NOT NULL)",
            name=op.f("ck_task_plan_task_has_template"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_task_assignment_id_assignment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f("fk_task_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        _person_fk("task", "assignee_person_id"),
        _person_fk("task", "assigned_by_id"),
        _person_fk("task", "completed_by_id"),
        _person_fk("task", "created_by_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task")),
    )
    op.create_index(
        "uq_task_dedupe_key",
        "task",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_index("ix_task_assignment_id", "task", ["assignment_id"])
    op.create_index("ix_task_vacancy_id", "task", ["vacancy_id"])
    op.create_index("ix_task_assignee_person_id", "task", ["assignee_person_id"])
    op.create_index("ix_task_status", "task", ["status"])

    op.create_table(
        "task_note",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        _uuid("task_id", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _uuid("created_by_id"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.id"],
            name=op.f("fk_task_note_task_id_task"),
            ondelete="CASCADE",
        ),
        _person_fk("task_note", "created_by_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_note")),
    )
    op.create_index(op.f("ix_task_note_task_id"), "task_note", ["task_id"])

    op.create_table(
        "task_case",
        sa.Column("case_kind", sa.String(20), nullable=False),
        _uuid("case_id", nullable=False),
        sa.Column("plan_version", sa.String(40), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "case_kind IN ('assignment', 'vacancy')",
            name=op.f("ck_task_case_case_kind_valid"),
        ),
        sa.PrimaryKeyConstraint("case_kind", "case_id", name=op.f("pk_task_case")),
    )

    op.create_table(
        "task_engine_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_engine_run")),
    )


def downgrade() -> None:
    op.drop_table("task_engine_run")
    op.drop_table("task_case")
    op.drop_index(op.f("ix_task_note_task_id"), table_name="task_note")
    op.drop_table("task_note")
    op.drop_index("ix_task_status", table_name="task")
    op.drop_index("ix_task_assignee_person_id", table_name="task")
    op.drop_index("ix_task_vacancy_id", table_name="task")
    op.drop_index("ix_task_assignment_id", table_name="task")
    op.drop_index("uq_task_dedupe_key", table_name="task")
    op.drop_table("task")
