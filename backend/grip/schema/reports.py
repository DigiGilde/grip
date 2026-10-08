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
from grip.schema.finance import FiguresOut
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
    # Open months of assignments agreed formally or verbally, planned inzet.
    forecast_cents: Annotated[int, B]
    # The part of the forecast that rests on a verbal agreement only.
    verbal_cents: Annotated[int, B]
    # Open months of assignments that are not agreed yet.
    pipeline_cents: Annotated[int, B]


class TurnoverOut(BaseModel):
    # all: every assignment. own: the assignments the reader manages.
    scope: Annotated[str, B]
    months: Annotated[list[TurnoverMonthOut], nested()]
    realised_cents: Annotated[int, B]
    forecast_cents: Annotated[int, B]
    verbal_cents: Annotated[int, B]
    pipeline_cents: Annotated[int, B]
    # Realised plus forecast: what the year is expected to bring.
    expected_cents: Annotated[int, B]
    # The year in the words of the assignment pages, over the assignments
    # that are agreed formally or verbally: budgeted, realised, planned,
    # costs, expected total, variance and the share realised.
    figures: Annotated[FiguresOut, nested()]
    # Assignments left out because their inzet could not be priced.
    unpriced_assignments: Annotated[list[str], B]


class OccupancyMonthOut(BaseModel):
    month: Annotated[str, COUNTS]
    allocated_fte: Annotated[Decimal, COUNTS]
    # The tentative part of what is allocated: inzet on potential assignments.
    tentative_fte: Annotated[Decimal, COUNTS]
    available_fte: Annotated[Decimal, COUNTS]
    # Room left, with nobody's overbooking set off against it.
    free_fte: Annotated[Decimal, COUNTS]
    # Null in a month without anyone available.
    pct: Annotated[Decimal | None, COUNTS]
    under: Annotated[int, COUNTS]
    full: Annotated[int, COUNTS]
    over: Annotated[int, COUNTS]


class OccupancySummaryOut(BaseModel):
    """The figures on top, over the persons in the block and no one else."""

    person_count: Annotated[int, COUNTS]
    average_pct: Annotated[Decimal | None, COUNTS]
    # Persons above 100 percent in some month of the year, and which months.
    over_count: Annotated[int, COUNTS]
    over_months: Annotated[list[str], COUNTS]
    # Today's month, whatever year is on screen.
    current_month: Annotated[str, COUNTS]
    # This month and the three after it.
    window: Annotated[list[OccupancyMonthOut], nested()]
    # Available in the coming three months without any inzet in them.
    idle_count: Annotated[int, COUNTS]


class OccupancyPartOut(BaseModel):
    """What one assignment takes of a person in a month.

    The percentage is staffing (class C of the person). Which assignment it
    is, is class A of that assignment: a reader who may not see the
    assignment gets the part without its name.
    """

    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    pct: Annotated[Decimal, C]
    tentative: Annotated[bool, C]
    verbally_agreed: Annotated[bool, C]
    established: Annotated[bool, C]


class OccupancyCellOut(BaseModel):
    month: Annotated[str, C]
    # False in a month the person could not be deployed.
    available: Annotated[bool, C]
    pct: Annotated[Decimal, C]
    tentative_pct: Annotated[Decimal, C]
    # Everything in the cell comes from closed months.
    established: Annotated[bool, C]
    parts: Annotated[list[OccupancyPartOut], nested()]


class PersonOccupancyOut(BaseModel):
    person_id: Annotated[UUID, ROSTER]
    person_name: Annotated[str, ROSTER]
    # Mean over the months the person was available.
    average_pct: Annotated[Decimal | None, C]
    over_months: Annotated[list[str], C]
    # Allocated this month, whatever year is on screen. Null when the
    # person cannot be deployed this month.
    now_pct: Annotated[Decimal | None, C]
    # Counted by the figure "zonder inzet de komende drie maanden".
    idle_ahead: Annotated[bool, C]
    # The last day of inzet on any assignment; null without any.
    last_inzet_end: Annotated[date | None, C]
    cells: Annotated[list[OccupancyCellOut], nested()]


class NotDeployableOut(BaseModel):
    person_id: Annotated[UUID, ROSTER]
    person_name: Annotated[str, ROSTER]


class OccupancyOut(BaseModel):
    # all: everyone available for inzet. own: the persons the reader may see.
    scope: Annotated[str, COUNTS]
    summary: Annotated[OccupancySummaryOut, nested()]
    months: Annotated[list[OccupancyMonthOut], nested()]
    persons: Annotated[list[PersonOccupancyOut], nested()]
    # Active persons the reader may see who are no row: no billing scale and
    # no inzet in the year.
    not_deployable: Annotated[list[NotDeployableOut], nested()]


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
    # Realised plus forecast.
    realisation_cents: Annotated[int, F]
    # Of the persons listed: how many have a target, and how many of those
    # are expected to end the year below it.
    with_target_count: Annotated[int, F]
    below_target_count: Annotated[int, F]


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
    # Billing data delivered to the financial administration. Not invoiced:
    # grip only knows of an invoice once one is recorded.
    delivered_cents: Annotated[int, B]
    # Established and not yet in a billing export.
    to_deliver_cents: Annotated[int | None, B]
    # An invoice recorded as sent, and what was delivered without one.
    invoiced_cents: Annotated[int, B]
    to_invoice_cents: Annotated[int, B]
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
    delivered_cents: Annotated[int, B]
    to_deliver_cents: Annotated[int, B]
    invoiced_cents: Annotated[int, B]
    to_invoice_cents: Annotated[int, B]


class YearAccountOut(BaseModel):
    year: Annotated[int, A]
    scope: Annotated[str, A]
    rows: Annotated[list[YearAccountRowOut], nested()]
    totals: Annotated[YearAccountTotalsOut | None, nested()]
