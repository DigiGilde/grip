"""The year account: assignments received and carried out in a budget year.

One row per assignment with something in the year. The amounts of a
multi-year assignment are those of the months in the year, from the pricing
service's per-year split. Agreed is the subtotal of the accepted quote for
the year, as frozen in its snapshot.

Delivered ("aangeleverd") and invoiced ("gefactureerd") are two facts, and
they come from the invoice service: delivered is billing data exported for
the financial administration, invoiced is an invoice someone recorded as
sent. Until an invoice is recorded, nothing counts as invoiced.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.assignment import BudgetLine
from grip.repositories.domain import AssignmentRepository
from grip.services import assignment_views as views
from grip.services import outgoing_invoices, read_cache
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    inputs_digest,
    load_inputs_by_assignment,
)
from grip.services.reports.assignment_report import Agreed, accepted_quotes

# The columns of the CSV export, in order. Stable: a new column is added at
# the end, an existing one is never renamed or moved. Amounts are in euros
# with a decimal point and two decimals; empty means "not known", which is
# different from zero.
#
# One rename, made before the export was in use: "billed" and "to_bill" are
# now "delivered" and "to_deliver". They always meant billing data delivered
# to the financial administration, and the old names read as invoiced.
#
# "invoiced" and "to_invoice" were added at the end: an invoice recorded as
# sent, and what was delivered without an invoice recorded for it.
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
    "delivered",
    "to_deliver",
    "difference",
    "currency",
    "invoiced",
    "to_invoice",
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
    # Billing data delivered to the financial administration (exports).
    delivered_cents: int
    # Established and priced, and not delivered yet. None when a closed
    # month cannot be priced.
    to_deliver_cents: int | None
    # Invoices recorded as sent, the part that falls in this year.
    invoiced_cents: int
    # Delivered, and no invoice recorded for it.
    to_invoice_cents: int

    @property
    def difference_cents(self) -> int | None:
        """Agreed minus realised: what is still to be delivered of the agreement."""
        if self.agreed_cents is None or self.totals is None:
            return None
        return self.agreed_cents - self.totals.realised_cents


def _in_year(row: views.AssignmentRow, year: int) -> bool:
    start, end = row.assignment.start_date, row.assignment.end_date
    if start is None and end is None:
        return False
    return (start is None or start.year <= year) and (end is None or end.year >= year)


@dataclass(frozen=True)
class _Figures:
    """What the year account computes of one assignment, as plain values."""

    totals: views.Totals | None
    pricing_error: str | None
    # The years the budget has an amount in.
    budgeted_years: tuple[int, ...]
    # Subtotal of the accepted quote for the year.
    agreed_cents: int | None


async def _figures(
    session: AsyncSession,
    assignment_ids: list[UUID],
    year: int,
    options: PricingOptions,
) -> dict[UUID, _Figures]:
    """The figures of several assignments, from what they share read once."""
    lines_of: dict[UUID, list[BudgetLine]] = {i: [] for i in assignment_ids}
    for line in await AssignmentRepository(session).budget_lines(assignment_ids):
        lines_of[line.assignment_id].append(line)
    inputs_of = await load_inputs_by_assignment(
        session,
        assignment_ids,
        options=options,
        lines=[line for own in lines_of.values() for line in own],
    )
    agreed_of = await accepted_quotes(session, assignment_ids)
    found: dict[UUID, _Figures] = {}
    for assignment_id in assignment_ids:
        agreed = agreed_of.get(assignment_id)

        def compute(
            assignment_id: UUID = assignment_id, agreed: Agreed | None = agreed
        ) -> _Figures:
            priced = views.price_lines(
                assignment_id,
                lines_of[assignment_id],
                inputs_of[assignment_id],
                year,
                options,
            )
            return _Figures(
                totals=priced.totals,
                pricing_error=priced.pricing_error,
                budgeted_years=tuple(priced.budgeted_by_year),
                agreed_cents=dict(agreed.subtotals).get(year)
                if agreed is not None
                else None,
            )

        content = read_cache.digest(
            assignment_id,
            inputs_digest(inputs_of[assignment_id]),
            lines_of[assignment_id],
            agreed.subtotals if agreed is not None else None,
            year,
            options,
        )
        found[assignment_id] = read_cache.by_content("year_account", content, compute)
    return found


async def year_account(
    session: AsyncSession,
    year: int,
    *,
    assignment_ids: Iterable[UUID] | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[YearAccountRow]:
    """The rows of the year account; ``assignment_ids=None`` means all."""
    rows = await views.assignment_rows(session, only_ids=assignment_ids)
    ids = [r.assignment.id for r in rows]
    positions = await outgoing_invoices.billing_positions(
        session, ids, year=year, options=options
    )
    figures = await read_cache.remember_many(
        session,
        "year_account",
        ids,
        (year, options),
        lambda missing: _figures(session, missing, year, options),
    )
    result: list[YearAccountRow] = []
    for row in rows:
        assignment_id = row.assignment.id
        position = positions[assignment_id]
        view = figures[assignment_id]
        has_amounts = view.totals is not None and (
            view.totals.budgeted_cents or view.totals.used_cents
        )
        if not (
            has_amounts
            or year in view.budgeted_years
            or position.delivered_cents
            or position.invoiced_cents
            or _in_year(row, year)
        ):
            continue
        result.append(
            YearAccountRow(
                row=row,
                year=year,
                agreed_cents=view.agreed_cents,
                totals=view.totals,
                pricing_error=view.pricing_error,
                delivered_cents=position.delivered_cents,
                to_deliver_cents=position.to_deliver_cents,
                invoiced_cents=position.invoiced_cents,
                to_invoice_cents=position.to_invoice_cents,
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
                _euros(item.delivered_cents),
                _euros(item.to_deliver_cents),
                _euros(item.difference_cents),
                "EUR",
                _euros(item.invoiced_cents),
                _euros(item.to_invoice_cents),
            ]
        )
    return buffer.getvalue()
