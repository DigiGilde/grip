"""Cost items, invoice lines (purchase side) and coverage by budget lines."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.assignment import BudgetLine
from grip.models.cost import (
    INVOICE_LINE_KINDS,
    REQUEST_WAITING,
    CostCoverage,
    CostItem,
    InvoiceLine,
)
from grip.models.person import Person
from grip.repositories.domain import CostRepository
from grip.services import cost_references, stale
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import audit_fields


def _plain_pct(value: Decimal) -> str:
    """A percentage as a person writes it: 110, or 62,5; never 110.00."""
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


_ITEM_FIELDS = ("description", "budgeted_cents", "executor_organisation_id")
# Leaves the executor of a cost item as it is.
UNCHANGED: object = object()
_INVOICE_FIELDS = (
    "cost_item_id",
    "reference",
    "description",
    "kind",
    "amount_cents",
    "period",
)
_COVERAGE_FIELDS = ("cost_item_id", "budget_line_id", "pct")


async def get_cost_item(session: AsyncSession, cost_item_id: UUID) -> CostItem:
    item = await session.get(CostItem, cost_item_id)
    if item is None:
        raise NotFoundError("Kostenpost", cost_item_id)
    return item


async def create_cost_item(
    session: AsyncSession,
    *,
    description: str,
    actor: Person | None,
    budgeted_cents: int = 0,
    executor_organisation_id: UUID | None = None,
    period: date | None = None,
    require_connection: bool = True,
) -> CostItem:
    """Add a cost item. With an executor it is a reference, and the executor
    is asked to make the item (ADR 0052); ``period`` goes with that request.

    Without ``require_connection`` the executor need not be connected yet;
    the request then waits until it is. For example data only.
    """
    if budgeted_cents < 0:
        raise DomainValidationError("Een bedrag kan niet negatief zijn.")
    if executor_organisation_id is not None and require_connection:
        await cost_references.require_possible_executor(
            session, executor_organisation_id
        )
    item = CostItem(
        description=description,
        budgeted_cents=budgeted_cents,
        created_by_id=actor.id if actor is not None else None,
        executor_organisation_id=executor_organisation_id,
    )
    if executor_organisation_id is not None:
        item.request_sequence = 1
        item.request_status = REQUEST_WAITING
        item.request_period = period
    session.add(item)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="cost_item",
        entity_id=item.id,
        new_value=audit_fields(item, _ITEM_FIELDS),
    )
    return item


async def _invoice_line_count(session: AsyncSession, cost_item_id: UUID) -> int:
    return len(await CostRepository(session).invoice_lines([cost_item_id]))


async def update_cost_item(
    session: AsyncSession,
    cost_item_id: UUID,
    *,
    actor: Person | None,
    description: str | None = None,
    budgeted_cents: int | None = None,
    executor_organisation_id: UUID | None | object = UNCHANGED,
) -> CostItem:
    """Change a cost item.

    On a reference a change of description or amount is a request to the
    executor, who applies it. An item of this organisation can get an
    executor while it has no invoices; a reference keeps its executor.
    """
    item = await get_cost_item(session, cost_item_id)
    await stale.check(session, item, "deze kostenpost")
    if budgeted_cents is not None and budgeted_cents < 0:
        raise DomainValidationError("Een bedrag kan niet negatief zijn.")
    executor = (
        item.executor_organisation_id
        if executor_organisation_id is UNCHANGED
        else executor_organisation_id
    )
    if executor is not None and not isinstance(executor, UUID):
        raise DomainValidationError("Onbekende uitvoerder.")
    if cost_references.is_reference(item):
        if executor != item.executor_organisation_id:
            raise DomainValidationError(cost_references.EXECUTOR_FIXED)
        if description is None and budgeted_cents is None:
            return item
        asked_description = description or item.description
        asked_cents = (
            budgeted_cents if budgeted_cents is not None else item.budgeted_cents
        )
        if asked_description is None or asked_cents is None:
            # What the executor has now completes a change of one of the two.
            reference = (await cost_references.read(session, [item])).get(item.id)
            if reference is not None and reference.content is not None:
                asked_description = asked_description or reference.content.description
                if asked_cents is None:
                    asked_cents = reference.content.budgeted_cents
        if asked_description is None or asked_cents is None:
            raise DomainValidationError(
                "Geef omschrijving en bedrag op om de uitvoerder om een wijziging "
                "te vragen."
            )
        await cost_references.ask(
            session,
            item,
            actor=actor,
            description=asked_description,
            budgeted_cents=asked_cents,
        )
        return item

    old = audit_fields(item, _ITEM_FIELDS)
    if description is not None:
        item.description = description
    if budgeted_cents is not None:
        item.budgeted_cents = budgeted_cents
    if executor is not None:
        if item.reference_uri is not None:
            raise DomainValidationError(cost_references.REQUESTED_HERE)
        if await _invoice_line_count(session, item.id):
            raise DomainValidationError(
                "Een kostenpost met facturen kan geen uitvoerder krijgen. "
                "Voeg een nieuwe kostenpost toe."
            )
        assert isinstance(executor, UUID)
        await cost_references.require_possible_executor(session, executor)
        item.executor_organisation_id = executor
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="cost_item",
        entity_id=item.id,
        old_value=old,
        new_value=audit_fields(item, _ITEM_FIELDS),
    )
    if item.executor_organisation_id is not None:
        assert item.description is not None and item.budgeted_cents is not None
        await cost_references.ask(
            session,
            item,
            actor=actor,
            description=item.description,
            budgeted_cents=item.budgeted_cents,
        )
    return item


async def delete_reference(
    session: AsyncSession, cost_item_id: UUID, *, actor: Person | None
) -> None:
    """Remove a reference with its coverage here. Only a reference: an item
    of this organisation has invoices that stay on record. The cost item at
    the executor stays as it is."""
    item = await get_cost_item(session, cost_item_id)
    if not cost_references.is_reference(item):
        raise DomainValidationError(
            "Alleen een kostenpost die een andere organisatie uitvoert, kan weg."
        )
    for coverage in await CostRepository(session).coverages_of_item(item.id):
        record_audit(
            session,
            actor=actor,
            action=DELETE,
            entity="cost_coverage",
            entity_id=coverage.id,
            old_value=audit_fields(coverage, _COVERAGE_FIELDS),
        )
        await session.delete(coverage)
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="cost_item",
        entity_id=item.id,
        old_value=audit_fields(item, _ITEM_FIELDS),
    )
    await session.flush()
    await session.execute(delete(CostItem).where(CostItem.id == item.id))
    session.expunge(item)


async def add_invoice_line(
    session: AsyncSession,
    cost_item_id: UUID,
    *,
    kind: str,
    amount_cents: int,
    actor: Person | None,
    reference: str | None = None,
    description: str | None = None,
    period: date | None = None,
) -> InvoiceLine:
    """Record a realised or estimated amount on a cost item."""
    if kind not in INVOICE_LINE_KINDS:
        raise DomainValidationError(f"Onbekend soort factuurregel: {kind}")
    item = await get_cost_item(session, cost_item_id)
    if cost_references.is_reference(item):
        raise DomainValidationError(cost_references.LINES_AT_EXECUTOR)
    line = InvoiceLine(
        cost_item_id=cost_item_id,
        reference=reference,
        description=description,
        kind=kind,
        amount_cents=amount_cents,
        period=period,
    )
    session.add(line)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="invoice_line",
        entity_id=line.id,
        new_value=audit_fields(line, _INVOICE_FIELDS),
    )
    return line


async def delete_invoice_line(
    session: AsyncSession, invoice_line_id: UUID, *, actor: Person | None
) -> None:
    line = await session.get(InvoiceLine, invoice_line_id)
    if line is None:
        raise NotFoundError("Factuurregel", invoice_line_id)
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="invoice_line",
        entity_id=line.id,
        old_value=audit_fields(line, _INVOICE_FIELDS),
    )
    await session.delete(line)
    await session.flush()


async def set_coverage(
    session: AsyncSession,
    cost_item_id: UUID,
    budget_line_id: UUID,
    pct: Decimal,
    *,
    actor: Person | None,
) -> CostCoverage:
    """Let a budget line cover a share of a cost item (create or change).

    The shares of one cost item may not add up to more than 100 percent.
    """
    pct = Decimal(pct)
    if not Decimal(0) < pct <= Decimal(100):
        raise DomainValidationError(
            "Een dekkingspercentage ligt boven 0 en is hoogstens 100."
        )
    await get_cost_item(session, cost_item_id)
    if await session.get(BudgetLine, budget_line_id) is None:
        raise NotFoundError("Begrotingsregel", budget_line_id)
    coverages = await CostRepository(session).coverages_of_item(cost_item_id)
    current = next((c for c in coverages if c.budget_line_id == budget_line_id), None)
    others = sum(
        (c.pct for c in coverages if c.budget_line_id != budget_line_id), Decimal(0)
    )
    if others + pct > Decimal(100):
        raise DomainValidationError(
            "De dekking van deze kostenpost komt op "
            f"{_plain_pct(others + pct)} procent; meer dan 100 kan niet."
        )
    old = None
    if current is None:
        current = CostCoverage(
            cost_item_id=cost_item_id, budget_line_id=budget_line_id, pct=pct
        )
        session.add(current)
    else:
        await stale.check(session, current, "deze dekking")
        old = audit_fields(current, _COVERAGE_FIELDS)
        current.pct = pct
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE if old else CREATE,
        entity="cost_coverage",
        entity_id=current.id,
        old_value=old,
        new_value=audit_fields(current, _COVERAGE_FIELDS),
    )
    return current


async def remove_coverage(
    session: AsyncSession,
    cost_item_id: UUID,
    budget_line_id: UUID,
    *,
    actor: Person | None,
) -> None:
    result = await session.execute(
        select(CostCoverage).where(
            CostCoverage.cost_item_id == cost_item_id,
            CostCoverage.budget_line_id == budget_line_id,
        )
    )
    coverage = result.scalar_one_or_none()
    if coverage is None:
        raise NotFoundError("Kostendekking", f"{cost_item_id}/{budget_line_id}")
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="cost_coverage",
        entity_id=coverage.id,
        old_value=audit_fields(coverage, _COVERAGE_FIELDS),
    )
    await session.delete(coverage)
    await session.flush()
