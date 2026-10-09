"""Billing per period: terms, deliveries to the financial administration.

Months are settled one by one (see ``month_close``). A billing period, a
month or a quarter by the agreement, is delivered once all its months are
closed: a factuurverzoek as a document that is kept, to a recipient, on a
date. The invoice that results is recorded against the period.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import (
    Action,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    decide,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.assignment_support import DbSession, RequestAccess
from grip.api.routes.quotes import filtered
from grip.core import clock
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.organisation import Organisation
from grip.schema.billing import (
    BatchDeliverIn,
    BillingDeliveryOut,
    BillingOverviewOut,
    BillingPeriodOut,
    BillingTermsIn,
    BillingTermsOut,
    DeliverIn,
    NextStepOut,
    PeriodInvoiceIn,
    PeriodMonthOut,
    ReplacedMonthOut,
)
from grip.services import (
    assignment_views,
    billing_deliveries,
    billing_periods,
    month_overview,
    quote_views,
    stored_documents,
)
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.phase import allows_month_close

router = APIRouter(tags=["billing"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL


async def _visible(decider: Decider, subject: Subject, assignment_id: UUID) -> Resource:
    resource = Resource.assignment(assignment_id)
    await require(decider, subject, Action.READ, resource, A, hide_existence=True)
    return resource


def _terms_out(terms: billing_deliveries.Terms) -> BillingTermsOut:
    return BillingTermsOut(
        rhythm=terms.rhythm,
        rhythm_is_default=terms.rhythm_is_default,
        details=terms.details,
        missing_details=list(terms.missing_details),
        names_on_specification=terms.names_on_specification,
    )


def _delivery_out(view: billing_deliveries.DeliveryView) -> BillingDeliveryOut:
    return BillingDeliveryOut(
        id=view.id,
        reference=view.reference,
        period_key=view.period_key,
        total_cents=view.total_cents,
        via=view.via,
        recipient=view.recipient,
        delivered_at=view.delivered_at,
        delivered_by_name=view.delivered_by_name,
        has_document=view.has_document,
        mail_state=view.mail_state,
        invoice_id=view.invoice_id,
        invoice_number=view.invoice_number,
        in_force_cents=view.in_force_cents,
        replaced=[
            ReplacedMonthOut(
                month=str(month),
                month_label=billing_periods.month_name(month),
                delivery_id=delivery_id,
                reference=reference,
                amount_cents=amount,
            )
            for month, reference, delivery_id, amount in view.replaced
        ],
    )


def _period_out(view: billing_deliveries.PeriodView) -> BillingPeriodOut:
    return BillingPeriodOut(
        key=view.period.key,
        label=view.period.label,
        span=view.period.span,
        state=view.state,
        months=[
            PeriodMonthOut(
                month=str(m.month),
                label=billing_periods.month_name(m.month),
                state=m.state,
                closed_at=m.closed_at,
                closed_by_name=m.closed_by_name,
                amount_cents=m.amount_cents,
                delivered_cents=m.delivered_cents,
                correction_cents=m.correction_cents,
            )
            for m in view.months
        ],
        closed_cents=view.closed_cents,
        to_deliver_cents=view.to_deliver_cents,
        delivered_cents=view.delivered_cents,
        invoiced_cents=view.invoiced_cents,
        deliveries=[_delivery_out(d) for d in view.deliveries],
        invoice_numbers=list(view.invoice_numbers),
        awaits_invoice=bool(view.open_export_ids),
        last_step_at=view.last_step_at,
        correction=view.correction,
        correction_cause=view.correction_cause,
        invoiced_on=view.invoiced_on,
        invoice_difference_cents=view.invoice_difference_cents,
    )


def _next_out(
    state: billing_deliveries.Overview,
) -> NextStepOut:
    step = state.next_step
    view = next(
        (
            v
            for v in (*state.periods, *state.upcoming)
            if v.period.key == step.period_key
        ),
        None,
    )
    period = view.period if view is not None else None
    last_delivery = (
        view.deliveries[-1] if view is not None and view.deliveries else None
    )
    month = step.month or step.upcoming_month
    return NextStepOut(
        kind=step.kind,
        month=str(month) if month else None,
        month_label=billing_periods.month_name(month) if month else None,
        period_key=step.period_key,
        period_label=period.label if period else None,
        amount_cents=step.amount_cents,
        from_date=step.from_date,
        correction=step.correction,
        invoice_numbers=list(view.invoice_numbers) if view and step.correction else [],
        invoiced_on=view.invoiced_on if view and step.correction else None,
        delivered_on=clock.local_date(last_delivery.delivered_at)
        if last_delivery is not None and step.correction
        else None,
    )


async def _overview_value(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    resource: Resource,
    assignment_id: UUID,
) -> BillingOverviewOut:
    assignment = await get_assignment(db, assignment_id)
    try:
        state = await billing_deliveries.overview(db, assignment_id)
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    client = (
        await db.get(Organisation, assignment.client_organisation_id)
        if assignment.client_organisation_id
        else None
    )
    may_edit = bool(await decide(decider, subject, Action.EDIT, resource, B))
    upcoming = state.upcoming
    return BillingOverviewOut(
        assignment_id=assignment.id,
        assignment_name=assignment.name,
        client_name=client.name if client is not None else None,
        closing_started=allows_month_close(assignment.status),
        billable=state.billable,
        may_close=bool(await decide(decider, subject, Action.CLOSE_MONTH, resource)),
        may_deliver=may_edit,
        may_record_invoice=bool(
            await decide(decider, subject, Action.RECORD_INVOICE, resource)
        ),
        may_edit_terms=may_edit,
        terms=_terms_out(state.terms),
        next_step=_next_out(state),
        periods=[_period_out(view) for view in state.periods],
        upcoming_count=len(upcoming),
        upcoming_until=billing_periods.month_name(upcoming[-1].period.last)
        if upcoming
        else None,
        closed_cents=state.closed_cents,
        delivered_cents=state.delivered_cents,
        invoiced_cents=state.invoiced_cents,
        can_mail=state.can_mail,
        recipient=state.recipient or None,
    )


async def _overview(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    resource: Resource,
    assignment_id: UUID,
) -> dict[str, Any]:
    value = await _overview_value(db, decider, subject, resource, assignment_id)
    return await filtered(decider, subject, resource, value)


@router.get("/assignments/{assignment_id}/billing", response_model=None)
async def billing_overview(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The billing periods of the assignment with their months, and what is next."""
    resource = await _visible(decider, subject, assignment_id)
    return await _overview(db, decider, subject, resource, assignment_id)


