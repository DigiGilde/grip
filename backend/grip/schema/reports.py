"""Schemas for the reports: per assignment, steering, and the year account.

Every field has one data class. The amounts of an assignment are class B,
who works on it is class C, the KPI of a person is class F. A block of the
steering overview is built per reader from what that reader may see, so the
totals in it are totals over the visible rows, never over more.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested
from grip.schema.kpi import KpiOut
from grip.schema.overview import TotalsOut

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)
C = in_class(DataClass.STAFFING)
ROSTER = in_class(DataClass.STAFFING_ROSTER)
COUNTS = in_class(DataClass.STAFFING_COUNTS)
F = in_class(DataClass.PERSON_KPI)


# -- report per assignment ----------------------------------------------------


class AgreedLineOut(BaseModel):
    description: Annotated[str, B]
    kind: Annotated[str, B]
    role: Annotated[str | None, B]
    fte: Annotated[str | None, B]
    start_date: Annotated[str | None, B]
    end_date: Annotated[str | None, B]
    amount_cents: Annotated[int, B]


class YearAmountOut(BaseModel):
    year: Annotated[int, B]
    amount_cents: Annotated[int, B]


class AgreedOut(BaseModel):
    """The accepted quote, as issued."""

    quote_id: Annotated[UUID, B]
    quote_uri: Annotated[str, B]
    issued_at: Annotated[datetime, B]
    accepted_at: Annotated[datetime | None, B]
    form: Annotated[str | None, B]
    total_cents: Annotated[int, B]
    lines: Annotated[list[AgreedLineOut], nested()]
    subtotals: Annotated[list[YearAmountOut], nested()]


class StatusChangeOut(BaseModel):
    occurred_at: Annotated[datetime, A]
    old_status: Annotated[str | None, A]
    new_status: Annotated[str, A]
    reason: Annotated[str | None, A]


class FinalReportOut(BaseModel):
    issued_at: Annotated[datetime, A]
    summary: Annotated[str | None, A]
    delivered: Annotated[list[str], A]
    not_delivered: Annotated[list[str], A]


class ReportMonthOut(BaseModel):
    # YYYY-MM.
    month: Annotated[str, A]
    closed: Annotated[bool, A]
    closed_at: Annotated[datetime | None, A]


class ReportPeriodOut(BaseModel):
    year: Annotated[int, B]
    totals: Annotated[TotalsOut | None, nested()]
    pricing_error: Annotated[str | None, B]


class ReportLineOut(BaseModel):
    budget_line_id: Annotated[UUID, A]
    description: Annotated[str, A]
    kind: Annotated[str, A]
    totals: Annotated[TotalsOut | None, nested()]
    pricing_error: Annotated[str | None, B]


class ReportCostOut(BaseModel):
    cost_item_id: Annotated[UUID, B]
    description: Annotated[str, B]
    budget_line_description: Annotated[str, B]
    pct: Annotated[Decimal, B]
    amount_cents: Annotated[int | None, B]


class ReportStaffingOut(BaseModel):
    person_id: Annotated[UUID, ROSTER]
    person_name: Annotated[str, ROSTER]
    budget_line_description: Annotated[str, ROSTER]
    role: Annotated[str | None, C]
    start_date: Annotated[date, C]
    end_date: Annotated[date, C]
    fte_pct: Annotated[Decimal, C]


class AssignmentReportOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    uri: Annotated[str, A]
    name: Annotated[str, A]
    kind: Annotated[str, A]
    status: Annotated[str, A]
    client_name: Annotated[str | None, A]
    contractor_name: Annotated[str | None, A]
    start_date: Annotated[date | None, A]
    end_date: Annotated[date | None, A]
    context_refs: Annotated[list[str], A]
    # client: classes A and B only. internal: adds who worked on it.
    audience: Annotated[str, A]
    generated_on: Annotated[date, A]
    months_total: Annotated[int, A]
    months_closed: Annotated[int, A]
    agreed: Annotated[AgreedOut | None, nested()]
    # The amount entered on the assignment; shown when no quote was accepted.
    quoted_amount_cents: Annotated[int | None, B]
    status_history: Annotated[list[StatusChangeOut], nested()]
    final_report: Annotated[FinalReportOut | None, nested()]
    months: Annotated[list[ReportMonthOut], nested()]
    totals: Annotated[TotalsOut | None, nested()]
    pricing_error: Annotated[str | None, B]
    periods: Annotated[list[ReportPeriodOut], nested()]
    lines: Annotated[list[ReportLineOut], nested()]
    costs: Annotated[list[ReportCostOut], nested()]
    staffing: Annotated[list[ReportStaffingOut], nested()]


# -- steering -----------------------------------------------------------------


class TurnoverMonthOut(BaseModel):
    month: Annotated[str, B]
    # Closed months, at the established inzet.
    realised_cents: Annotated[int, B]
    # Open months of agreed assignments, at the planned inzet.
    forecast_cents: Annotated[int, B]
    # Open months of assignments that are not agreed yet.
    pipeline_cents: Annotated[int, B]


class TurnoverOut(BaseModel):
    # all: every assignment. own: the assignments the reader manages.
    scope: Annotated[str, B]
    months: Annotated[list[TurnoverMonthOut], nested()]
    realised_cents: Annotated[int, B]
    forecast_cents: Annotated[int, B]
    pipeline_cents: Annotated[int, B]
    # Assignments left out because their inzet could not be priced.
    unpriced_assignments: Annotated[list[str], B]


class OccupancyMonthOut(BaseModel):
    month: Annotated[str, COUNTS]
    allocated_fte: Annotated[Decimal, COUNTS]
    available_fte: Annotated[Decimal, COUNTS]
    # Null in a month without anyone available.
    pct: Annotated[Decimal | None, COUNTS]
    under: Annotated[int, COUNTS]
    full: Annotated[int, COUNTS]
    over: Annotated[int, COUNTS]


class PersonOccupancyOut(BaseModel):
    person_id: Annotated[UUID, ROSTER]
    person_name: Annotated[str, ROSTER]
    # Twelve values; null in a month the person was not available.
    months: Annotated[list[Decimal | None], C]
    average_pct: Annotated[Decimal | None, C]


class OccupancyOut(BaseModel):
    # all: everyone available for inzet. own: the persons the reader may see.
    scope: Annotated[str, COUNTS]
    months: Annotated[list[OccupancyMonthOut], nested()]
    persons: Annotated[list[PersonOccupancyOut], nested()]


class PipelineStatusOut(BaseModel):
    status: Annotated[str, B]
    count: Annotated[int, B]
    total_cents: Annotated[int, B]


class PipelineQuoteOut(BaseModel):
    quote_id: Annotated[UUID, B]
    assignment_id: Annotated[UUID, B]
    assignment_name: Annotated[str, B]
    client_name: Annotated[str | None, B]
    status: Annotated[str, B]
    total_cents: Annotated[int, B]
    issued_at: Annotated[datetime, B]
    valid_until: Annotated[str | None, B]


class PipelineOut(BaseModel):
    scope: Annotated[str, B]
    statuses: Annotated[list[PipelineStatusOut], nested()]
    # Issued and waiting for the client.
    waiting: Annotated[list[PipelineQuoteOut], nested()]


class CostCoverageItemOut(BaseModel):
    cost_item_id: Annotated[UUID, B]
    description: Annotated[str, B]
    forecast_cents: Annotated[int, B]
    # Null when the percentages of the item add up to more than 100.
    covered_cents: Annotated[int | None, B]
    uncovered_cents: Annotated[int | None, B]
    pct_total: Annotated[Decimal, B]


class CostCoverageOut(BaseModel):
    scope: Annotated[str, B]
    forecast_cents: Annotated[int, B]
    covered_cents: Annotated[int, B]
    uncovered_cents: Annotated[int, B]
    items: Annotated[list[CostCoverageItemOut], nested()]


class BillabilityOut(BaseModel):
    # all: everyone with a target or inzet. own: the persons the reader may see.
    scope: Annotated[str, F]
    persons: Annotated[list[KpiOut], nested()]
    # Over the persons listed, where the amounts are known.
    target_cents: Annotated[int, F]
    realised_cents: Annotated[int, F]
    forecast_cents: Annotated[int, F]


class OpenRoleOut(BaseModel):
    assignment_id: Annotated[UUID | None, C]
    assignment_name: Annotated[str | None, C]
    budget_line_id: Annotated[UUID | None, C]
    description: Annotated[str, C]
    unfilled_fte: Annotated[Decimal, C]
    start_date: Annotated[date | None, C]
    end_date: Annotated[date | None, C]
    vacancy_status: Annotated[str | None, C]


class OpenRolesOut(BaseModel):
    scope: Annotated[str, C]
    unfilled_fte: Annotated[Decimal, C]
    roles: Annotated[list[OpenRoleOut], nested()]


# -- year account -------------------------------------------------------------


class YearAccountRowOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    uri: Annotated[str, A]
    name: Annotated[str, A]
    kind: Annotated[str, A]
    client_name: Annotated[str | None, A]
    status: Annotated[str, A]
    start_date: Annotated[date | None, A]
    end_date: Annotated[date | None, A]
    agreed_cents: Annotated[int | None, B]
    budgeted_cents: Annotated[int | None, B]
    realised_cents: Annotated[int | None, B]
    forecast_cents: Annotated[int | None, B]
    costs_cents: Annotated[int | None, B]
    billed_cents: Annotated[int, B]
    # Realised and not yet in a billing export.
    to_bill_cents: Annotated[int | None, B]
    # Agreed minus realised.
    difference_cents: Annotated[int | None, B]
    pricing_error: Annotated[str | None, B]


class YearAccountTotalsOut(BaseModel):
    """Over the rows whose amounts the reader sees."""

    agreed_cents: Annotated[int, B]
    budgeted_cents: Annotated[int, B]
    realised_cents: Annotated[int, B]
    forecast_cents: Annotated[int, B]
    costs_cents: Annotated[int, B]
    billed_cents: Annotated[int, B]
    to_bill_cents: Annotated[int, B]


class YearAccountOut(BaseModel):
    year: Annotated[int, A]
    scope: Annotated[str, A]
    rows: Annotated[list[YearAccountRowOut], nested()]
    totals: Annotated[YearAccountTotalsOut | None, nested()]
