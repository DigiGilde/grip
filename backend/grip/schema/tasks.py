"""Schemas of the task routes.

Every field of a task is data class A of its case: what to do, for which
case, by when and for whom. A task never carries an amount, a rate or
anything else its subject would keep from the reader.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = in_class(DataClass.ASSIGNMENT_BASIC)

CaseKind = Literal["assignment", "vacancy"]
TaskStatus = Literal["todo", "doing", "waiting", "done", "obsolete"]


class TaskNoteOut(BaseModel):
    id: Annotated[UUID, A]
    body: Annotated[str, A]
    created_at: Annotated[datetime, A]
    author_name: Annotated[str | None, A] = None


class ChecklistItemOut(BaseModel):
    text: Annotated[str, A]
    done: Annotated[bool, A] = False


class TaskOut(BaseModel):
    id: Annotated[UUID, A]
    case_kind: Annotated[str, A]
    assignment_id: Annotated[UUID | None, A] = None
    assignment_name: Annotated[str | None, A] = None
    vacancy_id: Annotated[UUID | None, A] = None
    vacancy_title: Annotated[str | None, A] = None
    case_label: Annotated[str, A]
    title: Annotated[str, A]
    track: Annotated[str, A]
    track_label: Annotated[str, A]
    status: Annotated[str, A]
    status_label: Annotated[str, A]
    origin: Annotated[str, A]
    due_on: Annotated[date | None, A] = None
    overdue: Annotated[bool, A] = False
    assignee_person_id: Annotated[UUID | None, A] = None
    assignee_role: Annotated[str | None, A] = None
    assignee_label: Annotated[str, A]
    waiting_on: Annotated[str | None, A] = None
    link: Annotated[str | None, A] = None
    is_mine: Annotated[bool, A] = False
    can_change: Annotated[bool, A] = False
    can_complete: Annotated[bool, A] = False
    closes_by_fact: Annotated[bool, A] = False
    closing_fact_label: Annotated[str | None, A] = None
    completed_at: Annotated[datetime | None, A] = None
    completed_by_name: Annotated[str | None, A] = None
    completed_by_fact: Annotated[bool, A] = False
    note_count: Annotated[int, A] = 0
    notes: Annotated[list[TaskNoteOut], nested()] = Field(default_factory=list)
    # The task as this reader must hear it. ``headline`` is what to do, or
    # what is waited for; ``instruction`` the sentence addressed to the
    # reader; ``needs_me`` whether the reader must act now.
    headline: Annotated[str, A] = ""
    # What must happen, whoever reads it: for an overview of everyone's work.
    doer_title: Annotated[str, A] = ""
    instruction: Annotated[str, A] = ""
    needs_me: Annotated[bool, A] = False
    why: Annotated[str | None, A] = None
    then: Annotated[str | None, A] = None
    # The one action; absent when the reader has nothing to do now.
    action_text: Annotated[str | None, A] = None
    # Where the work is done, inside the application.
    work_href: Annotated[str | None, A] = None
    waits_on: Annotated[str | None, A] = None
    blocked: Annotated[str | None, A] = None
    checklist: Annotated[list[ChecklistItemOut], nested()] = Field(default_factory=list)


class TaskCountsOut(BaseModel):
    open: Annotated[int, A] = 0
    to_do: Annotated[int, A] = 0
    overdue: Annotated[int, A] = 0


class TaskListOut(BaseModel):
    items: Annotated[list[TaskOut], nested()] = Field(default_factory=list)
    # Tasks of others on the cases the reader started: what the reader
    # waits for. Never the reader's own.
    awaited: Annotated[list[TaskOut], nested()] = Field(default_factory=list)
    counts: Annotated[TaskCountsOut, nested()] = Field(default_factory=TaskCountsOut)


class TrackOut(BaseModel):
    key: Annotated[str, A]
    label: Annotated[str, A]
    open_count: Annotated[int, A] = 0
    waiting_count: Annotated[int, A] = 0
    standing: Annotated[str, A]
    tasks: Annotated[list[TaskOut], nested()] = Field(default_factory=list)


class CaseTasksOut(BaseModel):
    case_kind: Annotated[str, A]
    case_id: Annotated[UUID, A]
    plan_version: Annotated[str, A]
    can_add: Annotated[bool, A] = False
    tracks: Annotated[list[TrackOut], nested()] = Field(default_factory=list)


class TaskCreateIn(BaseModel):
    case_kind: CaseKind
    case_id: UUID
    title: str = Field(min_length=1, max_length=255)
    track: str | None = None
    assignee_person_id: UUID | None = None
    due_on: date | None = None


class TaskUpdateIn(BaseModel):
    status: TaskStatus | None = None
    # Present and null hands the task back to the role of the plan.
    assignee_person_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    due_on: date | None = None


class TaskNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
