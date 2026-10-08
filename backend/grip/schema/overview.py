"""Schemas for the stand van zaken: budgeted, used and available."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
D = DataClass.PERSON_RATE
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL


class TotalsOut(BaseModel):
    budgeted_cents: Annotated[int, in_class(B)]
    # Inzet of closed months, at the established percentage.
    realised_cents: Annotated[int, in_class(B)]
    # Inzet of open months, at the planned percentage.
    forecast_cents: Annotated[int, in_class(B)]
    coverage_cents: Annotated[int, in_class(B)]
    used_cents: Annotated[int, in_class(B)]
    available_cents: Annotated[int, in_class(B)]
    overrun: Annotated[bool, in_class(B)]


class OverviewRowOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    status: Annotated[str, in_class(A)]
    client_name: Annotated[str | None, in_class(A)]
    start_date: Annotated[date | None, in_class(A)]
    end_date: Annotated[date | None, in_class(A)]
    # Null when the assignment could not be priced; see pricing_error.
    totals: Annotated[TotalsOut | None, nested()]
    pricing_error: Annotated[str | None, in_class(B)]


class OverviewOut(BaseModel):
    # Null means the whole period.
    year: Annotated[int | None, in_class(A)]
    rows: Annotated[list[OverviewRowOut], nested()]
    # Over the rows that could be priced.
    totals: Annotated[TotalsOut, nested()]


class TeamMemberOut(BaseModel):
    allocation_id: Annotated[UUID, in_class(ROSTER)]
    person_id: Annotated[UUID, in_class(ROSTER)]
    person_name: Annotated[str, in_class(ROSTER)]
    start_date: Annotated[date, in_class(C)]
    end_date: Annotated[date, in_class(C)]
    fte_pct: Annotated[Decimal, in_class(C)]
    amount_cents: Annotated[int | None, in_class(D)]
    pricing_error: Annotated[str | None, in_class(D)]
    category_mismatch: Annotated[bool, in_class(SIGNAL)]


class LineCostOut(BaseModel):
    cost_item_id: Annotated[UUID, in_class(B)]
    description: Annotated[str, in_class(B)]
    pct: Annotated[Decimal, in_class(B)]
    amount_cents: Annotated[int | None, in_class(B)]


class LineOverviewOut(BaseModel):
    budget_line_id: Annotated[UUID, in_class(A)]
    description: Annotated[str, in_class(A)]
    kind: Annotated[str, in_class(A)]
    role: Annotated[str | None, in_class(C)]
    fte: Annotated[Decimal | None, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    rate_category: Annotated[str | None, in_class(B)]
    totals: Annotated[TotalsOut | None, nested()]
    pricing_error: Annotated[str | None, in_class(B)]
    team: Annotated[list[TeamMemberOut], nested()]
    costs: Annotated[list[LineCostOut], nested()]


class AssignmentOverviewOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    status: Annotated[str, in_class(A)]
    year: Annotated[int | None, in_class(A)]
    totals: Annotated[TotalsOut | None, nested()]
    pricing_error: Annotated[str | None, in_class(B)]
    lines: Annotated[list[LineOverviewOut], nested()]