@router.put("/assignments/{assignment_id}/billing/terms", response_model=None)
async def set_terms(
    assignment_id: UUID,
    body: BillingTermsIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record the billing rhythm and what the client gave for the invoice."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.EDIT, resource, B)
    await billing_deliveries.set_terms(
        db,
        assignment_id,
        actor=person,
        rhythm=body.rhythm,
        details=body.details,
        names_on_specification=body.names_on_specification,
    )
    return await _overview(db, decider, subject, resource, assignment_id)


async def _require_delivery_rights(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    resource: Resource,
    assignment_id: UUID,
) -> None:
    await require(decider, subject, Action.EDIT, resource, B)
    # A specification that names people shows their rates.
    terms = await billing_deliveries.terms_of(db, assignment_id)
    if terms.names_on_specification:
        await require(decider, subject, Action.READ, resource, DataClass.PERSON_RATE)


@router.post(
    "/assignments/{assignment_id}/billing/deliveries",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def deliver(
    assignment_id: UUID,
    body: DeliverIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Hand a billing period to the financial administration."""
    resource = await _visible(decider, subject, assignment_id)
    await _require_delivery_rights(db, decider, subject, resource, assignment_id)
    try:
        await billing_deliveries.deliver(
            db,
            assignment_id,
            body.period_key,
            via=body.via,
            actor=person,
            note=body.note,
        )
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    return await _overview(db, decider, subject, resource, assignment_id)


@router.post(
    "/assignments/{assignment_id}/billing/periods/{period_key}/invoice",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def record_period_invoice(
    assignment_id: UUID,
    period_key: str,
    body: PeriodInvoiceIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record the invoice that was sent for a delivered period."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.RECORD_INVOICE, resource)
    await billing_deliveries.record_invoice_for_period(
        db,
        assignment_id,
        period_key,
        invoice_number=body.invoice_number,
        invoice_date=body.invoice_date,
        amount_cents=body.amount_cents,
        note=body.note,
        actor=person,
    )
    return await _overview(db, decider, subject, resource, assignment_id)


async def _readable_delivery(
    db: AsyncSession, decider: Decider, subject: Subject, delivery_id: UUID
):
    delivery = await billing_deliveries.get_delivery(db, delivery_id)
    resource = await _visible(decider, subject, delivery.assignment_id)
    await require(decider, subject, Action.READ, resource, B)
    terms = await billing_deliveries.terms_of(db, delivery.assignment_id)
    if terms.names_on_specification:
        await require(decider, subject, Action.READ, resource, DataClass.PERSON_RATE)
    return delivery, resource


@router.get("/billing/deliveries/{delivery_id}", response_model=None)
async def get_delivery(
    delivery_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One delivery with what it states, for the page a mailed link opens."""
    delivery, _ = await _readable_delivery(db, decider, subject, delivery_id)
    content = await billing_deliveries.document_content(db, delivery)
    return {
        "id": str(delivery.id),
        "assignment_id": str(delivery.assignment_id),
        "reference": delivery.reference,
        "assignment_name": content["assignment_name"],
        "client_name": content["client_name"],
        "period_label": content["period_label"],
        "total_cents": delivery.total_cents,
        # What still counts once a later request delivered a month again.
        "in_force_cents": delivery.total_cents
        - sum(item["amount_cents"] for item in content["replaced_by"]),
        "replaces": content["replaces"],
        "replaced_by": content["replaced_by"],
        "corrections": content["corrections"],
        "delivered_at": delivery.delivered_at.isoformat(),
        "delivered_by_name": content["delivered_by_name"],
        "has_document": delivery.document_ref is not None,
        "document_sha256": delivery.document_sha256,
        "details": content["details"],
        "lines": content["lines"],
    }


@router.get("/billing/deliveries/{delivery_id}/document")
async def delivery_document(
    delivery_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    download: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The factuurverzoek as it was made at delivery: the kept file."""
    delivery, _ = await _readable_delivery(db, decider, subject, delivery_id)
    document_id = stored_documents.parse_document_ref(delivery.document_ref)
    if document_id is None:
        raise NotFoundError("Document van de aanlevering", delivery_id)
    document = await stored_documents.load_document(db, document_id)
    disposition = "attachment" if download else "inline"
    return Response(
        content=document.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{document.filename}"',
            "Cache-Control": "private, no-store",
            "X-Document-SHA256": document.sha256,
        },
    )


@router.get("/billing/deliveries/{delivery_id}/csv")
async def delivery_csv(
    delivery_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The lines of a delivery as a file for a system.

    One row per person's inzet, so it needs the right to read the rates of
    the people on the assignment as well.
    """
    delivery = await billing_deliveries.get_delivery(db, delivery_id)
    resource = await _visible(decider, subject, delivery.assignment_id)
    for data_class in (B, DataClass.PERSON_RATE):
        await require(decider, subject, Action.READ, resource, data_class)
    parts: list[str] = []
    for export in await billing_deliveries.exports_of_delivery(db, delivery.id):
        text = await month_overview.export_csv(db, export)
        rows = text.splitlines(keepends=True)
        parts.extend(rows if not parts else rows[1:])
    name = delivery.reference.replace("/", "-")
    return Response(
        content="".join(parts).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="factuurgegevens-{name}.csv"',
            "Cache-Control": "private, no-store",
        },
    )


# -- across assignments ---------------------------------------------------------


@router.get("/billing", response_model=None)
async def billing_across(
    access: RequestAccess, decider: AccessDecider, db: DbSession
) -> dict[str, Any]:
    """What is ready to deliver and what awaits an invoice, over all the
    assignments the reader may see the money of."""
    if await access.may(Action.READ, Resource.assignment(), A):
        rows = await assignment_views.assignment_rows(db)
    else:
        rows = await assignment_views.assignment_rows(
            db, only_ids=await access.own_assignment_ids()
        )
    classes = schema_classes(BillingOverviewOut)
    items: list[dict[str, Any]] = []
    # Whether the reader may see the money of any assignment at all: an empty
    # list for who may not is "not for you", not "everything is done".
    reads_money = False
    for row in rows:
        resource = Resource.assignment(row.assignment.id)
        permitted = await access.classes(resource, classes)
        if B not in permitted:
            continue
        reads_money = True
        try:
            value = await _overview_value(
                db, decider, access.subject, resource, row.assignment.id
            )
        except DomainValidationError:
            continue
        if not value.billable:
            continue
        items.append(build_response(value, permitted))
    mailable, _ = await billing_deliveries.can_mail(db)
    return {"assignments": items, "can_mail": mailable, "reads_money": reads_money}


@router.post("/billing/deliveries/batch", response_model=None)
async def deliver_batch(
    body: BatchDeliverIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deliver several periods at once. All or nothing: one refusal stops it."""
    if not body.items:
        raise DomainValidationError("Kies minstens een periode om aan te leveren.")
    delivered = []
    for item in body.items:
        try:
            assignment_id = UUID(item["assignment_id"])
            period_key = item["period_key"]
        except (KeyError, ValueError) as exc:
            raise DomainValidationError(
                "Een periode om aan te leveren noemt de opdracht en de periode."
            ) from exc
        resource = await _visible(decider, subject, assignment_id)
        await _require_delivery_rights(db, decider, subject, resource, assignment_id)
        try:
            delivery = await billing_deliveries.deliver(
                db, assignment_id, period_key, via=body.via, actor=person
            )
        except calc.CalcError as exc:
            raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
        delivered.append({"id": str(delivery.id), "reference": delivery.reference})
    return {"delivered": delivered}
