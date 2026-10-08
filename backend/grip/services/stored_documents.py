"""Files kept in the database with a record, with limits on size and type."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.services.errors import DomainValidationError, NotFoundError

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ("application/pdf",)
REF_PREFIX = "stored_document:"

_PDF_MAGIC = b"%PDF-"


def document_ref(document_id: UUID) -> str:
    return f"{REF_PREFIX}{document_id}"


def parse_document_ref(ref: str | None) -> UUID | None:
    if not ref or not ref.startswith(REF_PREFIX):
        return None
    try:
        return UUID(ref[len(REF_PREFIX) :])
    except ValueError:
        return None


def _safe_filename(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>|:*?')
    return name[:255] or "document.pdf"


async def store_pdf(
    session: AsyncSession,
    *,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    actor: Person | None,
) -> StoredDocument:
    """Store a pdf. Refuses anything that is not a pdf or is too large.

    The declared content type is not trusted on its own: the content must
    also start as a pdf does.
    """
    if not content:
        raise DomainValidationError("Het bestand is leeg.")
    if len(content) > MAX_DOCUMENT_BYTES:
        limit_mb = MAX_DOCUMENT_BYTES // (1024 * 1024)
        raise DomainValidationError(
            f"Het bestand is te groot. De grens is {limit_mb} MB."
        )
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES or not content.startswith(_PDF_MAGIC):
        raise DomainValidationError("Alleen een pdf-bestand kan worden vastgelegd.")
    document = StoredDocument(
        filename=_safe_filename(filename),
        content_type="application/pdf",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        uploaded_by_id=actor.id if actor is not None else None,
    )
    session.add(document)
    await session.flush()
    return document


async def load_document(session: AsyncSession, document_id: UUID) -> StoredDocument:
    """The document with its content loaded."""
    document = await session.get(
        StoredDocument, document_id, options=[undefer(StoredDocument.content)]
    )
    if document is None:
        raise NotFoundError("Document", document_id)
    return document
