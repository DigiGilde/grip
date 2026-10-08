"""Billing data of a closed month, its delivery, and recorded invoices.

Grip makes no invoices. It produces the data an invoice or an internal
settlement is made from: per closed month the established inzet priced at
the rate card, frozen as an export run and downloadable as CSV. That is a
delivery ("aangeleverd"). Whether an invoice was actually sent is a fact
someone records here ("gefactureerd"); until then nothing counts as invoiced.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import Action, DataClass, Decider, Resource, Subject, decide
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.routes.quotes import filtered
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.assignment import Allocation, BudgetLine
from grip.models.month_close import BillingExport
from grip.models.person import Person
from grip.schema.billing import (
    BillingDataOut,
    BillingExportLineOut,
    BillingExportListOut,
    BillingExportOut,
    BillingLineOut,
    BillingStatusOut,
    CorrectInvoiceIn,
    InvoiceProposalOut,
    MonthBillingOut,
    OutgoingInvoiceOut,
    RecordInvoiceIn,
    WithdrawInvoiceIn,
)
from grip.services import (
    month_close,
    month_overview,
    outgoing_invoices,
    quote_views,
)
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError

router = APIRouter(tags=["billing"])


async def _visible(decider: Decider, subject: Subject, assignment_id: UUID) -> Resource:
    resource = Resource.assignment(assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    return resource


async def _person_names(db: AsyncSession, person_ids: set[UUID]) -> dict[UUID, str]:
    if not person_ids:
        return {}
    result = await db.execute(
        select(Person.id, Person.name).where(Person.id.in_(person_ids))
    )
    return {row.id: row.name for row in result}


async def _export_out(
    db: AsyncSession, export: BillingExport, exported_by_name: str | None
) -> BillingExportOut:
    names = await _person_names(db, {line.person_id for line in export.lines})
    return BillingExportOut(
        id=export.id,
        assignment_id=export.assignment_id,
        month=str(calc.Month.of(export.month)),
        created_at=export.created_at,
        exported_by_name=exported_by_name,
        total_cents=export.total_cents,
        lines=[
            BillingExportLineOut(
                description=line.description,
                person_name=names.get(line.person_id, ""),
                fte_pct=line.fte_pct,
                category=line.category,
                monthly_rate_cents=line.monthly_rate_cents,
                amount_cents=line.amount_cents,
            )
            for line in sorted(
                export.lines, key=lambda entry: (entry.description, str(entry.id))
            )
        ],
    )


@router.get(
    "/assignments/{assignment_id}/months/{month}/billing-data", response_model=None
)
async def billing_data(
    assignment_id: UUID,
    month: str,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The billing data of a closed month, priced at the established inzet."""
    resource = await _visible(decider, subject, assignment_id)
    await get_assignment(db, assignment_id)
    parsed = month_overview.parse_month(month)
    try:
        data = await month_close.billing_data(db, assignment_id, parsed)
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    allocation_ids = {UUID(line.allocation_id) for line in data.lines}
    rows = (
        await db.execute(
            select(Allocation.id, Person.name, BudgetLine.role, BudgetLine.description)
            .join(Person, Person.id == Allocation.person_id)
            .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
            .where(Allocation.id.in_(allocation_ids))
        )
    ).all()
    info = {row[0]: (row[1], row[2] or row[3]) for row in rows}
    value = BillingDataOut(
        assignment_id=assignment_id,
        month=str(parsed),
        closed_at=data.closed_at,
        total_cents=data.total_cents,
        lines=sorted(
            (
                BillingLineOut(
                    allocation_id=UUID(line.allocation_id),
                    person_name=info.get(UUID(line.allocation_id), ("", ""))[0],
                    description=info.get(UUID(line.allocation_id), ("", ""))[1],
                    fte_pct=line.fte_pct,
                    category=line.category,
                    monthly_rate_cents=line.monthly_rate_cents,
                    amount_cents=line.amount_cents,
                )
                for line in data.lines
            ),
            key=lambda entry: (entry.description, entry.person_name),
        ),
    )
    return await filtered(decider, subject, resource, value)


