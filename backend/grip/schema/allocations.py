"""Schemas for inzet: a person on a budget line for a period.

The R14 signal exists twice on purpose. ``category_mismatch`` is the bare
fact, which a planner may see. The categories behind it are class D.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
D = DataClass.PERSON_RATE
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL


class AllocationOut(BaseModel):
    id: Annotated[UUID, in_class(ROSTER)]
    person_id: Annotated[UUID, in_class(ROSTER)]
    person_name: Annotated[str, in_class(ROSTER)]
    assignment_id: Annotated[UUID, in_class(A)]
    assignment_name: Annotated[str, in_class(A)]
    budget_line_id: Annotated[UUID, in_class(A)]
    budget_line_description: Annotated[str, in_class(A)]
    role: Annotated[str | None, in_class(ROSTER)]
    # On an assignment that is still potential: this inzet may not happen.
    tentative: Annotated[bool, in_class(ROSTER)]
    # "line": the inzet runs as long as its budget line; "own": it has a
    # period of its own. The two dates are the period in force either way.
    period_source: Annotated[str, in_class(C)]
    start_date: Annotated[date, in_class(C)]
    end_date: Annotated[date, in_class(C)]
    fte_pct: Annotated[Decimal, in_class(C)]
    can_edit: Annotated[bool, in_class(C)]
    amount_cents: Annotated[int | None, in_class(D)]
    pricing_error: Annotated[str | None, in_class(D)]
    # The price level of the budget line: money of the assignment (class B),
    # not something about the person. A team member reads their own
    # category, not the one the line is budgeted at.
    line_category: Annotated[str | None, in_class(B)]
    person_category: Annotated[str | None, in_class(D)]
    mismatch_direction: Annotated[str | None, in_class(D)]
    category_mismatch: Annotated[bool, in_class(SIGNAL)]


class AllocationListOut(BaseModel):
    items: Annotated[list[AllocationOut], nested()]
    # Whether the person asking may add inzet anywhere.
    can_add: Annotated[bool, in_class(A)]


class AllocationCreate(BaseModel):
    budget_line_id: UUID
    person_id: UUID
    # Without dates the inzet follows the period of the budget line.
    period_source: Literal["line", "own"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    fte_pct: Decimal = Field(gt=0, le=100)
    allow_closed_year: bool = False


class AllocationUpdate(BaseModel):
    """Only the fields that are sent are changed."""

    # "line" makes the inzet follow its budget line again.
    period_source: Literal["line", "own"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    fte_pct: Decimal | None = Field(default=None, gt=0, le=100)
    allow_closed_year: bool = False


class PersonChoiceOut(BaseModel):
    id: Annotated[UUID, in_class(ROSTER)]
    name: Annotated[str, in_class(ROSTER)]


class LineChoiceOut(BaseModel):
    budget_line_id: Annotated[UUID, in_class(A)]
    assignment_id: Annotated[UUID, in_class(A)]
    assignment_name: Annotated[str, in_class(A)]
    description: Annotated[str, in_class(A)]
    role: Annotated[str | None, in_class(C)]
    fte: Annotated[Decimal | None, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]


class AllocationOptionsOut(BaseModel):
    people: Annotated[list[PersonChoiceOut], nested()]
    lines: Annotated[list[LineChoiceOut], nested()]


class AllocationLoadIn(BaseModel):
    """An inzet as it would be saved, to ask what it does to the person's load."""

    # The inzet being changed; its person and line then follow from it.
    allocation_id: UUID | None = None
    budget_line_id: UUID | None = None
    person_id: UUID | None = None
    period_source: Literal["line", "own"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    fte_pct: Decimal = Field(gt=0, le=100)


class OverMonthOut(BaseModel):
    # First day of the month.
    month: Annotated[date, in_class(C)]
    current_pct: Annotated[Decimal, in_class(C)]
    new_pct: Annotated[Decimal, in_class(C)]


class AllocationLoadOut(BaseModel):
    """The months in which the person would be above 100 percent."""

    person_name: Annotated[str, in_class(ROSTER)]
    over_months: Annotated[list[OverMonthOut], nested()] = Field(default_factory=list)
