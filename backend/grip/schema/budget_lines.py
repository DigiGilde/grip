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
D = DataClass.PERSON_RATE
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL


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
    # The colleague the role is meant for. Staffing data: absent for a reader
    # without class C, and never part of a quote.
    intended_person_id: Annotated[UUID | None, in_class(C)] = None
    intended_person_name: Annotated[str | None, in_class(C)] = None
    # The reservation the name made: the allocation, whether it still has the
    # period and size of the line, and whether it is "onder voorbehoud".
    intended_allocation_id: Annotated[UUID | None, in_class(C)] = None
    intended_in_step: Annotated[bool | None, in_class(C)] = None
    intended_tentative: Annotated[bool | None, in_class(C)] = None
    intended_notes: Annotated[list[str], in_class(C)] = Field(default_factory=list)
    # The R14 signal: the person bills in another category than the line
    # assumes in some month. A fact, without the category.
    intended_category_differs: Annotated[bool | None, in_class(SIGNAL)] = None
    # What the person bills, and why it may differ from the line.
    intended_category: Annotated[str | None, in_class(D)] = None
    intended_category_notes: Annotated[list[str], in_class(D)] = Field(
        default_factory=list
    )


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
    # The colleague the role is meant for. Without a rate_category the
    # category is derived from this person.
    intended_person_id: UUID | None = None
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
    # Send a person to name or replace the intended person, null to remove.
    intended_person_id: UUID | None = None
    # Take the category from the intended person instead of sending one.
    derive_category: bool = False
    allow_closed_year: bool = False


class DeriveRequest(BaseModel):
    """What the form knows so far when it asks what a person implies."""

    intended_person_id: UUID
    start_date: date | None = None
    end_date: date | None = None
    fte: Decimal | None = Field(default=None, gt=0)


class RateByYearOut(BaseModel):
    year: Annotated[int, in_class(B)]
    monthly_rate_cents: Annotated[int, in_class(B)]


class DerivationOut(BaseModel):
    """Proposals for a budget line meant for a person. Nothing is saved."""

    intended_person_id: Annotated[UUID, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    # True when the period is a proposal and was not sent by the form.
    period_proposed: Annotated[bool, in_class(C)]
    # Always null: grip does not know what someone has free.
    fte: Annotated[Decimal | None, in_class(C)]
    notes: Annotated[list[str], in_class(C)]
    rate_category: Annotated[str | None, in_class(D)]
    category_notes: Annotated[list[str], in_class(D)]
    monthly_rates: Annotated[list[RateByYearOut], nested()]
    budgeted_cents: Annotated[int | None, in_class(B)]
