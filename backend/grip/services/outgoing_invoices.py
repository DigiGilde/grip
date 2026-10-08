"""Delivered and invoiced: what grip knows about billing, and no more.

Three facts, each with its own word:

- **Aangeleverd** (delivered): billing data of a closed month was exported
  for the financial administration. That is a ``billing_export``.
- **Gefactureerd** (invoiced): an invoice was actually sent. Grip cannot see
  that, so someone records it here as an ``outgoing_invoice`` on one or
  several deliveries. Until then no amount counts as invoiced.
- **Betaald** (paid): not recorded. Nothing in grip says so.

The delivery that counts for a month is the latest export made from the
close that is in force. Reopening a month takes its delivery out of force;
an invoice recorded on it stays what it is, a fact, and the month then
shows that the invoice rests on an earlier delivery.

The amount of an invoice that covers several months is spread over those
months in proportion to what was delivered for each, so figures per year add
up to the invoice amount.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip import calc
from grip.calc import Month
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment
from grip.models.month_close import BillingExport, MonthClose
from grip.models.outgoing_invoice import (
    INVOICE_SOURCES,
    OutgoingInvoice,
    OutgoingInvoiceDelivery,
)
from grip.models.person import Person
from grip.services import events
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.phase import allows_billing
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    load_inputs_for_assignment,
)

NOT_DELIVERED = "not_delivered"
DELIVERED = "delivered"
INVOICED = "invoiced"

SOURCE_MANUAL = "manual"
SOURCE_FINANCIAL_SYSTEM = "financial_system"


@dataclass(frozen=True)
class MonthBilling:
    """Where one month of an assignment stands: delivered, invoiced, or neither."""

    # First day of the month.
    month: date
    # False when the month was reopened after an invoice was recorded on it.
    closed: bool
    state: str
    # What a delivery made now would hold: the established inzet of the
    # month priced at the rate card. None when the month is not closed or
    # cannot be priced.
    deliverable_cents: int | None
    # The delivery in force.
    export_id: UUID | None
    delivered_at: datetime | None
    delivered_by_name: str | None
    delivered_cents: int | None
    invoice_id: UUID | None
    invoice_number: str | None
    invoice_date: date | None
    # This month's share of the invoice amount.
    invoiced_cents: int | None
    # The invoice was recorded on a delivery that is no longer the one in
    # force: the month was delivered again, or reopened.
    invoice_on_earlier_delivery: bool

    @property
    def to_deliver_cents(self) -> int | None:
        if self.deliverable_cents is None:
            return None
        return self.deliverable_cents - (self.delivered_cents or 0)

    @property
    def to_invoice_cents(self) -> int:
        return (self.delivered_cents or 0) - (self.invoiced_cents or 0)


@dataclass(frozen=True)
class BillingPosition:
    """Delivered and invoiced of one assignment, for a year or the whole period.

    A month belongs to the year it falls in, whenever it was delivered or
    invoiced.
    """

    assignment_id: UUID
    # None means the whole period.
    year: int | None
    # Whether billing data may be produced at all in the current status.
    billable: bool
    # Established inzet of the closed months, priced. None when a month
    # cannot be priced.
    deliverable_cents: int | None
    delivered_cents: int
    invoiced_cents: int
    months: tuple[MonthBilling, ...]

    @property
    def to_deliver_cents(self) -> int | None:
        """Nog aan te leveren: closed, priced, and not delivered yet."""
        if self.deliverable_cents is None:
            return None
        return self.deliverable_cents - self.delivered_cents

    @property
    def to_invoice_cents(self) -> int:
        """Nog te factureren: delivered, and no invoice recorded for it."""
        return self.delivered_cents - self.invoiced_cents


@dataclass(frozen=True)
class InvoiceDelivery:
    export_id: UUID
    month: date
    delivered_cents: int
    # False when the export is no longer the delivery in force of its month.
    in_force: bool


@dataclass(frozen=True)
class InvoiceView:
    invoice: OutgoingInvoice
    deliveries: tuple[InvoiceDelivery, ...]
    recorded_by_name: str | None
    withdrawn_by_name: str | None

    @property
    def delivered_cents(self) -> int:
        return sum(d.delivered_cents for d in self.deliveries)

    @property
    def difference_cents(self) -> int:
        """Invoice amount minus what was delivered for it."""
        return self.invoice.amount_cents - self.delivered_cents


# -- reading ------------------------------------------------------------------


async def _names(session: AsyncSession, person_ids: set[UUID]) -> dict[UUID, str]:
    if not person_ids:
        return {}
    rows = await session.execute(
        select(Person.id, Person.name).where(Person.id.in_(person_ids))
    )
    return {row[0]: row[1] for row in rows}


async def _exports(session: AsyncSession, assignment_id: UUID) -> list[BillingExport]:
    result = await session.execute(
        select(BillingExport)
        .where(BillingExport.assignment_id == assignment_id)
        .order_by(BillingExport.created_at, BillingExport.id)
    )
    return list(result.scalars())


async def _closes_in_force(
    session: AsyncSession, assignment_id: UUID
) -> dict[date, UUID]:
    rows = await session.execute(
        select(MonthClose.month, MonthClose.id).where(
            MonthClose.assignment_id == assignment_id,
            MonthClose.reopened_at.is_(None),
        )
    )
    return {row[0]: row[1] for row in rows}


def _current_exports(
    exports: Iterable[BillingExport], closes: dict[date, UUID]
) -> dict[date, BillingExport]:
    """Per month the delivery in force: the latest export of the close in force.

    A correction (naverrekening) is not a delivery of the month but an
    addition to it; see ``_corrections``.
    """
    current: dict[date, BillingExport] = {}
    for export in exports:
        if (
            closes.get(export.month) == export.month_close_id
            and export.kind != "correction"
        ):
            current[export.month] = export
    return current


def _corrections(
    exports: Iterable[BillingExport], current: dict[date, BillingExport]
) -> dict[date, list[BillingExport]]:
    """Per month the corrections delivered on top of the delivery in force."""
    found: dict[date, list[BillingExport]] = {}
    for export in exports:
        original = current.get(export.month)
        if (
            export.kind == "correction"
            and original is not None
            and export.month_close_id == original.month_close_id
            and export.created_at >= original.created_at
        ):
            found.setdefault(export.month, []).append(export)
    return found


async def _invoices_in_force(
    session: AsyncSession, assignment_id: UUID
) -> list[OutgoingInvoice]:
    result = await session.execute(
        select(OutgoingInvoice)
        .where(
            OutgoingInvoice.assignment_id == assignment_id,
            OutgoingInvoice.withdrawn_at.is_(None),
        )
        .options(selectinload(OutgoingInvoice.deliveries))
        .order_by(OutgoingInvoice.invoice_date, OutgoingInvoice.created_at)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


def spread(amount_cents: int, weights: list[int]) -> list[int]:
    """Split an amount over parts in proportion to their weights, exactly.

    The parts add up to the amount; the last part takes the rounding rest.
    Without any weight the amount is split evenly.
    """
    if not weights:
        return []
    total = sum(weights)
    if total == 0:
        weights = [1] * len(weights)
        total = len(weights)
    parts = [amount_cents * weight // total for weight in weights[:-1]]
    parts.append(amount_cents - sum(parts))
    return parts


async def _deliverable(
    session: AsyncSession,
    assignment_id: UUID,
    months: Iterable[date],
    options: PricingOptions,
) -> dict[date, int | None]:
    """Per closed month what a delivery made now would hold."""
    wanted = sorted(set(months))
    if not wanted:
        return {}
    try:
        inputs = await load_inputs_for_assignment(
            session, assignment_id, options=options
        )
    except calc.CalcError:
        return dict.fromkeys(wanted)
    result: dict[date, int | None] = {}
    for first_day in wanted:
        month = Month.of(first_day)
        actuals = {key: pct for key, pct in inputs.actuals.items() if key[1] == month}
        try:
            lines = calc.billing_lines(
                month,
                inputs.allocations,
                inputs.lines,
                inputs.rates,
                inputs.scales,
                actuals=actuals,
                partial_months=options.partial_months,
            )
        except calc.CalcError:
            result[first_day] = None
            continue
        result[first_day] = sum(line.amount_cents for line in lines)
    return result


async def month_billing(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> tuple[MonthBilling, ...]:
    """Every closed month of the assignment, and every month with an invoice.

    In order of month. A month that was reopened after an invoice was
    recorded on it is listed too, with ``closed`` false.
    """
    exports = await _exports(session, assignment_id)
    by_id = {export.id: export for export in exports}
    closes = await _closes_in_force(session, assignment_id)
    current = _current_exports(exports, closes)
    corrections = _corrections(exports, current)
    invoices = await _invoices_in_force(session, assignment_id)

    # Per month: the invoice, this month's share of its amount, and whether
    # it rests on the delivery in force.
    invoiced: dict[date, tuple[OutgoingInvoice, int, bool]] = {}
    for invoice in invoices:
        linked = [
            by_id[d.billing_export_id]
            for d in invoice.deliveries
            if d.billing_export_id in by_id
        ]
        linked.sort(key=lambda export: (export.month, export.created_at))
        shares = spread(invoice.amount_cents, [e.total_cents for e in linked])
        for export, share in zip(linked, shares, strict=True):
            in_force = current.get(export.month) is export or any(
                export is correction for correction in corrections.get(export.month, [])
            )
            previous = invoiced.get(export.month)
            invoiced[export.month] = (
                invoice,
                share + (previous[1] if previous else 0),
                in_force and (previous[2] if previous else True),
            )

    deliverable = await _deliverable(session, assignment_id, closes, options)
    names = await _names(
        session, {e.exported_by_id for e in current.values() if e.exported_by_id}
    )

    result = []
    for first_day in sorted(set(closes) | set(invoiced)):
        export = current.get(first_day)
        entry = invoiced.get(first_day)
        if entry is not None:
            state = INVOICED
        elif export is not None:
            state = DELIVERED
        else:
            state = NOT_DELIVERED
        result.append(
            MonthBilling(
                month=first_day,
                closed=first_day in closes,
                state=state,
                deliverable_cents=deliverable.get(first_day),
                export_id=export.id if export else None,
                delivered_at=export.created_at if export else None,
                delivered_by_name=names.get(export.exported_by_id)
                if export and export.exported_by_id
                else None,
                # The delivery in force plus the corrections on top of it.
                delivered_cents=export.total_cents
                + sum(c.total_cents for c in corrections.get(first_day, []))
                if export
                else None,
                invoice_id=entry[0].id if entry else None,
                invoice_number=entry[0].invoice_number if entry else None,
                invoice_date=entry[0].invoice_date if entry else None,
                invoiced_cents=entry[1] if entry else None,
                invoice_on_earlier_delivery=bool(entry) and not entry[2],
            )
        )
    return tuple(result)


def position_from_months(
    assignment_id: UUID,
    months: Iterable[MonthBilling],
    *,
    year: int | None,
    billable: bool,
) -> BillingPosition:
    """Add months up to a position, for one year or the whole period."""
    chosen = tuple(m for m in months if year is None or m.month.year == year)
    closed = [m for m in chosen if m.closed]
    priced = all(m.deliverable_cents is not None for m in closed)
    return BillingPosition(
        assignment_id=assignment_id,
        year=year,
        billable=billable,
        deliverable_cents=sum(m.deliverable_cents or 0 for m in closed)
        if priced
        else None,
        delivered_cents=sum(m.delivered_cents or 0 for m in chosen),
        invoiced_cents=sum(m.invoiced_cents or 0 for m in chosen),
        months=chosen,
    )


async def billing_position(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> BillingPosition:
    """Delivered, invoiced and what is still open, of one assignment."""
    assignment = await get_assignment(session, assignment_id)
    months = await month_billing(session, assignment_id, options=options)
    return position_from_months(
        assignment_id, months, year=year, billable=allows_billing(assignment.status)
    )


async def billing_positions(
    session: AsyncSession,
    assignment_ids: Iterable[UUID],
    *,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> dict[UUID, BillingPosition]:
    """The position of several assignments at once, keyed by assignment id."""
    return {
        assignment_id: await billing_position(
            session, assignment_id, year=year, options=options
        )
        for assignment_id in dict.fromkeys(assignment_ids)
    }


async def invoices_of_assignment(
    session: AsyncSession, assignment_id: UUID, *, include_withdrawn: bool = True
) -> list[InvoiceView]:
    """The recorded invoices of an assignment, newest invoice date first."""
    stmt = (
        select(OutgoingInvoice)
        .where(OutgoingInvoice.assignment_id == assignment_id)
        .options(selectinload(OutgoingInvoice.deliveries))
        .order_by(
            OutgoingInvoice.invoice_date.desc(), OutgoingInvoice.created_at.desc()
        )
        .execution_options(populate_existing=True)
    )
    if not include_withdrawn:
        stmt = stmt.where(OutgoingInvoice.withdrawn_at.is_(None))
    invoices = list((await session.execute(stmt)).scalars())
    return await _views(session, assignment_id, invoices)


async def invoice_view(session: AsyncSession, invoice_id: UUID) -> InvoiceView:
    invoice = await get_invoice(session, invoice_id)
    return (await _views(session, invoice.assignment_id, [invoice]))[0]


async def _views(
    session: AsyncSession, assignment_id: UUID, invoices: list[OutgoingInvoice]
) -> list[InvoiceView]:
    exports = await _exports(session, assignment_id)
    by_id = {export.id: export for export in exports}
    current = _current_exports(exports, await _closes_in_force(session, assignment_id))
    names = await _names(
        session,
        {
            pid
            for invoice in invoices
            for pid in (invoice.recorded_by_id, invoice.withdrawn_by_id)
            if pid is not None
        },
    )
    views = []
    for invoice in invoices:
        deliveries = sorted(
            (
                InvoiceDelivery(
                    export_id=export.id,
                    month=export.month,
                    delivered_cents=export.total_cents,
                    in_force=current.get(export.month) is export,
                )
                for export in (
                    by_id[d.billing_export_id]
                    for d in invoice.deliveries
                    if d.billing_export_id in by_id
                )
            ),
            key=lambda delivery: delivery.month,
        )
        views.append(
            InvoiceView(
                invoice=invoice,
                deliveries=tuple(deliveries),
                recorded_by_name=names.get(invoice.recorded_by_id)
                if invoice.recorded_by_id
                else None,
                withdrawn_by_name=names.get(invoice.withdrawn_by_id)
                if invoice.withdrawn_by_id
                else None,
            )
        )
    return views


async def get_invoice(session: AsyncSession, invoice_id: UUID) -> OutgoingInvoice:
    result = await session.execute(
        select(OutgoingInvoice)
        .where(OutgoingInvoice.id == invoice_id)
        .options(selectinload(OutgoingInvoice.deliveries))
        .execution_options(populate_existing=True)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Factuur", invoice_id)
    return invoice


# -- writing ------------------------------------------------------------------


def _clean_number(invoice_number: str) -> str:
    number = (invoice_number or "").strip()
    if not number:
        raise DomainValidationError("Vul het factuurnummer in.")
    if len(number) > 100:
        raise DomainValidationError("Het factuurnummer is te lang.")
    return number


def _check_date(invoice_date: date, today: date | None) -> None:
    if invoice_date > (today or datetime.now(UTC).date()):
        raise DomainValidationError(
            "De factuurdatum ligt in de toekomst. Leg een factuur vast nadat die "
            "is verstuurd."
        )


async def _check_number_free(
    session: AsyncSession,
    assignment_id: UUID,
    number: str,
    *,
    except_id: UUID | None = None,
) -> None:
    stmt = select(OutgoingInvoice.id).where(
        OutgoingInvoice.assignment_id == assignment_id,
        func.lower(OutgoingInvoice.invoice_number) == number.lower(),
        OutgoingInvoice.withdrawn_at.is_(None),
    )
    if except_id is not None:
        stmt = stmt.where(OutgoingInvoice.id != except_id)
    if (await session.execute(stmt)).first() is not None:
        raise DomainValidationError(
            f"Factuurnummer {number} is voor deze opdracht al vastgelegd."
        )


async def _deliveries_for(
    session: AsyncSession,
    assignment_id: UUID,
    export_ids: Iterable[UUID],
    *,
    except_invoice_id: UUID | None = None,
) -> list[BillingExport]:
    """The exports an invoice may be recorded on, or a validation error."""
    wanted = list(dict.fromkeys(export_ids))
    if not wanted:
        raise DomainValidationError(
            "Kies minstens een aangeleverde maand waarvoor de factuur is verstuurd."
        )
    exports = await _exports(session, assignment_id)
    by_id = {export.id: export for export in exports}
    current = _current_exports(exports, await _closes_in_force(session, assignment_id))
    corrections = _corrections(exports, current)
    chosen = []
    for export_id in wanted:
        export = by_id.get(export_id)
        if export is None:
            raise DomainValidationError(
                "Een van de gekozen aanleveringen hoort niet bij deze opdracht."
            )
        if current.get(export.month) is not export and not any(
            export is correction for correction in corrections.get(export.month, [])
        ):
            raise DomainValidationError(
                f"De aanlevering van {Month.of(export.month)} is niet meer de "
                "geldende: de maand is heropend of opnieuw aangeleverd. Kies de "
                "geldende aanlevering."
            )
        chosen.append(export)
    taken = await session.execute(
        select(OutgoingInvoiceDelivery.billing_export_id, OutgoingInvoice.id)
        .join(
            OutgoingInvoice,
            OutgoingInvoice.id == OutgoingInvoiceDelivery.outgoing_invoice_id,
        )
        .where(OutgoingInvoiceDelivery.billing_export_id.in_(wanted))
    )
    for export_id, invoice_id in taken:
        if invoice_id != except_invoice_id:
            month = Month.of(by_id[export_id].month)
            raise DomainValidationError(
                f"Voor de aanlevering van {month} is al een factuur vastgelegd."
            )
    return chosen


def _snapshot(
    invoice: OutgoingInvoice, export_ids: Iterable[UUID]
) -> dict[str, object]:
    return {
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "amount_cents": invoice.amount_cents,
        "source": invoice.source,
        "external_ref": invoice.external_ref,
        "note": invoice.note,
        "export_ids": sorted(str(export_id) for export_id in export_ids),
    }


async def _event_payload(
    session: AsyncSession, invoice: OutgoingInvoice, exports: list[BillingExport]
) -> dict[str, object]:
    assignment = await session.get(Assignment, invoice.assignment_id)
    return {
        "invoice_id": str(invoice.id),
        "assignment_id": str(invoice.assignment_id),
        "assignment_uri": assignment.uri if assignment is not None else None,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "amount_cents": invoice.amount_cents,
        "delivered_cents": sum(export.total_cents for export in exports),
        "months": sorted(str(Month.of(export.month)) for export in exports),
        "export_ids": sorted(str(export.id) for export in exports),
        "source": invoice.source,
        "origin": "local",
    }


async def record_invoice(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    export_ids: Iterable[UUID],
    invoice_number: str,
    invoice_date: date,
    amount_cents: int,
    actor: Person | None,
    source: str = SOURCE_MANUAL,
    external_ref: str | None = None,
    note: str | None = None,
    today: date | None = None,
) -> OutgoingInvoice:
    """Record that an invoice was sent for one or several delivered months.

    The amount is what the invoice says. It is compared with what was
    delivered and a difference is shown, not refused. Emits
    ``invoice.recorded``.
    """
    await get_assignment(session, assignment_id)
    if source not in INVOICE_SOURCES:
        raise DomainValidationError(f"Onbekende bron van een factuur: {source}")
    number = _clean_number(invoice_number)
    _check_date(invoice_date, today)
    await _check_number_free(session, assignment_id, number)
    exports = await _deliveries_for(session, assignment_id, export_ids)

    invoice = OutgoingInvoice(
        assignment_id=assignment_id,
        invoice_number=number,
        invoice_date=invoice_date,
        amount_cents=amount_cents,
        source=source,
        external_ref=(external_ref or "").strip() or None,
        note=(note or "").strip() or None,
        recorded_by_id=actor.id if actor is not None else None,
    )
    session.add(invoice)
    await session.flush()
    for export in exports:
        session.add(
            OutgoingInvoiceDelivery(
                outgoing_invoice_id=invoice.id, billing_export_id=export.id
            )
        )
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="outgoing_invoice",
        entity_id=invoice.id,
        new_value={
            "assignment_id": str(assignment_id),
            **_snapshot(invoice, [export.id for export in exports]),
        },
    )
    await events.emit(
        session,
        events.INVOICE_RECORDED,
        await _event_payload(session, invoice, exports),
    )
    return await get_invoice(session, invoice.id)


async def correct_invoice(
    session: AsyncSession,
    invoice_id: UUID,
    *,
    actor: Person | None,
    invoice_number: str | None = None,
    invoice_date: date | None = None,
    amount_cents: int | None = None,
    note: str | None = None,
    export_ids: Iterable[UUID] | None = None,
    today: date | None = None,
) -> OutgoingInvoice:
    """Correct a recorded invoice. Only the given fields change.

    The old and the new values go to the audit log.
    """
    invoice = await get_invoice(session, invoice_id)
    if invoice.withdrawn_at is not None:
        raise DomainValidationError(
            "Deze factuur is ingetrokken en kan niet meer worden gewijzigd."
        )
    current_ids = [d.billing_export_id for d in invoice.deliveries]
    before = _snapshot(invoice, current_ids)

    if invoice_number is not None:
        number = _clean_number(invoice_number)
        await _check_number_free(
            session, invoice.assignment_id, number, except_id=invoice.id
        )
        invoice.invoice_number = number
    if invoice_date is not None:
        _check_date(invoice_date, today)
        invoice.invoice_date = invoice_date
    if amount_cents is not None:
        invoice.amount_cents = amount_cents
    if note is not None:
        invoice.note = note.strip() or None
    new_ids = current_ids
    if export_ids is not None:
        exports = await _deliveries_for(
            session,
            invoice.assignment_id,
            export_ids,
            except_invoice_id=invoice.id,
        )
        new_ids = [export.id for export in exports]
        for delivery in list(invoice.deliveries):
            if delivery.billing_export_id not in new_ids:
                await session.delete(delivery)
        for export_id in new_ids:
            if export_id not in current_ids:
                session.add(
                    OutgoingInvoiceDelivery(
                        outgoing_invoice_id=invoice.id, billing_export_id=export_id
                    )
                )
    await session.flush()
    after = _snapshot(invoice, new_ids)
    if after != before:
        changed = {key for key in after if after[key] != before[key]}
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="outgoing_invoice",
            entity_id=invoice.id,
            old_value={key: before[key] for key in sorted(changed)},
            new_value={key: after[key] for key in sorted(changed)},
        )
    return await get_invoice(session, invoice.id)


async def withdraw_invoice(
    session: AsyncSession,
    invoice_id: UUID,
    *,
    actor: Person | None,
    reason: str,
) -> OutgoingInvoice:
    """Take back a recorded invoice that should not have been recorded.

    The row stays, marked withdrawn with who and why. Its deliveries become
    free again, so the months go back to "aangeleverd". Emits
    ``invoice.withdrawn``.
    """
    if not reason or not reason.strip():
        raise DomainValidationError("Geef een reden voor het intrekken van de factuur.")
    invoice = await get_invoice(session, invoice_id)
    if invoice.withdrawn_at is not None:
        raise DomainValidationError("Deze factuur is al ingetrokken.")
    export_ids = [d.billing_export_id for d in invoice.deliveries]
    exports = [
        export
        for export in await _exports(session, invoice.assignment_id)
        if export.id in export_ids
    ]
    payload = await _event_payload(session, invoice, exports)
    before = _snapshot(invoice, export_ids)
    for delivery in list(invoice.deliveries):
        await session.delete(delivery)
    invoice.withdrawn_at = datetime.now(UTC)
    invoice.withdrawn_by_id = actor.id if actor is not None else None
    invoice.withdrawn_reason = reason.strip()
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="outgoing_invoice",
        entity_id=invoice.id,
        old_value={"withdrawn": False, **before},
        new_value={"withdrawn": True, "reason": invoice.withdrawn_reason},
    )
    await events.emit(
        session,
        events.INVOICE_WITHDRAWN,
        {**payload, "reason": invoice.withdrawn_reason},
    )
    return await get_invoice(session, invoice.id)
