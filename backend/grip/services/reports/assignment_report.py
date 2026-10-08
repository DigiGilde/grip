"""The report of one assignment: agreed, delivered, and what it cost.

Agreed is the accepted quote, a frozen snapshot. Delivered is what the
record shows: the status history and the final report from the audit log,
and which months are closed. Cost comes from the same read model the stand
van zaken uses, for the whole period and per year.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.models.audit_log import AuditLog
from grip.models.quote import Quote, QuoteAcceptance
from grip.services import assignment_views as views
from grip.services import month_overview
from grip.services.pricing import DEFAULT_OPTIONS, PricingOptions


@dataclass(frozen=True)
class AgreedLine:
    description: str
    kind: str
    role: str | None
    fte: str | None
    start_date: str | None
    end_date: str | None
    amount_cents: int


@dataclass(frozen=True)
class Agreed:
    quote_id: UUID
    quote_uri: str
    issued_at: datetime
    accepted_at: datetime | None
    form: str | None
    total_cents: int
    lines: tuple[AgreedLine, ...]
    # (year, amount in cents), in order.
    subtotals: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class StatusChange:
    occurred_at: datetime
    old_status: str | None
    new_status: str
    reason: str | None


@dataclass(frozen=True)
class FinalReport:
    issued_at: datetime
    summary: str | None
    delivered: tuple[str, ...]
    not_delivered: tuple[str, ...]


@dataclass(frozen=True)
class PeriodTotals:
    year: int
    totals: views.Totals | None
    pricing_error: str | None


@dataclass(frozen=True)
class CostLine:
    cost_item_id: UUID
    description: str
    budget_line_description: str
    pct: Decimal
    amount_cents: int | None


@dataclass(frozen=True)
class StaffingLine:
    person_id: UUID
    person_name: str
    budget_line_description: str
    role: str | None
    start_date: date
    end_date: date
    fte_pct: Decimal


@dataclass(frozen=True)
class AssignmentReport:
    view: views.AssignmentView
    agreed: Agreed | None
    status_history: tuple[StatusChange, ...]
    final_report: FinalReport | None
    months: tuple[month_overview.MonthState, ...]
    periods: tuple[PeriodTotals, ...]
    costs: tuple[CostLine, ...]
    staffing: tuple[StaffingLine, ...]

    @property
    def closed_month_count(self) -> int:
        return sum(1 for month in self.months if month.closed)


def _cents(money: Any) -> int:
    if isinstance(money, dict):
        value = money.get("amount_cents")
        if isinstance(value, int):
            return value
    return 0


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _agreed_line(line: dict[str, Any]) -> AgreedLine:
    period = line.get("period") if isinstance(line.get("period"), dict) else {}
    return AgreedLine(
        description=str(line.get("description") or ""),
        kind=str(line.get("kind") or ""),
        role=_text(line.get("role")),
        fte=_text(line.get("fte")),
        start_date=_text(period.get("start_date")),
        end_date=_text(period.get("end_date")),
        amount_cents=_cents(line.get("amount")),
    )


async def accepted_quote(session: AsyncSession, assignment_id: UUID) -> Agreed | None:
    """The quote the client accepted, as it was issued. The latest, if several."""
    result = await session.execute(
        select(Quote)
        .where(Quote.assignment_id == assignment_id, Quote.status == "accepted")
        .order_by(Quote.issued_at.desc())
        .limit(1)
    )
    quote = result.scalar_one_or_none()
    if quote is None:
        return None
    acceptance = (
        await session.execute(
            select(QuoteAcceptance)
            .where(QuoteAcceptance.quote_id == quote.id)
            .order_by(QuoteAcceptance.signed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    snapshot = quote.snapshot or {}
    subtotals = tuple(
        (int(entry["year"]), _cents(entry.get("amount")))
        for entry in snapshot.get("subtotals_per_year") or []
        if isinstance(entry, dict) and isinstance(entry.get("year"), int)
    )
    return Agreed(
        quote_id=quote.id,
        quote_uri=quote.uri,
        issued_at=quote.issued_at,
        accepted_at=acceptance.signed_at if acceptance is not None else None,
        form=acceptance.form if acceptance is not None else None,
        total_cents=quote.total_cents,
        lines=tuple(
            _agreed_line(line)
            for line in snapshot.get("lines") or []
            if isinstance(line, dict)
        ),
        subtotals=subtotals,
    )


def _in_order(changes: list[StatusChange]) -> list[StatusChange]:
    """Status changes in the order they happened.

    Audit rows of one transaction share a timestamp, so within a timestamp
    the order follows the chain: each change starts where the previous ended.
    """
    ordered: list[StatusChange] = []
    remaining = sorted(changes, key=lambda change: change.occurred_at)
    current: str | None = None
    while remaining:
        stamp = remaining[0].occurred_at
        group = [c for c in remaining if c.occurred_at == stamp]
        pick = next((c for c in group if c.old_status == current), group[0])
        ordered.append(pick)
        remaining.remove(pick)
        current = pick.new_status
    return ordered


async def status_history(
    session: AsyncSession, assignment_id: UUID
) -> tuple[StatusChange, ...]:
    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.entity == "assignment", AuditLog.entity_id == str(assignment_id)
        )
        .order_by(AuditLog.occurred_at)
    )
    changes: list[StatusChange] = []
    for row in result.scalars():
        new = row.new_value or {}
        status = new.get("status")
        if not isinstance(status, str):
            continue
        old = (row.old_value or {}).get("status")
        changes.append(
            StatusChange(
                occurred_at=row.occurred_at,
                old_status=old if isinstance(old, str) else None,
                new_status=status,
                reason=_text(new.get("reason")),
            )
        )
    return tuple(_in_order(changes))


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


async def final_report(
    session: AsyncSession, assignment_id: UUID
) -> FinalReport | None:
    """The final report as it was issued; the latest, if it was issued again."""
    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.entity == "final_report",
            AuditLog.entity_id == str(assignment_id),
        )
        .order_by(AuditLog.occurred_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    body = row.new_value or {}
    return FinalReport(
        issued_at=row.occurred_at,
        summary=_text(body.get("summary")),
        delivered=_strings(body.get("delivered")),
        not_delivered=_strings(body.get("not_delivered")),
    )


async def assignment_report(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
    today: date | None = None,
) -> AssignmentReport:
    """Everything the report of one assignment shows. Raises when it does not exist."""
    view = await views.assignment_view(session, assignment_id, options=options)
    months = await month_overview.timeline(session, assignment_id, today=today)

    years = set(view.budgeted_by_year) | {state.month.year for state in months}
    periods: list[PeriodTotals] = []
    for year in sorted(years):
        year_view = await views.assignment_view(
            session, assignment_id, year=year, options=options
        )
        periods.append(
            PeriodTotals(
                year=year,
                totals=year_view.totals,
                pricing_error=year_view.pricing_error,
            )
        )

    costs: list[CostLine] = []
    staffing: list[StaffingLine] = []
    for line_view in view.lines:
        line = line_view.line
        for coverage in line_view.coverages:
            costs.append(
                CostLine(
                    cost_item_id=coverage.cost_item_id,
                    description=coverage.description,
                    budget_line_description=line.description,
                    pct=Decimal(str(coverage.pct)),
                    amount_cents=coverage.amount_cents,
                )
            )
        for member in line_view.allocations:
            allocation = member.allocation
            staffing.append(
                StaffingLine(
                    person_id=allocation.person_id,
                    person_name=member.person_name,
                    budget_line_description=line.description,
                    role=line.role,
                    start_date=allocation.start_date,
                    end_date=allocation.end_date,
                    fte_pct=allocation.fte_pct,
                )
            )

    return AssignmentReport(
        view=view,
        agreed=await accepted_quote(session, assignment_id),
        status_history=await status_history(session, assignment_id),
        final_report=await final_report(session, assignment_id),
        months=tuple(months),
        periods=tuple(periods),
        costs=tuple(costs),
        staffing=tuple(staffing),
    )


def progress_summary(report: AssignmentReport) -> dict[str, Any]:
    """Class A facts about progress, free of money and of names.

    This is the part of the report that an answer to a client's pull for
    progress could carry beyond the bare status.
    """
    last = report.status_history[-1] if report.status_history else None
    return {
        "status": report.view.row.assignment.status,
        "status_since": clock.local_date(last.occurred_at).isoformat()
        if last
        else None,
        "months_total": len(report.months),
        "months_closed": report.closed_month_count,
        "final_report_issued": report.final_report is not None,
    }
