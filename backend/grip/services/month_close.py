"""Monthly close: establish the actual inzet, and produce billing data.

The planned inzet is the proposal. The manager of the assignment adjusts
what differs and closes the month. From then on that month counts with the
established percentages (ADR 0011).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import Month
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment
from grip.models.month_close import (
    BillingExport,
    BillingExportLine,
    MonthClose,
    MonthCloseLine,
)
from grip.models.person import Person
from grip.repositories.domain import AssignmentRepository, MonthCloseRepository
from grip.services import billing_periods
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import ensure_years_open
from grip.services.phase import (
    VERBALLY_AGREED,
    allows_billing,
    allows_month_close,
    status_label,
)
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    CalcInputs,
    PricingOptions,
    load_inputs_for_assignment,
)


@dataclass(frozen=True)
class BillingData:
    """Factuurgegevens of one assignment for one closed month."""

    assignment_id: UUID
    month: Month
    closed_at: datetime
    lines: tuple[calc.BillingLine, ...]

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


async def _assignment_status(session: AsyncSession, assignment_id: UUID) -> str:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", assignment_id)
    return assignment.status


async def ensure_month_can_close(session: AsyncSession, assignment_id: UUID) -> None:
    """Months close only once work has started: after a verbal or a formal
    agreement."""
    status = await _assignment_status(session, assignment_id)
    if not allows_month_close(status):
        raise DomainValidationError(
            f"Een opdracht met status '{status_label(status)}' heeft nog geen "
            "maanden om af te sluiten. Dat kan vanaf een mondeling akkoord."
        )


async def ensure_billable(session: AsyncSession, assignment_id: UUID) -> None:
    """Billing data exists only for a formally accepted assignment."""
    status = await _assignment_status(session, assignment_id)
    if allows_billing(status):
        return
    if status == VERBALLY_AGREED:
        raise DomainValidationError(
            "Deze opdracht heeft alleen een mondeling akkoord. Factuurgegevens "
            "zijn er pas als de offerte formeel is geaccepteerd."
        )
    raise DomainValidationError(
        f"Voor een opdracht met status '{status_label(status)}' zijn er geen "
        "factuurgegevens."
    )


def _lines(
    inputs: CalcInputs,
    month: Month,
    options: PricingOptions,
    actuals: Mapping[tuple[str, Month], Decimal] | None,
) -> tuple[calc.BillingLine, ...]:
    return calc.billing_lines(
        month,
        inputs.allocations,
        inputs.lines,
        inputs.rates,
        inputs.scales,
        actuals=actuals,
        partial_months=options.partial_months,
    )


async def proposal(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> tuple[calc.BillingLine, ...]:
    """The planned inzet of a month, as the proposal for the close."""
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    return _lines(inputs, month, options, None)


async def preview(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    established: Mapping[UUID, Decimal] | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> tuple[calc.BillingLine, ...]:
    """What the month would come to at these percentages. Changes nothing.

    The same lines a close at ``established`` would bill, so the person sees
    the amount follow the percentage before settling it.
    """
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    running = {line.allocation_id for line in _lines(inputs, month, options, None)}
    wanted = {str(k): Decimal(v) for k, v in (established or {}).items()}
    if set(wanted) - running:
        raise DomainValidationError(
            "Er is inzet vastgesteld die niet in deze maand op deze opdracht loopt."
        )
    for pct in wanted.values():
        if not Decimal(0) <= pct <= Decimal(100):
            raise DomainValidationError(
                "Een vastgesteld percentage ligt tussen 0 en 100."
            )
    actuals = {(allocation_id, month): pct for allocation_id, pct in wanted.items()}
    return _lines(inputs, month, options, actuals)


async def close_month(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    actor: Person | None,
    established: Mapping[UUID, Decimal] | None = None,
    closed_at: datetime | None = None,
    allow_closed_year: bool = False,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> MonthClose:
    """Close a month of an assignment.

    ``established`` gives the actual FTE percentage per allocation id where
    it differs from the plan; every other allocation that runs in the month
    is established at its planned percentage. The percentage counts over the
    whole month.
    """
    await ensure_month_can_close(session, assignment_id)
    repo = MonthCloseRepository(session)
    if await repo.in_force(assignment_id, month.first_day) is not None:
        raise DomainValidationError(
            f"De maand {month} is al afgesloten voor deze opdracht."
        )
    closed_years = await ensure_years_open(
        session, [month.year], allow_closed_year=allow_closed_year
    )
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    # Pricing the month now makes a missing rate card or scale fail here, not
    # later when someone asks for the billing data.
    planned = {
        line.allocation_id: line for line in _lines(inputs, month, options, None)
    }
    established = {str(k): Decimal(v) for k, v in (established or {}).items()}
    unknown = set(established) - set(planned)
    if unknown:
        raise DomainValidationError(
            "Er is inzet vastgesteld die niet in deze maand op deze opdracht loopt."
        )
    for pct in established.values():
        if not Decimal(0) <= pct <= Decimal(100):
            raise DomainValidationError(
                "Een vastgesteld percentage ligt tussen 0 en 100."
            )
    planned_pct = {a.id: a.fte_pct for a in inputs.allocations}

    close = MonthClose(
        assignment_id=assignment_id,
        month=month.first_day,
        closed_by_id=actor.id if actor is not None else None,
        closed_at=closed_at or datetime.now(UTC),
    )
    session.add(close)
    await session.flush()
    for allocation_id in planned:
        session.add(
            MonthCloseLine(
                month_close_id=close.id,
                allocation_id=UUID(allocation_id),
                planned_fte_pct=planned_pct[allocation_id],
                established_fte_pct=established.get(
                    allocation_id, planned_pct[allocation_id]
                ),
            )
        )
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="month_close",
        entity_id=close.id,
        new_value={
            "assignment_id": str(assignment_id),
            "month": str(month),
            "established": {
                k: str(established.get(k, planned_pct[k])) for k in sorted(planned)
            },
            **({"closed_year_override": closed_years} if closed_years else {}),
        },
    )
    in_force = await repo.in_force(assignment_id, month.first_day)
    assert in_force is not None
    return in_force


async def reopen_month(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    actor: Person | None,
    reason: str,
    allow_closed_year: bool = False,
) -> MonthClose:
    """Reopen a closed month. The close stays in the trail, marked reopened."""
    if not reason or not reason.strip():
        raise DomainValidationError("Geef een reden voor het heropenen van de maand.")
    close = await MonthCloseRepository(session).in_force(assignment_id, month.first_day)
    if close is None:
        raise DomainValidationError(
            f"De maand {month} is niet afgesloten voor deze opdracht."
        )
    closed_years = await ensure_years_open(
        session, [month.year], allow_closed_year=allow_closed_year
    )
    close.reopened_at = datetime.now(UTC)
    close.reopened_by_id = actor.id if actor is not None else None
    close.reopen_reason = reason.strip()
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="month_close",
        entity_id=close.id,
        old_value={"reopened": False},
        new_value={
            "reopened": True,
            "reason": close.reopen_reason,
            **({"closed_year_override": closed_years} if closed_years else {}),
        },
    )
    # A difference that stood on this month is gone with its delivery: the
    # month is delivered again in full once it is closed again.
    from grip.services import billing_corrections

    if await billing_corrections.open_corrections(session, [assignment_id]):
        await billing_corrections.sync(
            session,
            cause=f"{billing_periods.month_name(month)} is heropend",
            actor=actor,
            assignment_ids=[assignment_id],
        )
    return close


async def billing_data(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> BillingData:
    """Billing data of a closed month, priced at the established inzet.

    The lines name persons (data class C and D). What crosses to a client is
    the role and the amount; see ``create_billing_export``.
    """
    await ensure_billable(session, assignment_id)
    close = await MonthCloseRepository(session).in_force(assignment_id, month.first_day)
    if close is None:
        raise DomainValidationError(
            f"De maand {month} is nog niet afgesloten; er zijn geen factuurgegevens."
        )
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    actuals = {key: pct for key, pct in inputs.actuals.items() if key[1] == month}
    return BillingData(
        assignment_id=assignment_id,
        month=month,
        closed_at=close.closed_at,
        lines=_lines(inputs, month, options, actuals),
    )


async def create_billing_export(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    actor: Person | None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> BillingExport:
    """Freeze the billing data of a closed month as an export run."""
    data = await billing_data(session, assignment_id, month, options=options)
    close = await MonthCloseRepository(session).in_force(assignment_id, month.first_day)
    if close is None:
        raise NotFoundError("Maandafsluiting", str(month))
    lines = await AssignmentRepository(session).budget_lines([assignment_id])
    descriptions = {str(line.id): line.role or line.description for line in lines}
    export = BillingExport(
        assignment_id=assignment_id,
        month=month.first_day,
        month_close_id=close.id,
        total_cents=data.total_cents,
        exported_by_id=actor.id if actor is not None else None,
    )
    session.add(export)
    await session.flush()
    for line in data.lines:
        session.add(
            BillingExportLine(
                billing_export_id=export.id,
                budget_line_id=UUID(line.budget_line_id),
                allocation_id=UUID(line.allocation_id),
                person_id=UUID(line.person_id),
                description=descriptions[line.budget_line_id],
                fte_pct=line.fte_pct,
                category=line.category,
                monthly_rate_cents=line.monthly_rate_cents,
                amount_cents=line.amount_cents,
            )
        )
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="billing_export",
        entity_id=export.id,
        new_value={
            "assignment_id": str(assignment_id),
            "month": str(month),
            "total_cents": data.total_cents,
        },
    )
    return export


async def create_correction_export(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    actor: Person | None,
    reason: str | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> BillingExport:
    """Deliver the difference that arose after a month was delivered.

    The price of a delivered month can change afterwards: a promotion or a
    rate card with effect in the past. What was delivered is a record and is
    never rewritten. The difference between what the month costs now and
    what was delivered for it (the delivery and any earlier corrections) is
    delivered as a correction of its own, a "naverrekening". Its lines refer
    to the month and hold the difference per inzet; a difference can be
    negative.
    """
    data = await billing_data(session, assignment_id, month, options=options)
    close = await MonthCloseRepository(session).in_force(assignment_id, month.first_day)
    if close is None:
        raise NotFoundError("Maandafsluiting", str(month))
    result = await session.execute(
        select(BillingExport)
        .where(BillingExport.month_close_id == close.id)
        .order_by(BillingExport.created_at, BillingExport.id)
    )
    exports = list(result.scalars())
    originals = [e for e in exports if e.kind != "correction"]
    if not originals:
        raise DomainValidationError(
            f"De maand {month} is nog niet aangeleverd. Lever de maand aan; een "
            "naverrekening is er pas na een aanlevering."
        )
    original = originals[-1]
    counted = [original.id] + [
        e.id
        for e in exports
        if e.kind == "correction" and e.created_at >= original.created_at
    ]
    delivered: dict[UUID, int] = {}
    for line in (
        await session.execute(
            select(BillingExportLine).where(
                BillingExportLine.billing_export_id.in_(counted)
            )
        )
    ).scalars():
        delivered[line.allocation_id] = (
            delivered.get(line.allocation_id, 0) + line.amount_cents
        )
    budget_lines = await AssignmentRepository(session).budget_lines([assignment_id])
    descriptions = {
        str(line.id): line.role or line.description for line in budget_lines
    }
    differences = [
        (line, line.amount_cents - delivered.get(UUID(line.allocation_id), 0))
        for line in data.lines
    ]
    differences = [(line, cents) for line, cents in differences if cents != 0]
    if not differences:
        raise DomainValidationError(
            f"Voor {month} is er niets na te verrekenen: wat is aangeleverd is "
            "gelijk aan wat de maand kost."
        )
    total = sum(cents for _, cents in differences)
    reason = (reason or "").strip() or (
        "De prijs van deze maand is na de aanlevering gewijzigd."
    )
    export = BillingExport(
        assignment_id=assignment_id,
        month=month.first_day,
        month_close_id=close.id,
        total_cents=total,
        kind="correction",
        reason=reason,
        exported_by_id=actor.id if actor is not None else None,
    )
    session.add(export)
    await session.flush()
    for line, cents in differences:
        session.add(
            BillingExportLine(
                billing_export_id=export.id,
                budget_line_id=UUID(line.budget_line_id),
                allocation_id=UUID(line.allocation_id),
                person_id=UUID(line.person_id),
                description=(
                    f"Naverrekening {billing_periods.month_name(month)}: "
                    f"{descriptions[line.budget_line_id]}"
                ),
                fte_pct=line.fte_pct,
                category=line.category,
                monthly_rate_cents=line.monthly_rate_cents,
                amount_cents=cents,
            )
        )
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="billing_export",
        entity_id=export.id,
        new_value={
            "assignment_id": str(assignment_id),
            "month": str(month),
            "kind": "correction",
            "corrects": str(original.id),
            "reason": reason,
            "total_cents": total,
        },
    )
    return export
