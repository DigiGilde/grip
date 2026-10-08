"""Cost items, invoice lines (purchase side) and coverage by budget lines."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.assignment import BudgetLine
from grip.models.cost import INVOICE_LINE_KINDS, CostCoverage, CostItem, InvoiceLine
from grip.models.person import Person
from grip.repositories.domain import CostRepository
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import audit_fields

_ITEM_FIELDS = ("description", "budgeted_cents")
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
) -> CostItem:
    if budgeted_cents < 0:
        raise DomainValidationError("Een bedrag kan niet negatief zijn.")
    item = CostItem(description=description, budgeted_cents=budgeted_cents)
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


async def update_cost_item(
    session: AsyncSession,
    cost_item_id: UUID,
    *,
    actor: Person | None,
    description: str | None = None,
    budgeted_cents: int | None = None,
) -> CostItem:
    item = await get_cost_item(session, cost_item_id)
    old = audit_fields(item, _ITEM_FIELDS)
    if description is not None:
        item.description = description
    if budgeted_cents is not None:
        if budgeted_cents < 0:
            raise DomainValidationError("Een bedrag kan niet negatief zijn.")
        item.budgeted_cents = budgeted_cents
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
    return item


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
    await get_cost_item(session, cost_item_id)
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
            f"De dekking van deze kostenpost komt op {others + pct} procent; "
            "meer dan 100 kan niet."
        )
    old = None
    if current is None:
        current = CostCoverage(
            cost_item_id=cost_item_id, budget_line_id=budget_line_id, pct=pct
        )
        session.add(current)
    else:
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
