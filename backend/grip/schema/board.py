"""Schemas for the planner's board. Time and people only: no amounts."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
D = DataClass.PERSON_RATE
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL


class BoardCellOut(BaseModel):
    month: Annotated[date, in_class(C)]
    available: Annotated[bool, in_class(C)]
    pct: Annotated[Decimal, in_class(C)]
    tentative_pct: Annotated[Decimal, in_class(C)]
    over: Annotated[bool, in_class(C)]
    established: Annotated[bool, in_class(C)]


class BoardBarOut(BaseModel):
    allocation_id: Annotated[UUID, in_class(ROSTER)]
    person_id: Annotated[UUID, in_class(ROSTER)]
    person_name: Annotated[str, in_class(ROSTER)]
    assignment_id: Annotated[UUID, in_class(A)]
    assignment_name: Annotated[str, in_class(A)]
    budget_line_id: Annotated[UUID, in_class(A)]
    line_description: Annotated[str, in_class(A)]
    role: Annotated[str | None, in_class(ROSTER)]
    tentative: Annotated[bool, in_class(ROSTER)]
    verbally_agreed: Annotated[bool, in_class(ROSTER)]
    start_date: Annotated[date, in_class(C)]
    end_date: Annotated[date, in_class(C)]
    fte_pct: Annotated[Decimal, in_class(C)]
    closed_months: Annotated[list[date], in_class(C)]
    can_edit: Annotated[bool, in_class(C)]
    category_mismatch: Annotated[bool, in_class(SIGNAL)]
    line_category: Annotated[str | None, in_class(D)]
    person_category: Annotated[str | None, in_class(D)]


class BoardPersonOut(BaseModel):
    person_id: Annotated[UUID, in_class(ROSTER)]
    person_name: Annotated[str, in_class(ROSTER)]
    manager_id: Annotated[UUID | None, in_class(C)]
    manager_name: Annotated[str | None, in_class(C)]
    # Totals over everything the person does, also on assignments the reader
    # cannot see; so only for whoever may read the staffing of the person.
    cells: Annotated[list[BoardCellOut], nested()]
    now_pct: Annotated[Decimal | None, in_class(C)]
    room_from: Annotated[date | None, in_class(C)]
    idle_from: Annotated[date | None, in_class(C)]
    over_months: Annotated[list[date], in_class(C)]
    bars: Annotated[list[BoardBarOut], nested()]


class BoardOpenRoleOut(BaseModel):
    budget_line_id: Annotated[UUID, in_class(A)]
    assignment_id: Annotated[UUID, in_class(A)]
    assignment_name: Annotated[str, in_class(A)]
    description: Annotated[str, in_class(A)]
    role: Annotated[str | None, in_class(C)]
    fte: Annotated[Decimal, in_class(C)]
    unfilled_fte: Annotated[Decimal, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    can_fill: Annotated[bool, in_class(C)]


class BoardOut(BaseModel):
    months: Annotated[list[date], in_class(A)]
    current_month: Annotated[date, in_class(A)]
    persons: Annotated[list[BoardPersonOut], nested()]
    open_roles: Annotated[list[BoardOpenRoleOut], nested()]
    can_add: Annotated[bool, in_class(A)]


# -- the staffing of one assignment -------------------------------------------


class RoleMonthOut(BaseModel):
    month: Annotated[date, in_class(C)]
    asked_pct: Annotated[Decimal, in_class(C)]
    filled_pct: Annotated[Decimal, in_class(C)]
    open_pct: Annotated[Decimal, in_class(C)]
    over: Annotated[bool, in_class(C)]
    closed: Annotated[bool, in_class(C)]


class RoleGapOut(BaseModel):
    start: Annotated[date, in_class(C)]
    end: Annotated[date, in_class(C)]
    open_fte: Annotated[Decimal, in_class(C)]


class RoleBarOut(BoardBarOut):
    # The person is hired but has not started yet.
    starts_on: Annotated[date | None, in_class(C)]
    before_start: Annotated[bool, in_class(C)]
    outside_role_period: Annotated[bool, in_class(C)]


class RoleStaffingOut(BaseModel):
    budget_line_id: Annotated[UUID, in_class(A)]
    description: Annotated[str, in_class(A)]
    role: Annotated[str | None, in_class(C)]
    fte: Annotated[Decimal, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    months: Annotated[list[RoleMonthOut], nested()]
    bars: Annotated[list[RoleBarOut], nested()]
    gaps: Annotated[list[RoleGapOut], nested()]
    fully_staffed: Annotated[bool, in_class(C)]
    # Who is on the role, for a reader who gets names but no time.
    names: Annotated[list[str], in_class(ROSTER)]
    can_fill: Annotated[bool, in_class(C)]


class OverbookedOut(BaseModel):
    """Someone on the assignment above 100 percent, with the first month."""

    person_id: Annotated[UUID, in_class(ROSTER)]
    person_name: Annotated[str, in_class(ROSTER)]
    month: Annotated[date, in_class(C)]
    pct: Annotated[Decimal, in_class(C)]


class AssignmentStaffingOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    months: Annotated[list[date], in_class(A)]
    current_month: Annotated[date, in_class(A)]
    closed_months: Annotated[list[date], in_class(C)]
    tentative: Annotated[bool, in_class(A)]
    roles: Annotated[list[RoleStaffingOut], nested()]
    role_count: Annotated[int, in_class(C)]
    staffed_count: Annotated[int, in_class(C)]
    open_fte: Annotated[Decimal | None, in_class(C)]
    open_from: Annotated[date | None, in_class(C)]
    overbooked_count: Annotated[int, in_class(C)]
    overbooked: Annotated[list[OverbookedOut], nested()] = []
