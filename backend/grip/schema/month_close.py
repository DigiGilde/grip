"""Shapes of the monthly close routes.

Which months are open or closed is class A. Who is on the assignment and at
which percentage is class C (staffing). The category, rate and amount per
person are class D. Totals over the month are class B.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)
ROSTER = in_class(DataClass.STAFFING_ROSTER)
C = in_class(DataClass.STAFFING)
D = in_class(DataClass.PERSON_RATE)


class MonthStateOut(BaseModel):
    month: Annotated[str, A]
    closed: Annotated[bool, A]
    closable: Annotated[bool, A]
    closed_at: Annotated[datetime | None, A] = None
    closed_by_name: Annotated[str | None, A] = None
    reopen_count: Annotated[int, A] = 0


class MonthTimelineOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    # Whether months of this assignment can be closed at all in its current
    # status: not before there is an agreement with the client.
    closing_started: Annotated[bool, A] = True
    # Whether the person asking is the one who closes months here.
    may_close: Annotated[bool, A] = False
    months: Annotated[list[MonthStateOut], nested()] = Field(default_factory=list)


class MonthLineOut(BaseModel):
    allocation_id: Annotated[UUID, ROSTER]
    person_id: Annotated[UUID, ROSTER]
    person_name: Annotated[str, ROSTER]
    description: Annotated[str, ROSTER]
    planned_fte_pct: Annotated[Decimal, C]
    established_fte_pct: Annotated[Decimal | None, C] = None
    category: Annotated[str, D]
    monthly_rate_cents: Annotated[int, D]
    planned_amount_cents: Annotated[int, D]
    established_amount_cents: Annotated[int | None, D] = None


class CloseRecordOut(BaseModel):
    closed_at: Annotated[datetime, A]
    closed_by_name: Annotated[str | None, A] = None
    reopened_at: Annotated[datetime | None, A] = None
    reopened_by_name: Annotated[str | None, A] = None
    reopen_reason: Annotated[str | None, A] = None


class MonthDetailOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    month: Annotated[str, A]
    closed: Annotated[bool, A]
    closable: Annotated[bool, A]
    closed_at: Annotated[datetime | None, A] = None
    closed_by_name: Annotated[str | None, A] = None
    # Whether the person asking may close or reopen this month.
    may_close: Annotated[bool, A] = False
    may_reopen: Annotated[bool, A] = False
    pricing_problem: Annotated[str | None, A] = None
    lines: Annotated[list[MonthLineOut], nested()] = Field(default_factory=list)
    history: Annotated[list[CloseRecordOut], nested()] = Field(default_factory=list)
    planned_total_cents: Annotated[int, B] = 0
    established_total_cents: Annotated[int | None, B] = None


class EstablishedIn(BaseModel):
    allocation_id: UUID
    fte_pct: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=3)


class CloseMonthIn(BaseModel):
    # Only the allocations whose actual percentage differs from the plan.
    established: list[EstablishedIn] = Field(default_factory=list)


class ReopenMonthIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
