"""Billing per period: what goes to the financial administration, and when.

Two acts with their own rhythm (ADR 0039). Settling what was worked is done
per month, soon after the month. Billing follows the agreement: per month
or per quarter. A billing period can be delivered once all its months are
closed. A delivery is a dated fact with a recipient and a document that is
made once; the invoice that results is recorded against it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip import calc
from grip.calc import Month
from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.core.config import get_settings
from grip.integrations.mail import outbox
from grip.integrations.mail.config import is_configured as mail_is_configured
from grip.models.assignment import Assignment
from grip.models.billing_delivery import BillingDelivery, BillingTerms
from grip.models.month_close import BillingExport
from grip.models.organisation import Organisation
from grip.models.outgoing_invoice import OutgoingInvoiceDelivery
from grip.models.person import Person
from grip.models.quote import Quote
from grip.services import (
    billing_corrections,
    billing_periods,
    instance_settings,
    month_close,
    month_overview,
    outgoing_invoices,
    read_cache,
    stale,
    stored_documents,
)
from grip.services.assignments import get_assignment
from grip.services.billing_periods import MONTHLY, QUARTERLY, RHYTHMS, Period
from grip.services.errors import DomainError, DomainValidationError, NotFoundError
from grip.services.phase import allows_billing
from grip.services.stored_documents import PDF, DocumentUse

VIA_MAIL = "mail"
VIA_SELF = "self"

# Period states, in the order a period passes through them.
UPCOMING = "upcoming"
RUNNING = "running"
TO_CLOSE = "to_close"
READY = "ready"
DELIVERED = "delivered"
INVOICED = "invoiced"

DETAIL_FIELDS = (
    "organisation",
    "attention_of",
    "address",
    "postcode_city",
    "reference",
    "contact_name",
    "contact_phone",
    "contact_email",
)
# What the financial administration cannot make an invoice without.
REQUIRED_DETAILS = ("organisation", "address", "postcode_city")
DETAIL_LABELS = {
    "organisation": "de organisatie waaraan wordt gefactureerd",
    "address": "het factuuradres",
    "postcode_city": "postcode en plaats",
}

BILLING_DELIVERY_DOCUMENT = DocumentUse(
    owner_kind="billing_delivery",
    content_types=frozenset({PDF}),
    accepted_text="Het document van een aanlevering is een pdf.",
)

MAIL_KIND = "billing_delivery"


def _mail_address(value: Any) -> str:
    if not isinstance(value, str):
        raise DomainValidationError("Een e-mailadres is tekst.")
    text = value.strip()
    if text and ("@" not in text or " " in text or len(text) > 320):
        raise DomainValidationError("Dit is geen e-mailadres.")
    return text


DEFAULT_RHYTHM = instance_settings.declare(
    "billing.rhythm",
    QUARTERLY,
    instance_settings.one_of(*RHYTHMS),
    "Over welke periode een opdracht wordt gefactureerd als de afspraak niets "
    "anders zegt: per maand of per kwartaal.",
)
RECIPIENT = instance_settings.declare(
    "billing.recipient",
    "",
    _mail_address,
    "Het e-mailadres van de financiële administratie. Daarheen gaat het bericht "
    "dat er een factuurverzoek klaarstaat.",
)


class DeliveryDocumentError(DomainError):
    """The document of a delivery could not be made; nothing was delivered."""


# -- terms --------------------------------------------------------------------


@dataclass(frozen=True)
class Terms:
    rhythm: str
    # True when the assignment has no terms of its own and follows the instance.
    rhythm_is_default: bool
    details: dict[str, str]
    names_on_specification: bool
    # Of the stored terms; None while the assignment follows the instance.
    version: int | None = None

    @property
    def missing_details(self) -> tuple[str, ...]:
        return tuple(key for key in REQUIRED_DETAILS if not self.details.get(key))


def _clean_details(details: dict[str, Any] | None) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in (details or {}).items():
        if key not in DETAIL_FIELDS:
            raise DomainValidationError(f"Onbekend gegeven voor de factuur: {key}")
        if value is None:
            continue
        if not isinstance(value, str):
            raise DomainValidationError("Een gegeven voor de factuur is tekst.")
        text = " ".join(value.split())
        if len(text) > 200:
            raise DomainValidationError(
                "Een gegeven voor de factuur is hooguit 200 tekens."
            )
        if text:
            cleaned[key] = text
    if cleaned.get("contact_email"):
        _mail_address(cleaned["contact_email"])
    return cleaned


async def terms_of(session: AsyncSession, assignment_id: UUID) -> Terms:
    row = await session.get(BillingTerms, assignment_id)
    if row is None:
        return Terms(
            rhythm=await instance_settings.get(session, DEFAULT_RHYTHM.key),
            rhythm_is_default=True,
            details={},
            names_on_specification=False,
        )
    return Terms(
        rhythm=row.rhythm,
        rhythm_is_default=False,
        details={k: str(v) for k, v in (row.details or {}).items() if v},
        names_on_specification=row.names_on_specification,
        version=row.version,
    )


async def set_terms(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    actor: Person | None,
    rhythm: str | None = None,
    details: dict[str, Any] | None = None,
    names_on_specification: bool | None = None,
) -> Terms:
    """Record how the assignment is billed and where the invoice goes.

    The rhythm cannot change once a period was delivered: the periods that
    were delivered would no longer be the periods of the agreement.
    """
    await get_assignment(session, assignment_id)
    before = await terms_of(session, assignment_id)
    new_rhythm = before.rhythm if rhythm is None else rhythm
    if new_rhythm not in RHYTHMS:
        raise DomainValidationError("Factureren gaat per maand of per kwartaal.")
    if new_rhythm != before.rhythm:
        delivered = (
            await session.execute(
                select(BillingDelivery.id)
                .where(BillingDelivery.assignment_id == assignment_id)
                .limit(1)
            )
        ).first()
        if delivered is not None:
            raise DomainValidationError(
                "Voor deze opdracht is al een periode aangeleverd. Het ritme van "
                "factureren ligt daarmee vast."
            )
    new_details = before.details if details is None else _clean_details(details)
    new_names = (
        before.names_on_specification
        if names_on_specification is None
        else bool(names_on_specification)
    )
    row = await session.get(BillingTerms, assignment_id)
    if row is None:
        row = BillingTerms(assignment_id=assignment_id, rhythm=new_rhythm)
        session.add(row)
    else:
        await stale.check(
            session,
            row,
            "de afspraken over factureren",
            key=f"terms:{assignment_id}",
            trail=assignment_id,
        )
        stale.touch(row)
    row.rhythm = new_rhythm
    row.details = new_details
    row.names_on_specification = new_names
    row.updated_by_id = actor.id if actor is not None else None
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="billing_terms",
        entity_id=assignment_id,
        old_value={
            "rhythm": before.rhythm,
            "details": before.details,
            "names_on_specification": before.names_on_specification,
        },
        new_value={
            "rhythm": new_rhythm,
            "details": new_details,
            "names_on_specification": new_names,
        },
        assignment_id=assignment_id,
    )
    return await terms_of(session, assignment_id)


# -- reading ------------------------------------------------------------------


@dataclass(frozen=True)
class MonthView:
    month: Month
    # closed | to_close | running | upcoming
    state: str
    closed_at: datetime | None
    closed_by_name: str | None
    # Established and priced when closed; else what the plan gives. None
    # when it cannot be priced.
    amount_cents: int | None
    delivered_cents: int | None
    # Positive or negative: what changed after the month was delivered.
    correction_cents: int


@dataclass(frozen=True)
class DeliveryView:
    id: UUID
    reference: str
    period_key: str
    total_cents: int
    via: str
    recipient: str | None
    delivered_at: datetime
    delivered_by_name: str | None
    has_document: bool
    # queued | sent | failed, when grip mailed it.
    mail_state: str | None
    invoice_id: UUID | None
    invoice_number: str | None
    # What of this request still counts: the total without the months a
    # later request delivers again.
    in_force_cents: int = 0
    # Those months: (month, reference of the later request, its id, amount).
    replaced: tuple[tuple[Month, str, UUID, int], ...] = ()


@dataclass(frozen=True)
class PeriodView:
    period: Period
    state: str
    months: tuple[MonthView, ...]
    # Sum of the months that are closed; None when one cannot be priced.
    closed_cents: int | None
    # What a delivery made now would hold: undelivered months of the period
    # and corrections on months up to its end.
    to_deliver_cents: int | None
    delivered_cents: int
    invoiced_cents: int
    deliveries: tuple[DeliveryView, ...]
    # Deliveries in force of this period no invoice was recorded for.
    open_export_ids: tuple[UUID, ...]
    invoice_numbers: tuple[str, ...]
    last_step_at: datetime | None
    # What is to be delivered is only a naverrekening: every month of the
    # period was delivered before, and a later change (a promotion recorded
    # afterwards, a corrected month) left a difference.
    correction: bool = False
    # Why there is a difference, in words; empty without one.
    correction_cause: str = ""
    # The day of the latest invoice recorded for the period, when there is one.
    invoiced_on: date | None = None
    # Invoiced minus delivered once every delivery has its invoice; None
    # while a delivery still waits for one. Not zero: something to look at.
    invoice_difference_cents: int | None = None

    @property
    def months_to_close(self) -> tuple[Month, ...]:
        return tuple(m.month for m in self.months if m.state == "to_close")


@dataclass(frozen=True)
class NextStep:
    # close_month | deliver | record_invoice | none
    kind: str
    month: Month | None = None
    period_key: str | None = None
    amount_cents: int | None = None
    # For "none": the first day something can be done.
    from_date: date | None = None
    # For "none" with a from_date: the month that can be closed then.
    upcoming_month: Month | None = None
    # For "deliver": only a naverrekening on a period delivered before.
    correction: bool = False


@dataclass(frozen=True)
class Overview:
    assignment_id: UUID
    billable: bool
    terms: Terms
    periods: tuple[PeriodView, ...]
    next_step: NextStep
    closed_cents: int | None
    delivered_cents: int
    invoiced_cents: int
    can_mail: bool
    recipient: str
    upcoming: tuple[PeriodView, ...] = field(default_factory=tuple)


async def _names(session: AsyncSession, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(
        select(Person.id, Person.name).where(Person.id.in_(wanted))
    )
    return {row.id: row.name for row in rows}


async def _deliveries(
    session: AsyncSession, assignment_id: UUID
) -> list[BillingDelivery]:
    result = await session.execute(
        select(BillingDelivery)
        .where(BillingDelivery.assignment_id == assignment_id)
        .order_by(BillingDelivery.delivered_at, BillingDelivery.id)
    )
    return list(result.scalars())


async def can_mail(session: AsyncSession) -> tuple[bool, str]:
    recipient = await instance_settings.get(session, RECIPIENT.key)
    return bool(recipient) and mail_is_configured(), recipient


async def overview(
    session: AsyncSession, assignment_id: UUID, *, today: date | None = None
) -> Overview:
    """Where every billing period of the assignment stands, and what is next."""
    found = await overviews(session, [assignment_id], today=today)
    return found[assignment_id]


async def overviews(
    session: AsyncSession,
    assignment_ids: Iterable[UUID],
    *,
    today: date | None = None,
) -> dict[UUID, Overview]:
    """``overview`` of several assignments.

    The day counts only by its month: a month can be closed from the first
    day after it, and runs from its first day. So what was worked out holds
    until the data of the assignment changes or the month turns.
    """
    day = today or clock.today()
    ids = list(dict.fromkeys(assignment_ids))

    async def compute(missing: list[UUID]) -> dict[UUID, Overview]:
        return await _overviews(session, missing, day)

    return await read_cache.remember_many(
        session,
        "billing_overview",
        ids,
        (day.year, day.month),
        compute,
        ignore=read_cache.COST_KINDS,
    )


@dataclass
class _Read:
    """What the overview of one assignment is built from, read beforehand."""

    assignment: Assignment
    terms: Terms
    timeline: list[month_overview.MonthState]
    billing: dict[Month, Any]
    deliveries: list[BillingDelivery]
    exports: list[BillingExport]
    closes: dict[date, UUID]
    invoiced_exports: set[UUID]
    invoice_of_export: dict[UUID, Any]
    names: dict[UUID, str]
    mail_rows: dict[UUID, Any]
    planned: dict[Month, int | None]
    stored: list[Any]
    mailable: bool
    recipient: str


async def _overviews(
    session: AsyncSession, assignment_ids: list[UUID], today: date
) -> dict[UUID, Overview]:
    """The overview of each assignment, with what they share read together.

    The number of statements does not grow with the number of assignments;
    the amounts come from the same functions as for one.
    """
    ids = list(dict.fromkeys(assignment_ids))
    if not ids:
        return {}
    assignments = {
        row.id: row
        for row in await session.scalars(
            select(Assignment).where(Assignment.id.in_(ids))
        )
    }
    for assignment_id in ids:
        if assignment_id not in assignments:
            raise NotFoundError("Opdracht", assignment_id)
    default_rhythm = await instance_settings.get(session, DEFAULT_RHYTHM.key)
    terms_rows = {
        row.assignment_id: row
        for row in await session.scalars(
            select(BillingTerms).where(BillingTerms.assignment_id.in_(ids))
        )
    }
    timelines = await month_overview.timelines(
        session, [assignments[i] for i in ids], today=today
    )
    billings = await outgoing_invoices.month_billings(session, ids)
    deliveries_of: dict[UUID, list[BillingDelivery]] = {i: [] for i in ids}
    for delivery in await session.scalars(
        select(BillingDelivery)
        .where(BillingDelivery.assignment_id.in_(ids))
        .order_by(BillingDelivery.delivered_at, BillingDelivery.id)
    ):
        deliveries_of[delivery.assignment_id].append(delivery)
    exports_of = await outgoing_invoices._exports_of(session, ids)
    closes_of = await outgoing_invoices._closes_in_force_of(session, ids)
    invoiced_exports = {
        row[0]
        for row in await session.execute(
            select(OutgoingInvoiceDelivery.billing_export_id)
            .join(
                BillingExport,
                BillingExport.id == OutgoingInvoiceDelivery.billing_export_id,
            )
            .where(BillingExport.assignment_id.in_(ids))
        )
    }
    invoices_of = await outgoing_invoices._invoices_in_force_of(session, ids)
    names = await _names(
        session,
        [d.delivered_by_id for rows in deliveries_of.values() for d in rows],
    )
    mail_rows = await outbox.latest_for(
        session,
        "billing_delivery",
        {d.id for rows in deliveries_of.values() for d in rows},
    )
    # The planned amount of the months that are not closed yet and have begun.
    wanted_months = {
        assignment_id: [
            state.month
            for state in timelines[assignment_id]
            if not state.closed and state.month.first_day <= today
        ]
        for assignment_id in ids
    }
    with_open = [i for i in ids if wanted_months[i]]
    inputs_of = (
        await outgoing_invoices._inputs_of(
            session, with_open, outgoing_invoices.DEFAULT_OPTIONS
        )
        if with_open
        else {}
    )
    stored_of = await billing_corrections.open_corrections(session, ids)
    mailable, recipient = await can_mail(session)

    found: dict[UUID, Overview] = {}
    for assignment_id in ids:
        row = terms_rows.get(assignment_id)
        terms = (
            Terms(
                rhythm=default_rhythm,
                rhythm_is_default=True,
                details={},
                names_on_specification=False,
            )
            if row is None
            else Terms(
                rhythm=row.rhythm,
                rhythm_is_default=False,
                details={k: str(v) for k, v in (row.details or {}).items() if v},
                names_on_specification=row.names_on_specification,
                version=row.version,
            )
        )
        exports = exports_of[assignment_id]
        own_exports = {export.id for export in exports}
        invoice_of_export: dict[UUID, Any] = {}
        # Newest invoice date first, as the list of invoices reads them.
        for invoice in reversed(invoices_of[assignment_id]):
            for link in invoice.deliveries:
                if link.billing_export_id in own_exports:
                    invoice_of_export[link.billing_export_id] = invoice
        planned: dict[Month, int | None] = {}
        inputs = inputs_of.get(assignment_id)
        for month in wanted_months[assignment_id]:
            if inputs is None:
                planned[month] = None
                continue
            try:
                lines = month_close._lines(
                    inputs, month, outgoing_invoices.DEFAULT_OPTIONS, None
                )
            except calc.CalcError:
                planned[month] = None
                continue
            planned[month] = sum(line.amount_cents for line in lines)
        found[assignment_id] = _overview(
            _Read(
                assignment=assignments[assignment_id],
                terms=terms,
                timeline=timelines[assignment_id],
                billing={Month.of(m.month): m for m in billings[assignment_id]},
                deliveries=deliveries_of[assignment_id],
                exports=exports,
                closes=closes_of[assignment_id],
                invoiced_exports=invoiced_exports,
                invoice_of_export=invoice_of_export,
                names=names,
                mail_rows=mail_rows,
                planned=planned,
                stored=stored_of.get(assignment_id, []),
                mailable=mailable,
                recipient=recipient,
            ),
            today,
        )
    return found


def _overview(read: _Read, today: date) -> Overview:
    assignment_id = read.assignment.id
    terms = read.terms
    billable = allows_billing(read.assignment.status)
    timeline = read.timeline
    billing = read.billing
    deliveries = read.deliveries
    exports = read.exports
    closes = read.closes
    current = outgoing_invoices._current_exports(exports, closes)
    corrections = outgoing_invoices._corrections(exports, current)
    invoiced_exports = read.invoiced_exports
    invoice_of_export = read.invoice_of_export
    names = read.names
    mail_rows = read.mail_rows

    replaced_of: dict[UUID, list[Replacement]] = {}
    for replacement in replacements(exports, closes):
        replaced_of.setdefault(replacement.old_delivery_id, []).append(replacement)
    reference_of = {d.id: d.reference for d in deliveries}

    planned = read.planned

    periods = billing_periods.periods_of(
        [state.month for state in timeline], terms.rhythm
    )
    stored = read.stored
    stored_cents = billing_corrections.month_cents(stored)
    causes_of = {row.period_key: billing_corrections.causes_text(row) for row in stored}
    by_month = {state.month: state for state in timeline}
    views: list[PeriodView] = []
    for period in periods:
        months: list[MonthView] = []
        for month in period.months:
            state = by_month[month]
            bill = billing.get(month)
            if state.closed:
                kind = "closed"
                amount = bill.deliverable_cents if bill else None
            elif state.closable:
                kind, amount = "to_close", planned.get(month)
            elif month.first_day <= today:
                kind, amount = "running", planned.get(month)
            else:
                kind, amount = "upcoming", None
            delivered = bill.delivered_cents if bill and state.closed else None
            # The stored correction, written when the price changed: not
            # worked out again here.
            correction = (
                stored_cents.get(month, 0)
                if state.closed and delivered is not None
                else 0
            )
            months.append(
                MonthView(
                    month=month,
                    state=kind,
                    closed_at=state.closed_at,
                    closed_by_name=state.closed_by_name,
                    amount_cents=amount,
                    delivered_cents=delivered,
                    correction_cents=correction,
                )
            )
        closed = [m for m in months if m.state == "closed"]
        priced = all(m.amount_cents is not None for m in closed)
        closed_cents = sum(m.amount_cents or 0 for m in closed) if priced else None
        delivered_cents = sum(m.delivered_cents or 0 for m in closed)
        period_exports: list[BillingExport] = []
        for month in period.months:
            original = current.get(month.first_day)
            if original is not None:
                period_exports.append(original)
                period_exports.extend(corrections.get(month.first_day, []))
        open_exports = tuple(
            e.id for e in period_exports if e.id not in invoiced_exports
        )
        # Also the invoice on a request that was replaced since: it was
        # sent, and what it billed still counts in "gefactureerd".
        first_days = {month.first_day for month in period.months}
        period_invoices = {
            invoice_of_export[e.id].id: invoice_of_export[e.id]
            for e in exports
            if e.month in first_days and e.id in invoice_of_export
        }
        numbers = tuple(
            invoice.invoice_number
            for invoice in sorted(
                period_invoices.values(),
                key=lambda invoice: (invoice.invoice_date, invoice.invoice_number),
            )
        )
        invoiced_cents = sum(
            (billing[m.month].invoiced_cents or 0) for m in closed if m.month in billing
        )
        all_closed = len(closed) == len(months)
        undelivered = [m for m in closed if m.delivered_cents is None]
        pending = sum(
            m.correction_cents for m in closed if m.delivered_cents is not None
        )
        if all(m.state == "upcoming" for m in months):
            state_name = UPCOMING
        elif not all_closed:
            state_name = (
                TO_CLOSE
                if all(m.state in ("closed", "to_close") for m in months)
                else RUNNING
            )
        elif undelivered or pending:
            state_name = READY
        elif open_exports:
            state_name = DELIVERED
        else:
            state_name = INVOICED
        to_deliver: int | None = None
        if all_closed and priced:
            to_deliver = sum(m.amount_cents or 0 for m in undelivered) + pending
        period_deliveries = [d for d in deliveries if d.period_key == period.key]
        delivery_views = []
        for delivery in period_deliveries:
            linked = [e for e in exports if e.delivery_id == delivery.id]
            invoice = next(
                (invoice_of_export[e.id] for e in linked if e.id in invoice_of_export),
                None,
            )
            mail = mail_rows.get(delivery.id)
            delivery_views.append(
                DeliveryView(
                    id=delivery.id,
                    reference=delivery.reference,
                    period_key=delivery.period_key,
                    total_cents=delivery.total_cents,
                    via=delivery.via,
                    recipient=delivery.recipient,
                    delivered_at=delivery.delivered_at,
                    delivered_by_name=names.get(delivery.delivered_by_id)
                    if delivery.delivered_by_id
                    else None,
                    has_document=delivery.document_ref is not None,
                    mail_state=_mail_state(mail.status) if mail is not None else None,
                    invoice_id=invoice.id if invoice is not None else None,
                    invoice_number=invoice.invoice_number
                    if invoice is not None
                    else None,
                    in_force_cents=delivery.total_cents
                    - sum(r.old_cents for r in replaced_of.get(delivery.id, [])),
                    replaced=tuple(
                        (
                            Month.of(r.month),
                            reference_of.get(r.new_delivery_id, ""),
                            r.new_delivery_id,
                            r.old_cents,
                        )
                        for r in replaced_of.get(delivery.id, [])
                    ),
                )
            )
        steps = [m.closed_at for m in closed if m.closed_at is not None]
        steps += [e.created_at for e in period_exports]
        invoice_days = [
            invoice_of_export[e.id].invoice_date
            for e in period_exports
            if e.id in invoice_of_export
        ]
        views.append(
            PeriodView(
                period=period,
                state=state_name,
                months=tuple(months),
                closed_cents=closed_cents,
                to_deliver_cents=to_deliver,
                delivered_cents=delivered_cents,
                invoiced_cents=invoiced_cents,
                deliveries=tuple(delivery_views),
                open_export_ids=open_exports,
                invoice_numbers=numbers,
                last_step_at=max(steps) if steps else None,
                correction=state_name == READY and not undelivered and pending != 0,
                correction_cause=causes_of.get(period.key, ""),
                invoiced_on=max(invoice_days) if invoice_days else None,
                invoice_difference_cents=(invoiced_cents - delivered_cents)
                if state_name == INVOICED and period_exports
                else None,
            )
        )

    shown = tuple(v for v in views if v.state != UPCOMING)
    upcoming = tuple(v for v in views if v.state == UPCOMING)
    all_priced = all(v.closed_cents is not None for v in shown)
    mailable, recipient = read.mailable, read.recipient
    return Overview(
        assignment_id=assignment_id,
        billable=billable,
        terms=terms,
        periods=shown,
        upcoming=upcoming,
        next_step=_next_step(views, billable=billable, today=today),
        closed_cents=sum(v.closed_cents or 0 for v in shown) if all_priced else None,
        delivered_cents=sum(v.delivered_cents for v in shown),
        invoiced_cents=sum(v.invoiced_cents for v in shown),
        can_mail=mailable,
        recipient=recipient,
    )


def _mail_state(status: str) -> str:
    return {"queued": "queued", "sent": "sent"}.get(status, "failed")


def _next_step(views: list[PeriodView], *, billable: bool, today: date) -> NextStep:
    """The one thing to do now: the oldest open step first.

    A naverrekening on a period that was delivered before comes after the
    work of the periods themselves: the head of the assignment follows the
    tasks, which do not know a correction yet, and the two must name the
    same step."""
    for view in views:
        for month in view.months:
            if month.state == "to_close":
                return NextStep(
                    "close_month", month=month.month, amount_cents=month.amount_cents
                )
        if billable and view.state == READY and not view.correction:
            return NextStep(
                "deliver",
                period_key=view.period.key,
                amount_cents=view.to_deliver_cents,
            )
    if billable:
        for view in views:
            if view.state == DELIVERED:
                return NextStep(
                    "record_invoice",
                    period_key=view.period.key,
                    amount_cents=view.delivered_cents - view.invoiced_cents,
                )
        for view in views:
            if view.state == READY and view.correction:
                return NextStep(
                    "deliver",
                    period_key=view.period.key,
                    amount_cents=view.to_deliver_cents,
                    correction=True,
                )
    for view in views:
        for month in view.months:
            if month.state == "running":
                return NextStep(
                    "none",
                    from_date=month.month.next().first_day,
                    upcoming_month=month.month,
                )
    for view in views:
        if view.state == UPCOMING:
            first = view.period.first
            return NextStep(
                "none", from_date=first.next().first_day, upcoming_month=first
            )
    return NextStep("none")


async def get_delivery(session: AsyncSession, delivery_id: UUID) -> BillingDelivery:
    delivery = await session.get(BillingDelivery, delivery_id)
    if delivery is None:
        raise NotFoundError("Aanlevering", delivery_id)
    return delivery


async def exports_of_delivery(
    session: AsyncSession, delivery_id: UUID
) -> list[BillingExport]:
    result = await session.execute(
        select(BillingExport)
        .where(BillingExport.delivery_id == delivery_id)
        .order_by(BillingExport.month, BillingExport.created_at)
        .options(selectinload(BillingExport.lines))
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


# -- delivering ---------------------------------------------------------------


async def _reference(
    session: AsyncSession, assignment_id: UUID, period: Period
) -> tuple[str, Quote | None]:
    quote = (
        await session.execute(
            select(Quote)
            .where(Quote.assignment_id == assignment_id, Quote.status == "accepted")
            .order_by(Quote.issued_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    earlier = len(
        [
            d
            for d in await _deliveries(session, assignment_id)
            if d.period_key == period.key
        ]
    )
    stem = quote.reference if quote is not None and quote.reference else "AL"
    reference = f"{stem}/{period.key}"
    if earlier:
        reference += f"-{earlier + 1}"
    return reference, quote


def specification(
    exports: list[BillingExport],
    *,
    with_names: bool,
    names: dict[UUID, str],
) -> list[dict[str, Any]]:
    """The lines of a delivery as the document and the file show them.

    Without names a line is a role in a month at a rate, as the quote names
    it; people who share role and rate in a month are added up. With names
    there is a line per person.
    """
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for export in exports:
        month = Month.of(export.month)
        for line in sorted(export.lines, key=lambda e: (e.description, str(e.id))):
            person = names.get(line.person_id, "") if with_names else ""
            key = (
                month,
                export.kind,
                line.description,
                line.monthly_rate_cents,
                line.person_id if with_names else None,
            )
            row = rows.setdefault(
                key,
                {
                    "month": str(month),
                    "month_label": billing_periods.month_name(month),
                    "correction": export.kind == "correction",
                    "description": line.description,
                    "person_name": person,
                    "fte_pct": 0,
                    "monthly_rate_cents": line.monthly_rate_cents,
                    "amount_cents": 0,
                },
            )
            row["fte_pct"] += line.fte_pct
            row["amount_cents"] += line.amount_cents
    ordered = sorted(
        rows.values(),
        key=lambda r: (r["month"], r["correction"], r["description"], r["person_name"]),
    )
    for row in ordered:
        # Plain digits: a normalised decimal would print 200 as "2E+2".
        text = format(row["fte_pct"], "f")
        row["fte_pct"] = text.rstrip("0").rstrip(".") if "." in text else text
    return ordered


@dataclass(frozen=True)
class Replacement:
    """What one request stated for a month that a later request delivers again."""

    month: date
    # The request that no longer counts for this month, and what it stated
    # for it: the month in full, or a naverrekening on top of it.
    old_delivery_id: UUID
    old_cents: int
    # The request that delivers the month again, and what it states.
    new_delivery_id: UUID
    new_cents: int
    # The new amount minus everything stated for the month before.
    difference_cents: int


def replacements(
    exports: Iterable[BillingExport], closes: dict[date, UUID] | None = None
) -> list[Replacement]:
    """Which request replaces which, per month. Pure.

    A month that is reopened after it was delivered and closed again is
    delivered anew, in full. The earlier request still lists the month, so
    without this the financial administration would bill the month twice.
    Every close of a month has its own delivery in full, with the
    corrections (naverrekening) made on top of it; the next close that is
    delivered replaces all of that, in whichever requests it went out.

    ``closes`` names the close in force per month. It only settles the order
    when two deliveries carry the same moment.
    """
    in_force = closes or {}
    by_month: dict[date, dict[UUID, list[BillingExport]]] = {}
    for export in exports:
        if export.delivery_id is not None:
            by_month.setdefault(export.month, {}).setdefault(
                export.month_close_id, []
            ).append(export)
    found: list[Replacement] = []
    for month, by_close in sorted(by_month.items()):
        delivered = [
            (close_id, rows)
            for close_id, rows in by_close.items()
            if any(e.kind != "correction" for e in rows)
        ]
        delivered.sort(
            key=lambda item: (
                min(e.created_at for e in item[1] if e.kind != "correction"),
                item[0] == in_force.get(month),
            )
        )
        for (_, older), (_, newer) in zip(delivered, delivered[1:], strict=False):
            full = next(e for e in newer if e.kind != "correction")
            before = sum(e.total_cents for e in older)
            per_delivery: dict[UUID, int] = {}
            for export in older:
                per_delivery[export.delivery_id] = (
                    per_delivery.get(export.delivery_id, 0) + export.total_cents
                )
            found.extend(
                Replacement(
                    month=month,
                    old_delivery_id=delivery_id,
                    old_cents=cents,
                    new_delivery_id=full.delivery_id,
                    new_cents=full.total_cents,
                    difference_cents=full.total_cents - before,
                )
                for delivery_id, cents in per_delivery.items()
            )
    return found


async def _all_replacements(
    session: AsyncSession, assignment_id: UUID
) -> list[Replacement]:
    exports = await outgoing_invoices._exports(session, assignment_id)
    closes = await outgoing_invoices._closes_in_force(session, assignment_id)
    return replacements(exports, closes)


async def _replaced(
    session: AsyncSession, delivery: BillingDelivery
) -> list[dict[str, Any]]:
    """The months this delivery delivers again, with the request it replaces.

    One entry per month; a month that went out in two requests (in full and
    as a naverrekening) names both.
    """
    found = await _all_replacements(session, delivery.assignment_id)
    mine = [r for r in found if r.new_delivery_id == delivery.id]
    references = await _references(session, [r.old_delivery_id for r in mine])
    by_month: dict[date, list[Replacement]] = {}
    for replacement in mine:
        by_month.setdefault(replacement.month, []).append(replacement)
    return [
        {
            "month_label": billing_periods.month_name(Month.of(month)),
            "reference": " en ".join(
                sorted(references[r.old_delivery_id] for r in rows)
            ),
            "amount_cents": sum(r.old_cents for r in rows),
            "difference_cents": rows[0].difference_cents,
        }
        for month, rows in sorted(by_month.items())
    ]


async def _replaced_by(
    session: AsyncSession, delivery: BillingDelivery
) -> list[dict[str, Any]]:
    """The months of this delivery that a later request delivers again."""
    found = await _all_replacements(session, delivery.assignment_id)
    mine = [r for r in found if r.old_delivery_id == delivery.id]
    references = await _references(session, [r.new_delivery_id for r in mine])
    return [
        {
            "month_label": billing_periods.month_name(Month.of(r.month)),
            "delivery_id": str(r.new_delivery_id),
            "reference": references[r.new_delivery_id],
            "amount_cents": r.old_cents,
        }
        for r in mine
    ]


async def _corrections_stated(
    session: AsyncSession, delivery: BillingDelivery
) -> list[dict[str, Any]]:
    """The differences this delivery carries: per month the amount, why, and
    the request it comes on top of.

    Read from the stored corrections that went along with this delivery. The
    cause is in the words it was stored in; those name a rate card or a date,
    never a person, so they go on the document whatever the agreement says
    about names.
    """
    rows = [
        row
        for row in (
            await billing_corrections.all_corrections(session, [delivery.assignment_id])
        ).get(delivery.assignment_id, [])
        if row.delivered_delivery_id == delivery.id
    ]
    follows_ids = {row.follows_delivery_id for row in rows if row.follows_delivery_id}
    follows: dict[UUID, BillingDelivery] = {}
    if follows_ids:
        found = await session.scalars(
            select(BillingDelivery).where(BillingDelivery.id.in_(follows_ids))
        )
        follows = {earlier.id: earlier for earlier in found}
    stated: list[dict[str, Any]] = []
    for row in rows:
        earlier = (
            follows.get(row.follows_delivery_id) if row.follows_delivery_id else None
        )
        cause = billing_corrections.causes_text(row)
        for month, cents in sorted(billing_corrections.month_cents([row]).items()):
            stated.append(
                {
                    "month": str(month),
                    "month_label": billing_periods.month_name(month),
                    "amount_cents": cents,
                    "cause": cause,
                    "follows_reference": earlier.reference if earlier else None,
                    "follows_delivered_on": clock.local_date(
                        earlier.delivered_at
                    ).isoformat()
                    if earlier
                    else None,
                }
            )
    stated.sort(key=lambda item: item["month"])
    return stated


async def _references(session: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, str]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(BillingDelivery.id, BillingDelivery.reference).where(
            BillingDelivery.id.in_(wanted)
        )
    )
    return {row[0]: row[1] for row in rows}


async def document_content(
    session: AsyncSession, delivery: BillingDelivery
) -> dict[str, Any]:
    """Everything the document of a delivery states, as plain values."""
    assignment = await get_assignment(session, delivery.assignment_id)
    terms = await terms_of(session, assignment.id)
    exports = await exports_of_delivery(session, delivery.id)
    people = await _names(
        session, [line.person_id for export in exports for line in export.lines]
    )
    client = (
        await session.get(Organisation, assignment.client_organisation_id)
        if assignment.client_organisation_id
        else None
    )
    quote = (
        await session.execute(
            select(Quote)
            .where(Quote.assignment_id == assignment.id, Quote.status == "accepted")
            .order_by(Quote.issued_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    deliverer = await _names(session, [delivery.delivered_by_id])
    from grip.services import quotes

    months = sorted({Month.of(e.month) for e in exports if e.kind != "correction"})
    # Only differences: the months they are about, in words like any other.
    months = months or sorted({Month.of(e.month) for e in exports})
    period_label = (
        f"{billing_periods.month_name(months[0])}"
        if len(months) == 1
        else (
            f"{billing_periods.month_name(months[0])} t/m "
            f"{billing_periods.month_name(months[-1])}"
            if months
            else delivery.period_key
        )
    )
    return {
        "reference": delivery.reference,
        "replaces": await _replaced(session, delivery),
        "replaced_by": await _replaced_by(session, delivery),
        "corrections": await _corrections_stated(session, delivery),
        "sender": await quotes.sender_name(session, assignment),
        "assignment_name": assignment.name,
        "assignment_uri": assignment.uri,
        "client_name": client.name if client is not None else None,
        "quote_reference": quote.reference if quote is not None else None,
        "client_reference": (quote.snapshot or {}).get("client_reference")
        if quote is not None
        else None,
        "period_key": delivery.period_key,
        "period_label": period_label,
        "rhythm": delivery.rhythm,
        "delivered_at": delivery.delivered_at.isoformat(),
        "delivered_by_name": deliverer.get(delivery.delivered_by_id)
        if delivery.delivered_by_id
        else None,
        "details": terms.details,
        "with_names": terms.names_on_specification,
        "lines": specification(
            exports, with_names=terms.names_on_specification, names=people
        ),
        "total_cents": delivery.total_cents,
    }


async def deliver(
    session: AsyncSession,
    assignment_id: UUID,
    period_key: str,
    *,
    via: str,
    actor: Person | None,
    note: str | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> BillingDelivery:
    """Hand a billing period to the financial administration.

    Freezes the billing data of the months of the period that were not
    delivered yet, takes along what changed since on months already
    delivered (a naverrekening), makes the document once, and records to
    whom it went and how.
    """
    if via not in (VIA_MAIL, VIA_SELF):
        raise DomainValidationError(
            "Kies hoe je aanlevert: per mail, of je geeft het zelf door."
        )
    await month_close.ensure_billable(session, assignment_id)
    state = await overview(session, assignment_id, today=today)
    view = next((v for v in state.periods if v.period.key == period_key), None)
    if view is None:
        raise DomainValidationError(
            f"De periode {period_key} hoort niet bij deze opdracht, of is nog "
            "niet begonnen."
        )
    if view.months_to_close or view.state in (RUNNING, TO_CLOSE):
        open_months = [
            billing_periods.month_name(m.month)
            for m in view.months
            if m.state != "closed"
        ]
        raise DomainValidationError(
            f"Het {view.period.label} kan nog niet worden aangeleverd: "
            f"{_join(open_months)} is nog niet afgesloten."
            if view.period.rhythm == QUARTERLY
            else f"{view.period.label.capitalize()} is nog niet afgesloten."
        )
    if view.state != READY:
        raise DomainValidationError(
            f"Voor {view.period.span} is er niets meer aan te leveren."
        )
    if state.terms.missing_details:
        missing = _join([DETAIL_LABELS[key] for key in state.terms.missing_details])
        verb = "ontbreekt" if len(state.terms.missing_details) == 1 else "ontbreken"
        raise DomainValidationError(
            "De financiële administratie kan hier geen factuur van maken: "
            f"{missing} {verb}. Vul de factuurgegevens van de opdrachtgever in."
        )
    mailable, recipient = await can_mail(session)
    if via == VIA_MAIL and not mailable:
        raise DomainValidationError(
            "Mailen aan de financiële administratie kan hier niet: er is geen "
            "adres ingesteld of deze omgeving verstuurt geen mail."
        )
    # Persist the terms the delivery was made under.
    if state.terms.rhythm_is_default:
        await set_terms(session, assignment_id, actor=actor, rhythm=state.terms.rhythm)

    created: list[BillingExport] = []
    for month in view.months:
        if month.delivered_cents is None:
            created.append(
                await month_close.create_billing_export(
                    session, assignment_id, month.month, actor=actor
                )
            )
    # What changed on months already delivered travels with this delivery.
    corrected: list[Month] = []
    for earlier in state.periods:
        if earlier.period.last > view.period.last:
            continue
        for month in earlier.months:
            if month.delivered_cents is not None and month.correction_cents != 0:
                corrected.append(month.month)
                created.append(
                    await month_close.create_correction_export(
                        session, assignment_id, month.month, actor=actor
                    )
                )
    if not created:
        raise DomainValidationError(
            f"Voor {view.period.span} is er niets meer aan te leveren."
        )
    reference, _ = await _reference(session, assignment_id, view.period)
    delivery = BillingDelivery(
        assignment_id=assignment_id,
        period_key=view.period.key,
        period_start=view.period.start,
        period_end=view.period.end,
        rhythm=view.period.rhythm,
        reference=reference,
        total_cents=sum(export.total_cents for export in created),
        via=via,
        recipient=recipient if via == VIA_MAIL else None,
        note=(note or "").strip() or None,
        delivered_by_id=actor.id if actor is not None else None,
        delivered_at=now or datetime.now(UTC),
    )
    session.add(delivery)
    await session.flush()
    for export in created:
        export.delivery_id = delivery.id
    await session.flush()
    await billing_corrections.mark_delivered(
        session, assignment_id, corrected, delivery, actor=actor
    )

    await _fix_document(session, delivery)
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="billing_delivery",
        entity_id=delivery.id,
        new_value={
            "assignment_id": str(assignment_id),
            "period": delivery.period_key,
            "reference": delivery.reference,
            "total_cents": delivery.total_cents,
            "via": via,
            "recipient": delivery.recipient,
            "document_sha256": delivery.document_sha256,
            "export_ids": sorted(str(export.id) for export in created),
        },
        assignment_id=assignment_id,
    )
    if via == VIA_MAIL:
        await _queue_mail(session, delivery, actor=actor)
    return delivery


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " en " + parts[-1]


async def _fix_document(session: AsyncSession, delivery: BillingDelivery) -> None:
    import asyncio

    from grip.services import billing_document

    content = await document_content(session, delivery)
    try:
        pdf = await asyncio.to_thread(billing_document.render_pdf, content)
    except DomainError:
        raise
    except Exception as exc:
        raise DeliveryDocumentError(
            "Het factuurverzoek kon niet worden opgemaakt. Er is niets aangeleverd."
        ) from exc
    document = await stored_documents.store_document(
        session,
        use=BILLING_DELIVERY_DOCUMENT,
        content=pdf,
        filename=f"factuurverzoek-{delivery.reference.replace('/', '-')}.pdf",
        content_type=PDF,
        actor=None,
        owner_id=delivery.id,
        uploaded=False,
    )
    delivery.document_ref = stored_documents.document_ref(document.id)
    delivery.document_sha256 = document.sha256
    await session.flush()


def delivery_link(delivery_id: UUID) -> str:
    return f"{get_settings().FRONTEND_URL.rstrip('/')}/factureren/{delivery_id}"


async def _queue_mail(
    session: AsyncSession, delivery: BillingDelivery, *, actor: Person | None
) -> None:
    assert delivery.recipient
    content = await document_content(session, delivery)
    link = delivery_link(delivery.id)
    amount = _euro(delivery.total_cents)
    client = content["client_name"] or "de opdrachtgever"
    lines = [
        "Beste collega,",
        "",
        f"Er staat een factuurverzoek klaar: {delivery.reference}.",
        "",
        f"Opdracht: {content['assignment_name']}",
        f"Opdrachtgever: {client}",
        f"Periode: {content['period_label']}",
        f"Bedrag: {amount}",
        "",
        "Het factuurverzoek met de specificatie en het factuuradres staat in grip. "
        "Je opent het na inloggen:",
        link,
        "",
        "In deze mail staan geen bijlagen. Mail is geen vertrouwelijk kanaal.",
    ]
    if content["delivered_by_name"]:
        lines += ["", f"Aangeleverd door {content['delivered_by_name']}."]
    row = await outbox.enqueue(
        session,
        kind=MAIL_KIND,
        dedupe_key=f"{MAIL_KIND}:{delivery.id}",
        subject_kind="billing_delivery",
        subject_id=delivery.id,
        recipient=delivery.recipient,
        content=outbox.Content(
            subject=(
                f"Factuurverzoek {delivery.reference}: {content['assignment_name']}"
            ),
            text="\n".join(lines),
        ),
        sender_name=content["sender"],
        reply_to=actor.email if actor is not None and actor.email else None,
        assignment_id=delivery.assignment_id,
        created_by_id=actor.id if actor is not None else None,
    )
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="mail_outbox",
        entity_id=row.id,
        new_value={
            "kind": MAIL_KIND,
            "recipient": delivery.recipient,
            "delivery_id": str(delivery.id),
        },
        assignment_id=delivery.assignment_id,
    )


def _euro(cents: int) -> str:
    from grip.services.quote_document import format_euro

    return format_euro(cents)


async def record_invoice_for_period(
    session: AsyncSession,
    assignment_id: UUID,
    period_key: str,
    *,
    invoice_number: str,
    invoice_date: date,
    amount_cents: int,
    note: str | None,
    actor: Person | None,
    today: date | None = None,
) -> None:
    """Record the invoice the administration sent for a delivered period."""
    state = await overview(session, assignment_id, today=today)
    view = next((v for v in state.periods if v.period.key == period_key), None)
    if view is None or not view.open_export_ids:
        raise DomainValidationError(
            "Voor deze periode is er geen aanlevering waarvoor nog een factuur "
            "moet worden vastgelegd."
        )
    await outgoing_invoices.record_invoice(
        session,
        assignment_id,
        export_ids=view.open_export_ids,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        amount_cents=amount_cents,
        note=note,
        actor=actor,
        today=today,
    )


# -- across assignments ---------------------------------------------------------


@dataclass(frozen=True)
class AssignmentBilling:
    assignment: Assignment
    client_name: str | None
    overview: Overview


async def across(
    session: AsyncSession,
    assignment_ids: Iterable[UUID],
    *,
    today: date | None = None,
) -> list[AssignmentBilling]:
    """The billing state of several assignments, for the page over all of them."""
    result = []
    ids = list(dict.fromkeys(assignment_ids))
    billable = [
        assignment_id
        for assignment_id in ids
        if allows_billing((await get_assignment(session, assignment_id)).status)
    ]
    states = await overviews(session, billable, today=today)
    for assignment_id in billable:
        assignment = await get_assignment(session, assignment_id)
        state = states[assignment_id]
        client = (
            await session.get(Organisation, assignment.client_organisation_id)
            if assignment.client_organisation_id
            else None
        )
        result.append(
            AssignmentBilling(
                assignment=assignment,
                client_name=client.name if client is not None else None,
                overview=state,
            )
        )
    result.sort(key=lambda entry: entry.assignment.name.lower())
    return result


__all__ = [
    "MONTHLY",
    "QUARTERLY",
    "AssignmentBilling",
    "DeliveryView",
    "MonthView",
    "NextStep",
    "Overview",
    "PeriodView",
    "Terms",
]