@router.post(
    "/assignments/{assignment_id}/months/{month}/billing-exports",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def create_export(
    assignment_id: UUID,
    month: str,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Freeze the billing data of a closed month as an export run."""
    resource = await _visible(decider, subject, assignment_id)
    await require(
        decider, subject, Action.EDIT, resource, DataClass.ASSIGNMENT_FINANCIAL
    )
    parsed = month_overview.parse_month(month)
    try:
        export = await month_close.create_billing_export(
            db, assignment_id, parsed, actor=person
        )
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    export = await month_overview.get_export(db, export.id)
    value = await _export_out(db, export, person.name)
    return await filtered(decider, subject, resource, value)


@router.get("/assignments/{assignment_id}/billing-exports", response_model=None)
async def list_exports(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The export runs of an assignment, newest first."""
    resource = await _visible(decider, subject, assignment_id)
    await get_assignment(db, assignment_id)
    exports = await month_overview.exports_of_assignment(db, assignment_id)
    value = BillingExportListOut(
        exports=[await _export_out(db, export, name) for export, name in exports]
    )
    return await filtered(decider, subject, resource, value)


@router.get("/billing-exports/{export_id}/csv")
async def export_csv(
    export_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The export run as a CSV file for the financial system.

    The file has one row per person's inzet, with the role, the category and
    the amount, so it needs the right to read both the financial data of the
    assignment and the rates of the people on it.
    """
    export = await month_overview.get_export(db, export_id)
    resource = await _visible(decider, subject, export.assignment_id)
    for data_class in (DataClass.ASSIGNMENT_FINANCIAL, DataClass.PERSON_RATE):
        await require(decider, subject, Action.READ, resource, data_class)
    text = await month_overview.export_csv(db, export)
    month = calc.Month.of(export.month)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="factuurgegevens-{month}-{export.id}.csv"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


# -- delivered and invoiced ---------------------------------------------------


def _invoice_out(view: outgoing_invoices.InvoiceView) -> OutgoingInvoiceOut:
    invoice = view.invoice
    return OutgoingInvoiceOut(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        amount_cents=invoice.amount_cents,
        delivered_cents=view.delivered_cents,
        difference_cents=view.difference_cents,
        months=[str(calc.Month.of(d.month)) for d in view.deliveries],
        export_ids=[d.export_id for d in view.deliveries],
        source=invoice.source,
        note=invoice.note,
        recorded_at=invoice.created_at,
        recorded_by_name=view.recorded_by_name,
        withdrawn_at=invoice.withdrawn_at,
        withdrawn_by_name=view.withdrawn_by_name,
        withdrawn_reason=invoice.withdrawn_reason,
    )


def _month_out(month: outgoing_invoices.MonthBilling) -> MonthBillingOut:
    return MonthBillingOut(
        month=str(calc.Month.of(month.month)),
        closed=month.closed,
        state=month.state,
        deliverable_cents=month.deliverable_cents,
        to_deliver_cents=month.to_deliver_cents,
        export_id=month.export_id,
        delivered_at=month.delivered_at,
        delivered_by_name=month.delivered_by_name,
        delivered_cents=month.delivered_cents,
        invoice_id=month.invoice_id,
        invoice_number=month.invoice_number,
        invoice_date=month.invoice_date,
        invoiced_cents=month.invoiced_cents,
        invoice_on_earlier_delivery=month.invoice_on_earlier_delivery,
    )


async def _status(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    resource: Resource,
    assignment_id: UUID,
    year: int | None = None,
) -> dict[str, Any]:
    position = await outgoing_invoices.billing_position(db, assignment_id, year=year)
    invoices = await outgoing_invoices.invoices_of_assignment(db, assignment_id)
    value = BillingStatusOut(
        assignment_id=assignment_id,
        year=year,
        billable=position.billable,
        may_record_invoice=bool(
            await decide(decider, subject, Action.RECORD_INVOICE, resource)
        ),
        deliverable_cents=position.deliverable_cents,
        delivered_cents=position.delivered_cents,
        to_deliver_cents=position.to_deliver_cents,
        invoiced_cents=position.invoiced_cents,
        to_invoice_cents=position.to_invoice_cents,
        months=[_month_out(month) for month in position.months],
        invoices=[_invoice_out(view) for view in invoices],
    )
    return await filtered(decider, subject, resource, value)


@router.get("/assignments/{assignment_id}/billing-status", response_model=None)
async def billing_status(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    year: int | None = Query(default=None, ge=2000, le=2200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per closed month whether it was delivered and invoiced, with the totals.

    Delivered means billing data was exported for the financial
    administration. Invoiced means someone recorded that an invoice was
    sent; grip cannot see that by itself.
    """
    resource = await _visible(decider, subject, assignment_id)
    await get_assignment(db, assignment_id)
    return await _status(db, decider, subject, resource, assignment_id, year)


@router.get(
    "/assignments/{assignment_id}/outgoing-invoices/proposal", response_model=None
)
async def invoice_proposal(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    export_id: list[UUID] = Query(default_factory=list, max_length=120),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What was delivered for a selection of deliveries, added up."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.RECORD_INVOICE, resource)
    position = await outgoing_invoices.billing_position(db, assignment_id)
    chosen = [m for m in position.months if m.export_id in set(export_id)]
    value = InvoiceProposalOut(
        months=[str(calc.Month.of(m.month)) for m in chosen],
        delivered_cents=sum(m.delivered_cents or 0 for m in chosen),
    )
    return await filtered(decider, subject, resource, value)


@router.post(
    "/assignments/{assignment_id}/outgoing-invoices",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def record_invoice(
    assignment_id: UUID,
    body: RecordInvoiceIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record that an invoice was sent for one or several delivered months."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.RECORD_INVOICE, resource)
    await outgoing_invoices.record_invoice(
        db,
        assignment_id,
        export_ids=body.export_ids,
        invoice_number=body.invoice_number,
        invoice_date=body.invoice_date,
        amount_cents=body.amount_cents,
        note=body.note,
        actor=person,
    )
    return await _status(db, decider, subject, resource, assignment_id)


@router.patch("/outgoing-invoices/{invoice_id}", response_model=None)
async def correct_invoice(
    invoice_id: UUID,
    body: CorrectInvoiceIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Correct a recorded invoice; old and new values go to the audit log."""
    invoice = await outgoing_invoices.get_invoice(db, invoice_id)
    resource = await _visible(decider, subject, invoice.assignment_id)
    await require(decider, subject, Action.RECORD_INVOICE, resource)
    await outgoing_invoices.correct_invoice(
        db,
        invoice_id,
        actor=person,
        invoice_number=body.invoice_number,
        invoice_date=body.invoice_date,
        amount_cents=body.amount_cents,
        note=body.note,
        export_ids=body.export_ids,
    )
    return await _status(db, decider, subject, resource, invoice.assignment_id)


@router.post("/outgoing-invoices/{invoice_id}/withdraw", response_model=None)
async def withdraw_invoice(
    invoice_id: UUID,
    body: WithdrawInvoiceIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Take back an invoice that should not have been recorded."""
    invoice = await outgoing_invoices.get_invoice(db, invoice_id)
    resource = await _visible(decider, subject, invoice.assignment_id)
    await require(decider, subject, Action.RECORD_INVOICE, resource)
    await outgoing_invoices.withdraw_invoice(
        db, invoice_id, actor=person, reason=body.reason
    )
    return await _status(db, decider, subject, resource, invoice.assignment_id)
