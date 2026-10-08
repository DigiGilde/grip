"""Schemas for the budget of an assignment.

A budget line is split over three classes. What it is called is class A. The
demand it expresses (role, size, period) is class C, because a planner needs
it to put people on the line. The money, and the rate category that the
money follows from, is class B.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING


class BudgetLineOut(BaseModel):
    id: Annotated[UUID, in_class(A)]
    assignment_id: Annotated[UUID, in_class(A)]
    description: Annotated[str, in_class(A)]
    kind: Annotated[str, in_class(A)]
    position: Annotated[int, in_class(A)]
    role: Annotated[str | None, in_class(C)]
    fte: Annotated[Decimal | None, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    rate_category: Annotated[str | None, in_class(B)]
    amount_cents: Annotated[int | None, in_class(B)]
    year: Annotated[int | None, in_class(B)]
    # Computed by the calculation module; null when it could not be priced.
    budgeted_cents: Annotated[int | None, in_class(B)]
    budgeted_by_year: Annotated[dict[str, int], in_class(B)]
    pricing_error: Annotated[str | None, in_class(B)]


class BudgetOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    assignment_name: Annotated[str, in_class(A)]
    can_edit: Annotated[bool, in_class(A)]
    lines: Annotated[list[BudgetLineOut], nested()]
    subtotals_by_year: Annotated[dict[str, int], in_class(B)]
    total_budgeted_cents: Annotated[int | None, in_class(B)]
    quoted_amount_cents: Annotated[int | None, in_class(B)]
    pricing_error: Annotated[str | None, in_class(B)]


class BudgetLineCreate(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    kind: str
    position: int | None = Field(default=None, ge=1)
    role: str | None = Field(default=None, max_length=255)
    fte: Decimal | None = None
    rate_category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    year: int | None = Field(default=None, ge=2000, le=2100)
    # Only a beheerder may change a closed year; it leaves an audit row.
    allow_closed_year: bool = False


class BudgetLineUpdate(BaseModel):
    """Only the fields that are sent are changed. The kind cannot change."""

    description: str | None = Field(default=None, min_length=1, max_length=500)
    position: int | None = Field(default=None, ge=1)
    role: str | None = Field(default=None, max_length=255)
    fte: Decimal | None = None
    rate_category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    year: int | None = Field(default=None, ge=2000, le=2100)
    allow_closed_year: bool = False
