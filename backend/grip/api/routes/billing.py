"""Billing data of a closed month, and export runs for the financial system.

Grip makes no invoices. It produces the data an invoice or an internal
settlement is made from: per closed month the established inzet priced at
the rate card, frozen as an export run and downloadable as CSV.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import Action, DataClass, Decider, Resource, Subject
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
)
from grip.services import month_close, month_overview, quote_views
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
