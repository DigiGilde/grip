"""Tasks: the work people do on a case.

A case is an assignment, or a vacancy as a sub-case. A task from the plan is
created and closed by the task engine (``grip.tasks``) from facts in the
domain; a manual task is added and ticked by a person. A task never changes a
domain fact. See ADR 0024 and docs/taken.md.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

TASK_STATUSES = ("todo", "doing", "waiting", "done", "obsolete")
OPEN_STATUSES = ("todo", "doing", "waiting")
TASK_ORIGINS = ("plan", "manual")
CASE_KINDS = ("assignment", "vacancy")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Task(Base):
    """One piece of work on a case."""

    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(_in("case_kind", CASE_KINDS), name="case_kind_valid"),
        CheckConstraint(_in("status", TASK_STATUSES), name="status_valid"),
        CheckConstraint(_in("origin", TASK_ORIGINS), name="origin_valid"),
        # A vacancy task names its vacancy; an assignment task its assignment.
        CheckConstraint(
            "(case_kind = 'assignment' AND assignment_id IS NOT NULL"
            " AND vacancy_id IS NULL)"
            " OR (case_kind = 'vacancy' AND vacancy_id IS NOT NULL)",
            name="case_matches_kind",
        ),
        CheckConstraint(
            "(origin = 'plan') = (template_key IS NOT NULL)",
            name="plan_task_has_template",
        ),
        # One task per template, case and subject: the same event twice
        # never makes a second task.
        Index(
            "uq_task_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("ix_task_assignment_id", "assignment_id"),
        Index("ix_task_vacancy_id", "vacancy_id"),
        Index("ix_task_assignee_person_id", "assignee_person_id"),
        Index("ix_task_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    case_kind: Mapped[str] = mapped_column(String(20))
    # For a vacancy task: the assignment of the vacancy's budget line, if any.
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        nullable=True,
    )
    vacancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy.id", ondelete="CASCADE"),
        nullable=True,
    )

    origin: Mapped[str] = mapped_column(String(10))
    template_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    plan_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Which subject of the case this task is about: a month, a budget line, a
    # round of quotes. Empty for a task about the case as a whole.
    repeat_key: Mapped[str] = mapped_column(String(80), default="", server_default="")
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    title: Mapped[str] = mapped_column(String(255))
    track: Mapped[str] = mapped_column(String(20))
    subject_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Where in the application the work is done.
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # A person, or a role that is resolved when the task is read.
    assignee_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    assignee_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Set when a person chose the assignee: the plan then leaves it alone.
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Who the work waits for when nobody here can do it.
    waiting_on: Mapped[str | None] = mapped_column(String(120), nullable=True)

    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), default="todo", server_default="todo"
    )
    # The fact that closes the task; empty when a person ticks it.
    closing_fact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_by_fact: Mapped[str | None] = mapped_column(String(80), nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    notes: Mapped[list[TaskNote]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskNote.created_at",
    )

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class TaskNote(Base):
    """A remark on a task."""

    __tablename__ = "task_note"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()

    task: Mapped[Task] = relationship(back_populates="notes")


class TaskCase(Base):
    """What the engine remembers about a case.

    The plan version a case started with stays with it, so a later plan does
    not rearrange work that is under way.
    """

    __tablename__ = "task_case"
    __table_args__ = (
        CheckConstraint(_in("case_kind", CASE_KINDS), name="case_kind_valid"),
    )

    case_kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    plan_version: Mapped[str] = mapped_column(String(40))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaskEngineRun(Base):
    """When the engine last looked at every open case (one row)."""

    __tablename__ = "task_engine_run"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
