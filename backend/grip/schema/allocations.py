"""Schemas for inzet: a person on a budget line for a period.

The R14 signal exists twice on purpose. ``category_mismatch`` is the bare
fact, which a planner may see. The categories behind it are class D.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
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
    start_date: Annotated[date, in_class(C)]
    end_date: Annotated[date, in_class(C)]
    fte_pct: Annotated[Decimal, in_class(C)]
    can_edit: Annotated[bool, in_class(C)]
    amount_cents: Annotated[int | None, in_class(D)]
    pricing_error: Annotated[str | None, in_class(D)]
    line_category: Annotated[str | None, in_class(D)]
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
    start_date: date
    end_date: date
    fte_pct: Decimal = Field(gt=0, le=100)
    allow_closed_year: bool = False


class AllocationUpdate(BaseModel):
    """Only the fields that are sent are changed."""

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
