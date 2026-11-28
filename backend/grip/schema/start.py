"""The start page: what is to do and what is going on for the reader.

Nothing of classes D, E or F belongs here: a field of such a class on the first
screen would log a read on every visit, and the screen is shared in meetings.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
COUNTS = DataClass.STAFFING_COUNTS
M = DataClass.MASTER_DATA


class ToDoGroupOut(BaseModel):
    """One case: its first task, and what follows. A task is class A of its
    case; a number of months only goes into ``more_text`` for who may read B or
    C of the assignment."""

    case_kind: Annotated[str, in_class(A)]
    case_id: Annotated[UUID, in_class(A)]
    case_label: Annotated[str, in_class(A)]
    task_id: Annotated[UUID, in_class(A)]
    headline: Annotated[str, in_class(A)]
    # The page of the work, or else the case itself; null when neither may be
    # opened by this reader.
    href: Annotated[str | None, in_class(A)]
    overdue: Annotated[bool, in_class(A)]
    due_on: Annotated[date | None, in_class(A)]
    more_text: Annotated[str | None, in_class(A)]


class ToDoOut(BaseModel):
    groups: Annotated[list[ToDoGroupOut], nested()]
    # The number in the navigation bar, over all cases.
    total: Annotated[int, in_class(A)]


class MyWorkRowOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    line: Annotated[str, in_class(C)]
    warning: Annotated[str | None, in_class(C)]


class MyWorkOut(BaseModel):
    person_id: Annotated[UUID, in_class(C)]
    rows: Annotated[list[MyWorkRowOut], nested()]
    total: Annotated[int, in_class(C)]


class MyAssignmentRowOut(BaseModel):
    """``line`` is made by ``parts_of``, which only writes a sentence from
    classes the reader may read, so the field is as open as the assignment."""

    assignment_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    line: Annotated[str, in_class(A)]
    # Over the whole period of the assignment. Null while it is potential.
    verdict: Annotated[Literal["room", "overrun"] | None, in_class(B)]


class MyAssignmentsOut(BaseModel):
    rows: Annotated[list[MyAssignmentRowOut], nested()]
    total: Annotated[int, in_class(A)]


class PlanningOut(BaseModel):
    open_roles: Annotated[int, in_class(COUNTS)]
    open_fte: Annotated[Decimal, in_class(COUNTS)]
    idle_people: Annotated[int, in_class(COUNTS)]
    # First day of the month from which ``idle_people`` have no inzet.
    idle_from: Annotated[date | None, in_class(COUNTS)]


class MyPersonRowOut(BaseModel):
    person_id: Annotated[UUID, in_class(ROSTER)]
    name: Annotated[str, in_class(ROSTER)]
    now_pct: Annotated[Decimal | None, in_class(C)]
    # First day of the month from which the person has no inzet.
    free_from: Annotated[date | None, in_class(C)]


class MyPeopleOut(BaseModel):
    rows: Annotated[list[MyPersonRowOut], nested()]
    total: Annotated[int, in_class(ROSTER)]


class StartFiguresOut(BaseModel):
    year: Annotated[int, in_class(B)]
    # Agreed assignments in ``year``, as on Geld.
    expected_cents: Annotated[int, in_class(B)]
    budgeted_cents: Annotated[int, in_class(B)]
    # Left out when the reading of the investment room is withheld.
    room_cents: Annotated[int | None, in_class(B)] = None
    shortfall: Annotated[bool | None, in_class(B)] = None
    # Quotes issued in ``year`` that wait for an answer. Each is an amount over
    # the whole period of its assignment.
    potential_cents: Annotated[int, in_class(B)]
    quotes_waiting: Annotated[int, in_class(B)]
    # Executors whose cost items could not be counted in the agreed figures:
    # the figures are then incomplete (ADR 0052).
    incomplete_by: Annotated[list[str], in_class(B)] = []


class MyRequestRowOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    line: Annotated[str, in_class(A)]


class MyRequestsOut(BaseModel):
    rows: Annotated[list[MyRequestRowOut], nested()]
    total: Annotated[int, in_class(A)]


class ConnectionsOut(BaseModel):
    # Messages to other instances that stopped being retried.
    problems: Annotated[int, in_class(M)]


class StartOut(BaseModel):
    """A block the reader has nothing in or no right to is absent."""

    to_do: Annotated[ToDoOut, nested()]
    my_work: Annotated[MyWorkOut | None, nested()] = None
    my_assignments: Annotated[MyAssignmentsOut | None, nested()] = None
    planning: Annotated[PlanningOut | None, nested()] = None
    my_people: Annotated[MyPeopleOut | None, nested()] = None
    figures: Annotated[StartFiguresOut | None, nested()] = None
    my_requests: Annotated[MyRequestsOut | None, nested()] = None
    connections: Annotated[ConnectionsOut | None, nested()] = None
