"""Changing an invoice line, and the documents that belong to one.

A received invoice is a document: the line holds the number, the period and
the amount, the attachment is the invoice itself. Attachments are stored
documents owned by the line; removing the line removes them.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.cost import INVOICE_LINE_KINDS, InvoiceLine
from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.services import stored_documents
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import audit_fields
from grip.services.stored_documents import RECEIVED_INVOICE

_LINE_FIELDS = ("reference", "description", "kind", "amount_cents", "period")
_AUDIT_FIELDS = ("cost_item_id", *_LINE_FIELDS)


def _document_audit(document: StoredDocument) -> dict[str, Any]:
    return {
        "invoice_line_id": str(document.owner_id),
        "filename": document.filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "sha256": document.sha256,
    }


async def get_invoice_line(
    session: AsyncSession, cost_item_id: UUID, invoice_line_id: UUID
) -> InvoiceLine:
    """The line, only when it is a line of this cost item."""
    line = await session.get(InvoiceLine, invoice_line_id)
    if line is None or line.cost_item_id != cost_item_id:
        raise NotFoundError("Factuurregel", invoice_line_id)
    return line


async def update_invoice_line(
    session: AsyncSession,
    cost_item_id: UUID,
    invoice_line_id: UUID,
    *,
    actor: Person | None,
    changes: dict[str, Any],
) -> InvoiceLine:
    """Change fields of an invoice line. ``changes`` holds only what changes;
    reference, description and period may be set to ``None``."""
    unknown = set(changes) - set(_LINE_FIELDS)
    if unknown:
        raise DomainValidationError(f"Onbekende velden: {sorted(unknown)}")
    line = await get_invoice_line(session, cost_item_id, invoice_line_id)
    old = audit_fields(line, _AUDIT_FIELDS)
    if "kind" in changes:
        if changes["kind"] not in INVOICE_LINE_KINDS:
            raise DomainValidationError(
                f"Onbekend soort factuurregel: {changes['kind']}"
            )
        line.kind = changes["kind"]
    if "amount_cents" in changes:
        if not isinstance(changes["amount_cents"], int):
            raise DomainValidationError("Een bedrag is verplicht.")
        line.amount_cents = changes["amount_cents"]
    if "reference" in changes:
        line.reference = changes["reference"] or None
    if "description" in changes:
        line.description = changes["description"] or None
    if "period" in changes:
        period = changes["period"]
        if period is not None and not isinstance(period, date):
            raise DomainValidationError("De periode is geen geldige datum.")
        line.period = period
    await session.flush()
    new = audit_fields(line, _AUDIT_FIELDS)
    if new != old:
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="invoice_line",
            entity_id=line.id,
            old_value=old,
            new_value=new,
        )
    return line


async def add_attachment(
    session: AsyncSession,
    cost_item_id: UUID,
    invoice_line_id: UUID,
    *,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    actor: Person | None,
) -> StoredDocument:
    """Attach a received invoice (pdf, scan, photo or e-invoice) to a line."""
    line = await get_invoice_line(session, cost_item_id, invoice_line_id)
    document = await stored_documents.store_document(
        session,
        use=RECEIVED_INVOICE,
        owner_id=line.id,
        content=content,
        filename=filename,
        content_type=content_type,
        actor=actor,
    )
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="invoice_attachment",
        entity_id=document.id,
        new_value=_document_audit(document),
    )
    return document


async def get_attachment(
    session: AsyncSession,
    cost_item_id: UUID,
    invoice_line_id: UUID,
    document_id: UUID,
    *,
    with_content: bool = False,
) -> StoredDocument:
    line = await get_invoice_line(session, cost_item_id, invoice_line_id)
    return await stored_documents.owned_document(
        session, RECEIVED_INVOICE, line.id, document_id, with_content=with_content
    )


async def remove_attachment(
    session: AsyncSession,
    cost_item_id: UUID,
    invoice_line_id: UUID,
    document_id: UUID,
    *,
    actor: Person | None,
) -> None:
    """Delete an attachment: the file itself goes, the audit row stays."""
    document = await get_attachment(session, cost_item_id, invoice_line_id, document_id)
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="invoice_attachment",
        entity_id=document.id,
        old_value=_document_audit(document),
    )
    await stored_documents.delete_document(session, document)


async def delete_invoice_line_with_attachments(
    session: AsyncSession,
    cost_item_id: UUID,
    invoice_line_id: UUID,
    *,
    actor: Person | None,
) -> int:
    """Delete a line and every file attached to it. Returns how many files."""
    from grip.services import costs

    line = await get_invoice_line(session, cost_item_id, invoice_line_id)
    documents = (
        await stored_documents.documents_of(session, RECEIVED_INVOICE, [line.id])
    ).get(line.id, [])
    for document in documents:
        record_audit(
            session,
            actor=actor,
            action=DELETE,
            entity="invoice_attachment",
            entity_id=document.id,
            old_value=_document_audit(document),
        )
        await stored_documents.delete_document(session, document)
    await costs.delete_invoice_line(session, line.id, actor=actor)
    return len(documents)
