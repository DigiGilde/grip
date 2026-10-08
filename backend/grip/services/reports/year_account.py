"""The year account: assignments received and carried out in a budget year.

One row per assignment with something in the year. The amounts of a
multi-year assignment are those of the months in the year, from the pricing
service's per-year split. Agreed is the subtotal of the accepted quote for
the year, as frozen in its snapshot. Billed is what was put in billing
exports for the closed months of the year.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.month_close import BillingExport, MonthClose
from grip.services import assignment_views as views
from grip.services.pricing import DEFAULT_OPTIONS, PricingOptions
from grip.services.reports.assignment_report import accepted_quote

# The columns of the CSV export, in order. Stable: a new column is added at
# the end, an existing one is never renamed or moved. Amounts are in euros
# with a decimal point and two decimals; empty means "not known", which is
# different from zero.
CSV_COLUMNS: tuple[str, ...] = (
    "year",
    "assignment_uri",
    "assignment_name",
    "kind",
    "client_name",
    "status",
    "start_date",
    "end_date",
    "agreed",
    "budgeted",
    "realised",
    "forecast",
    "costs",
    "billed",
    "to_bill",
    "difference",
    "currency",
)


@dataclass(frozen=True)
class YearAccountRow:
    row: views.AssignmentRow
    year: int
    # Subtotal of the accepted quote for the year. None without an accepted
    # quote, or when the quote has nothing in this year.
    agreed_cents: int | None
    # Of the months in the year. None when the assignment cannot be priced.
    totals: views.Totals | None
    pricing_error: str | None
    billed_cents: int

    @property
    def to_bill_cents(self) -> int | None:
        """Realised and not yet in a billing export."""
        if self.totals is None:
            return None
        return self.totals.realised_cents - self.billed_cents

    @property
    def difference_cents(self) -> int | None:
        """Agreed minus realised: what is still to be delivered of the agreement."""
        if self.agreed_cents is None or self.totals is None:
            return None
        return self.agreed_cents - self.totals.realised_cents


async def billed_by_assignment(
    session: AsyncSession, year: int, assignment_ids: Iterable[UUID]
) -> dict[UUID, int]:
    """Billed per assignment in ``year``: the latest export of each closed month.

    An export of a close that was reopened since does not count.
    """
    ids = list(assignment_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(BillingExport)
        .join(MonthClose, MonthClose.id == BillingExport.month_close_id)
        .where(
            BillingExport.assignment_id.in_(ids),
            MonthClose.reopened_at.is_(None),
            func.extract("year", BillingExport.month) == year,
        )
        .order_by(BillingExport.created_at)
    )
    latest: dict[tuple[UUID, date], int] = {}
    for export in result.scalars():
        latest[(export.assignment_id, export.month)] = export.total_cents
    billed: dict[UUID, int] = {}
    for (assignment_id, _month), cents in latest.items():
        billed[assignment_id] = billed.get(assignment_id, 0) + cents
    return billed


def _in_year(row: views.AssignmentRow, year: int) -> bool:
    start, end = row.assignment.start_date, row.assignment.end_date
    if start is None and end is None:
        return False
    return (start is None or start.year <= year) and (end is None or end.year >= year)


async def year_account(
    session: AsyncSession,
    year: int,
    *,
    assignment_ids: Iterable[UUID] | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[YearAccountRow]:
    """The rows of the year account; ``assignment_ids=None`` means all."""
    rows = await views.assignment_rows(session, only_ids=assignment_ids)
    billed = await billed_by_assignment(session, year, [r.assignment.id for r in rows])
    result: list[YearAccountRow] = []
    for row in rows:
        assignment_id = row.assignment.id
        view = await views.assignment_view(
            session, assignment_id, year=year, options=options
        )
        has_amounts = view.totals is not None and (
            view.totals.budgeted_cents or view.totals.used_cents
        )
        if not (
            has_amounts
            or year in view.budgeted_by_year
            or assignment_id in billed
            or _in_year(row, year)
        ):
            continue
        agreed = await accepted_quote(session, assignment_id)
        agreed_cents = None
        if agreed is not None:
            agreed_cents = dict(agreed.subtotals).get(year)
        result.append(
            YearAccountRow(
                row=row,
                year=year,
                agreed_cents=agreed_cents,
                totals=view.totals,
                pricing_error=view.pricing_error,
                billed_cents=billed.get(assignment_id, 0),
            )
        )
    return result


def _euros(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _safe_cell(value: str | None) -> str:
    """Keep a spreadsheet from reading a cell as a formula."""
    text = value or ""
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _iso(day: date | None) -> str:
    return day.isoformat() if day is not None else ""


def to_csv(rows: Iterable[YearAccountRow]) -> str:
    """The year account as CSV: comma separated, UTF-8, columns of ``CSV_COLUMNS``."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for item in rows:
        a = item.row.assignment
        totals = item.totals
        writer.writerow(
            [
                item.year,
                a.uri,
                _safe_cell(a.name),
                a.kind,
                _safe_cell(item.row.client_name),
                a.status,
                _iso(a.start_date),
                _iso(a.end_date),
                _euros(item.agreed_cents),
                _euros(totals.budgeted_cents if totals else None),
                _euros(totals.realised_cents if totals else None),
                _euros(totals.forecast_cents if totals else None),
                _euros(totals.coverage_cents if totals else None),
                _euros(item.billed_cents),
                _euros(item.to_bill_cents),
                _euros(item.difference_cents),
                "EUR",
            ]
        )
    return buffer.getvalue()
