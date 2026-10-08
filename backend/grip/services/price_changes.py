"""One rule for "the price of a past month changed", whatever the cause.

Grip invoices what the work costs, always at the correct rate. The price of
a month follows from the inzet, the billing scale of the person and the rate
card valid on each day. Two things can change that price afterwards: a
billing scale recorded with a start date in the past (a promotion decided in
September with effect from 1 July), and a rate card that takes effect in the
past. Both are the truth and both are allowed. What happens then is the same
in both cases:

- An open month simply prices right from then on.
- A closed month that was not delivered yet prices right too: a close
  stores the established percentage, never an amount.
- A month that was already delivered keeps its delivery as it was. A
  delivery is a record of what went to the financial administration. The
  difference becomes a correction to deliver (a "naverrekening"), which
  counts as still to deliver until it is delivered, and as still to invoice
  until an invoice is recorded on it. A negative difference works the same.

Nothing has to detect the cause for this to hold: what is still to deliver
for a month is always what the month costs now minus what was delivered for
it. This module shows the effect before a change is saved (``preview``), and
tells the task layer when a correction arises (``emit_new_corrections``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import Month
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.month_close import BillingExport
from grip.models.person import Person
from grip.services import outgoing_invoices
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    load_inputs_for_assignment,
)

# True while a change is only being tried out. Nothing announces itself then.
_previewing: ContextVar[bool] = ContextVar("grip_price_preview", default=False)

OPEN = "open"
CLOSED = "closed"
DELIVERED = "delivered"
INVOICED = "invoiced"


def is_preview() -> bool:
    return _previewing.get()


@dataclass(frozen=True)
class MonthChange:
    month: Month
    # open, closed (not delivered), delivered or invoiced.
    state: str
    before_cents: int | None
    after_cents: int | None
    invoice_number: str | None = None

    @property
    def difference_cents(self) -> int:
        return (self.after_cents or 0) - (self.before_cents or 0)


@dataclass(frozen=True)
class AssignmentImpact:
    assignment_id: UUID
    assignment_name: str
    months: tuple[MonthChange, ...]

    def _sum(self, *states: str) -> int:
        return sum(m.difference_cents for m in self.months if m.state in states)

    @property
    def open_difference_cents(self) -> int:
        return self._sum(OPEN)

    @property
    def closed_difference_cents(self) -> int:
        """Closed and not delivered: prices right from now on."""
        return self._sum(CLOSED)

    @property
    def correction_cents(self) -> int:
        """Already delivered: becomes a correction to deliver."""
        return self._sum(DELIVERED, INVOICED)


@dataclass(frozen=True)
class PriceImpact:
    """What a change does to what is already priced."""

    assignments: tuple[AssignmentImpact, ...]
    budget_lines_changed: int
    budget_difference_cents: int
    allocations_changed: int
    # Months that can no longer be priced after the change (a gap).
    unpriced_months: int

    @property
    def open_difference_cents(self) -> int:
        return sum(a.open_difference_cents for a in self.assignments)

    @property
    def closed_difference_cents(self) -> int:
        return sum(a.closed_difference_cents for a in self.assignments)

    @property
    def correction_cents(self) -> int:
        return sum(a.correction_cents for a in self.assignments)

    @property
    def reaches_into_the_past(self) -> bool:
        return any(m.state != OPEN for a in self.assignments for m in a.months)


@dataclass(frozen=True)
class _Snapshot:
    months: dict[tuple[UUID, Month], int | None]
    allocations: dict[UUID, int | None]
    budget_lines: dict[UUID, int | None]


async def _snapshot(
    session: AsyncSession,
    since: date,
    person_id: UUID | None,
    options: PricingOptions,
) -> _Snapshot:
    """The price of everything from ``since`` on, as it stands now."""
    stmt = (
        select(BudgetLine.assignment_id)
        .join(Allocation, Allocation.budget_line_id == BudgetLine.id, isouter=True)
        .where(BudgetLine.kind == "personnel", BudgetLine.end_date >= since)
        .distinct()
    )
    if person_id is not None:
        stmt = stmt.where(Allocation.person_id == person_id)
    months: dict[tuple[UUID, Month], int | None] = {}
    allocations: dict[UUID, int | None] = {}
    budget_lines: dict[UUID, int | None] = {}
    first = Month.of(since)
    for assignment_id in (await session.execute(stmt)).scalars():
        inputs = await load_inputs_for_assignment(
            session, assignment_id, options=options
        )
        for line in inputs.lines:
            if line.kind is not calc.BudgetLineKind.PERSONNEL or person_id is not None:
                continue
            if line.end_date is None or line.end_date < since:
                continue
            try:
                budget_lines[UUID(line.id)] = sum(
                    m.cents
                    for m in calc.budget_line_months(
                        line, inputs.rates, partial_months=options.partial_months
                    )
                    if m.month >= first
                )
            except calc.CalcError:
                budget_lines[UUID(line.id)] = None
        for allocation in inputs.allocations:
            if allocation.end_date < since:
                continue
            if person_id is not None and allocation.person_id != str(person_id):
                continue
            try:
                priced = [
                    m
                    for m in calc.allocation_months(
                        allocation,
                        inputs.rates,
                        inputs.scales,
                        partial_months=options.partial_months,
                        actuals=inputs.actuals,
                    )
                    if m.month >= first
                ]
            except calc.CalcError:
                allocations[UUID(allocation.id)] = None
                for month in calc.months_between(
                    max(allocation.start_date, since), allocation.end_date
                ):
                    months[(assignment_id, month)] = None
                continue
            allocations[UUID(allocation.id)] = sum(m.cents for m in priced)
            for amount in priced:
                key = (assignment_id, amount.month)
                if key in months and months[key] is None:
                    continue
                months[key] = (months.get(key) or 0) + amount.cents
    return _Snapshot(months, allocations, budget_lines)


async def _states(
    session: AsyncSession, assignment_id: UUID, options: PricingOptions
) -> dict[Month, tuple[str, str | None]]:
    result = {}
    for month in await outgoing_invoices.month_billing(
        session, assignment_id, options=options
    ):
        if not month.closed:
            continue
        if month.invoice_id is not None:
            state = INVOICED
        elif month.export_id is not None:
            state = DELIVERED
        else:
            state = CLOSED
        result[Month.of(month.month)] = (state, month.invoice_number)
    return result


def _differs(before: int | None, after: int | None) -> bool:
    return before != after


async def preview(
    session: AsyncSession,
    change: Callable[[], Awaitable[object]],
    *,
    since: date,
    person_id: UUID | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> PriceImpact:
    """What ``change`` would do to prices from ``since`` on. Saves nothing.

    The change is really made, inside a savepoint that is rolled back, so the
    preview is what saving gives and not an estimate of it. Objects the
    change touched are stale afterwards; a caller that needs them reads them
    again.
    """
    before = await _snapshot(session, since, person_id, options)
    savepoint = await session.begin_nested()
    token = _previewing.set(True)
    try:
        await change()
        await session.flush()
        after = await _snapshot(session, since, person_id, options)
    finally:
        _previewing.reset(token)
        await savepoint.rollback()

    changed: dict[UUID, list[Month]] = {}
    for key in set(before.months) | set(after.months):
        if _differs(before.months.get(key), after.months.get(key)):
            changed.setdefault(key[0], []).append(key[1])
    names: dict[UUID, str] = {}
    if changed:
        rows = await session.execute(
            select(Assignment.id, Assignment.name).where(Assignment.id.in_(changed))
        )
        names = {row[0]: row[1] for row in rows}
    assignments = []
    for assignment_id, months in changed.items():
        states = await _states(session, assignment_id, options)
        assignments.append(
            AssignmentImpact(
                assignment_id=assignment_id,
                assignment_name=names.get(assignment_id, ""),
                months=tuple(
                    MonthChange(
                        month=month,
                        state=states.get(month, (OPEN, None))[0],
                        before_cents=before.months.get((assignment_id, month)),
                        after_cents=after.months.get((assignment_id, month)),
                        invoice_number=states.get(month, (OPEN, None))[1],
                    )
                    for month in sorted(months)
                ),
            )
        )
    assignments.sort(key=lambda a: a.assignment_name)
    line_ids = set(before.budget_lines) | set(after.budget_lines)
    lines_changed = [
        i
        for i in line_ids
        if _differs(before.budget_lines.get(i), after.budget_lines.get(i))
    ]
    allocation_ids = set(before.allocations) | set(after.allocations)
    return PriceImpact(
        assignments=tuple(assignments),
        budget_lines_changed=len(lines_changed),
        budget_difference_cents=sum(
            (after.budget_lines.get(i) or 0) - (before.budget_lines.get(i) or 0)
            for i in lines_changed
        ),
        allocations_changed=sum(
            1
            for i in allocation_ids
            if _differs(before.allocations.get(i), after.allocations.get(i))
        ),
        unpriced_months=sum(
            1
            for key, cents in after.months.items()
            if cents is None and before.months.get(key) is not None
        ),
    )


async def pending_corrections(
    session: AsyncSession, *, options: PricingOptions = DEFAULT_OPTIONS
) -> dict[tuple[UUID, date], int]:
    """Per delivered month what is still to deliver for it: what the month
    costs now minus what was delivered. Months without a difference are left
    out."""
    if is_preview():
        return {}
    result: dict[tuple[UUID, date], int] = {}
    rows = await session.execute(select(BillingExport.assignment_id).distinct())
    for assignment_id in rows.scalars():
        for month in await outgoing_invoices.month_billing(
            session, assignment_id, options=options
        ):
            if not month.closed or month.export_id is None:
                continue
            difference = month.to_deliver_cents
            if difference:
                result[(assignment_id, month.month)] = difference
    return result


async def emit_new_corrections(
    session: AsyncSession,
    before: dict[tuple[UUID, date], int],
    *,
    cause: str,
    actor: Person | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[tuple[UUID, date, int]]:
    """Record the corrections that arose since ``before`` was taken.

    The difference on a delivered month becomes a stored correction on its
    billing period (``grip.services.billing_corrections``), in this same
    transaction; a difference that is gone takes its correction away. Each
    correction that arose or changed is announced once as
    ``billing_correction.arose``, so the task layer asks someone to deliver
    it.
    """
    if is_preview():
        return []
    # Imported here: that module reads the months through this one's pricing.
    from grip.services import billing_corrections

    now_pending = await pending_corrections(session, options=options)
    changed = {
        key[0]
        for key in set(before) | set(now_pending)
        if before.get(key) != now_pending.get(key)
    }
    if not changed:
        return []
    await billing_corrections.sync(
        session, cause=cause, actor=actor, assignment_ids=changed
    )
    return [
        (key[0], key[1], difference)
        for key, difference in now_pending.items()
        if before.get(key) != difference
    ]
