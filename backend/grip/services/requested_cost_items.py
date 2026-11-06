"""A cost item that another organisation asked this one to make (ADR 0052).

This organisation makes the expense and owns the item: description, amount,
invoice lines, attachments and coverage. The item records who asked for it
and the URI of their reference. That organisation may change description
and amount by asking again, and reads the item; nobody else does either.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.cost import CostItem, InvoiceLine
from grip.models.organisation import Organisation
from grip.repositories.domain import CostRepository
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import audit_fields

FOREIGN_URI = "De verwijzing hoort niet bij de organisatie die om de kostenpost vraagt."

_ITEM_FIELDS = (
    "description",
    "budgeted_cents",
    "requester_organisation_id",
    "reference_uri",
    "reference_sequence",
)
_LINE_FIELDS = ("cost_item_id", "kind", "amount_cents", "period")


def _base(organisation: Organisation | None) -> str:
    if organisation is None:
        return ""
    return (organisation.instance_uri or "").strip().rstrip("/")


async def receive_request(
    session: AsyncSession,
    *,
    requester_organisation_id: UUID,
    reference_uri: str,
    sequence: int,
    description: str,
    budgeted_cents: int,
    period: date | None = None,
) -> tuple[CostItem, str]:
    """Make or change the item for a reference. Returns it and what happened:
    created, changed or ignored.

    ``requester_organisation_id`` is the asker as the transport established
    it, never a name in the message. The reference must be one that its
    instance minted, so only the same asker can change the item again. A
    request numbered at or below the last one applied changes nothing.

    A new item gets the asked amount as its expected invoice line, in the
    asked period. A change leaves invoice lines and coverage alone: those
    are this organisation's.
    """
    if budgeted_cents < 0:
        raise DomainValidationError("Een bedrag kan niet negatief zijn.")
    requester = await session.get(Organisation, requester_organisation_id)
    base = _base(requester)
    if not base or not reference_uri.startswith(f"{base}/id/kostenpost/"):
        raise DomainValidationError(FOREIGN_URI)
    item = await CostRepository(session).by_reference_uri(reference_uri)
    if item is not None:
        if item.requester_organisation_id != requester_organisation_id:
            raise NotFoundError("Kostenpost", reference_uri)
        if sequence <= item.reference_sequence:
            return item, "ignored"
        old = audit_fields(item, _ITEM_FIELDS)
        item.description = description
        item.budgeted_cents = budgeted_cents
        item.reference_sequence = sequence
        await session.flush()
        record_audit(
            session,
            actor=None,
            action=UPDATE,
            entity="cost_item",
            entity_id=item.id,
            old_value=old,
            new_value=audit_fields(item, _ITEM_FIELDS),
        )
        return item, "changed"
    item = CostItem(
        description=description,
        budgeted_cents=budgeted_cents,
        requester_organisation_id=requester_organisation_id,
        reference_uri=reference_uri,
        reference_sequence=sequence,
    )
    session.add(item)
    await session.flush()
    record_audit(
        session,
        actor=None,
        action=CREATE,
        entity="cost_item",
        entity_id=item.id,
        new_value=audit_fields(item, _ITEM_FIELDS),
    )
    if budgeted_cents > 0:
        line = InvoiceLine(
            cost_item_id=item.id,
            kind="estimate",
            amount_cents=budgeted_cents,
            period=period,
        )
        session.add(line)
        await session.flush()
        record_audit(
            session,
            actor=None,
            action=CREATE,
            entity="invoice_line",
            entity_id=line.id,
            new_value=audit_fields(line, _LINE_FIELDS),
        )
    return item, "created"


@dataclass(frozen=True)
class RequestedItem:
    item: CostItem
    lines: tuple[InvoiceLine, ...]


async def requested_by(
    session: AsyncSession,
    requester_organisation_id: UUID,
    reference_uris: Iterable[str],
) -> dict[str, RequestedItem]:
    """The items behind these references that this organisation asked for,
    by reference URI. Other references are not in the answer."""
    uris = list(dict.fromkeys(reference_uris))
    if not uris:
        return {}
    rows = await session.execute(
        select(CostItem).where(
            CostItem.reference_uri.in_(uris),
            CostItem.requester_organisation_id == requester_organisation_id,
        )
    )
    items = list(rows.scalars())
    lines = await CostRepository(session).invoice_lines([item.id for item in items])
    by_item: dict[UUID, list[InvoiceLine]] = {}
    for line in sorted(lines, key=lambda line: (line.period or date.max, line.id)):
        by_item.setdefault(line.cost_item_id, []).append(line)
    return {
        item.reference_uri: RequestedItem(item, tuple(by_item.get(item.id, ())))
        for item in items
        if item.reference_uri is not None
    }


__all__ = ["FOREIGN_URI", "RequestedItem", "receive_request", "requested_by"]
