"""Schemas for the financial state of an assignment. Class B throughout,
except the amounts per person (class D) and their names (roster)."""

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


class FiguresOut(BaseModel):
    budgeted_cents: Annotated[int, in_class(B)]
    # Inzet of closed months, at the established percentage.
    realised_cents: Annotated[int, in_class(B)]
    # Inzet of open months, at the planned percentage.
    planned_cents: Annotated[int, in_class(B)]
    costs_realised_cents: Annotated[int, in_class(B)]
    costs_forecast_cents: Annotated[int, in_class(B)]
    costs_cents: Annotated[int, in_class(B)]
    # Realised plus planned plus costs.
    expected_total_cents: Annotated[int, in_class(B)]
    # Budgeted minus expected total; negative is an overrun.
    variance_cents: Annotated[int, in_class(B)]
    variance_pct: Annotated[Decimal | None, in_class(B)]
    overrun: Annotated[bool, in_class(B)]
    # Realised inzet plus realised costs, and its share of the budget.
    realised_total_cents: Annotated[int, in_class(B)]
    realised_pct: Annotated[Decimal | None, in_class(B)]


class KeyFiguresOut(BaseModel):
    agreed_cents: Annotated[int | None, in_class(B)]
    budgeted_cents: Annotated[int | None, in_class(B)]
    expected_total_cents: Annotated[int | None, in_class(B)]
    agreed_minus_budgeted_cents: Annotated[int | None, in_class(B)]
    budgeted_minus_expected_cents: Annotated[int | None, in_class(B)]
    realised_cents: Annotated[int | None, in_class(B)]
    realised_pct: Annotated[Decimal | None, in_class(B)]
    # Aangeleverd: billing data exported for the financial administration.
    delivered_cents: Annotated[int, in_class(B)]
    # Nog aan te leveren: closed and priced, not delivered yet.
    to_deliver_cents: Annotated[int | None, in_class(B)]
    # Gefactureerd: only what was recorded as actually invoiced.
    invoiced_cents: Annotated[int, in_class(B)]
    # Nog te factureren: delivered, and no invoice recorded for it.
    to_invoice_cents: Annotated[int, in_class(B)]


class PersonAmountOut(BaseModel):
    allocation_id: Annotated[UUID, in_class(ROSTER)]
    person_id: Annotated[UUID, in_class(ROSTER)]
    person_name: Annotated[str, in_class(ROSTER)]
    start_date: Annotated[date, in_class(C)]
    end_date: Annotated[date, in_class(C)]
    realised_cents: Annotated[int, in_class(D)]
    planned_cents: Annotated[int, in_class(D)]
    total_cents: Annotated[int, in_class(D)]
    category_mismatch: Annotated[bool, in_class(SIGNAL)]


class CostAmountOut(BaseModel):
    cost_item_id: Annotated[UUID, in_class(B)]
    description: Annotated[str, in_class(B)]
    pct: Annotated[Decimal, in_class(B)]
    realised_cents: Annotated[int, in_class(B)]
    forecast_cents: Annotated[int, in_class(B)]
    total_cents: Annotated[int, in_class(B)]


class FinanceLineOut(BaseModel):
    budget_line_id: Annotated[UUID, in_class(A)]
    description: Annotated[str, in_class(A)]
    kind: Annotated[str, in_class(A)]
    rate_category: Annotated[str | None, in_class(B)]
    figures: Annotated[FiguresOut | None, nested()]
    pricing_error: Annotated[str | None, in_class(B)]
    persons: Annotated[list[PersonAmountOut], nested()]
    # Why the line runs over or under (R14): with the person and the
    # categories for who may see what that person bills, otherwise only
    # "tariefwijziging per <datum>". Filled by the route per reader.
    rate_difference_notes: Annotated[list[str], in_class(B)] = []
    # How many persons are on the line whose amounts this reader may not see.
    persons_hidden: Annotated[int, in_class(B)]
    costs: Annotated[list[CostAmountOut], nested()]


class MonthRowOut(BaseModel):
    month: Annotated[date, in_class(B)]
    closed: Annotated[bool, in_class(B)]
    budgeted_cents: Annotated[int, in_class(B)]
    planned_cents: Annotated[int, in_class(B)]
    realised_cents: Annotated[int | None, in_class(B)]
    cumulative_budgeted_cents: Annotated[int, in_class(B)]
    cumulative_realised_cents: Annotated[int, in_class(B)]
    cumulative_planned_open_cents: Annotated[int, in_class(B)]
    cumulative_expected_cents: Annotated[int, in_class(B)]
    cumulative_variance_cents: Annotated[int, in_class(B)]


class SignalOut(BaseModel):
    kind: Annotated[str, in_class(B)]
    budget_line_id: Annotated[UUID | None, in_class(B)]
    description: Annotated[str | None, in_class(B)]
    amount_cents: Annotated[int | None, in_class(B)]
    pct: Annotated[Decimal | None, in_class(B)]
    count: Annotated[int | None, in_class(B)]
    months: Annotated[list[date], in_class(B)]


class AssignmentFinanceOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    # Null means the whole period.
    year: Annotated[int | None, in_class(A)]
    # First day of the last closed month; null when none is closed.
    reference_month: Annotated[date | None, in_class(B)]
    key_figures: Annotated[KeyFiguresOut, nested()]
    totals: Annotated[FiguresOut | None, nested()]
    pricing_error: Annotated[str | None, in_class(B)]
    lines: Annotated[list[FinanceLineOut], nested()]
    months: Annotated[list[MonthRowOut], nested()]
    budgeted_outside_months_cents: Annotated[int, in_class(B)]
    signals: Annotated[list[SignalOut], nested()]
    free_room_threshold_pct: Annotated[Decimal, in_class(B)]


class LinePreviewIn(BaseModel):
    """The values of a budget line form, as far as they are filled in."""

    kind: str = "personnel"
    fte: Decimal | None = None
    rate_category: str | None = None
    # "assignment": price over the period of the assignment, whatever dates
    # are sent; anything else: over the two dates.
    period_source: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = None
    year: int | None = None


class LinePreviewOut(BaseModel):
    # Null while the line cannot be priced; the reason then says what is missing.
    budgeted_cents: Annotated[int | None, in_class(B)]
    budgeted_by_year: Annotated[dict[str, int], in_class(B)]
    reason: Annotated[str | None, in_class(B)]
