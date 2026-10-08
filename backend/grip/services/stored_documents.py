"""Files kept in the database with a record, with limits on size and type.

A document belongs to one owning object. What may be stored depends on the
use: a signed quote is a pdf, a received invoice may also be a scan, a photo
or an e-invoice. The declared content type is never trusted on its own; the
content must also look like that type.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.services.errors import DomainValidationError, NotFoundError

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
REF_PREFIX = "stored_document:"

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
XML = "application/xml"

# Declared types that mean the same as a canonical one.
_ALIASES = {"text/xml": XML, "image/jpg": JPEG, "image/pjpeg": JPEG}
_EXTENSIONS = {PDF: ".pdf", PNG: ".png", JPEG: ".jpg", XML: ".xml"}

_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")


@dataclass(frozen=True)
class DocumentUse:
    """What a kind of owner accepts as a document."""

    owner_kind: str
    content_types: frozenset[str]
    # Shown when a file is refused, so the user knows what would be accepted.
    accepted_text: str


SIGNED_QUOTE = DocumentUse(
    owner_kind="quote_acceptance",
    content_types=frozenset({PDF}),
    accepted_text="Alleen een pdf-bestand kan worden vastgelegd.",
)
RECEIVED_INVOICE = DocumentUse(
    owner_kind="invoice_line",
    content_types=frozenset({PDF, PNG, JPEG, XML}),
    accepted_text=(
        "Dit bestand kan niet worden vastgelegd. Een factuur is een pdf, een "
        "scan of foto (png of jpg) of een e-factuur (xml)."
    ),
)
# The allowed types for a signed quote; kept under its old name for callers.
ALLOWED_CONTENT_TYPES = tuple(SIGNED_QUOTE.content_types)


def document_ref(document_id: UUID) -> str:
    return f"{REF_PREFIX}{document_id}"


def parse_document_ref(ref: str | None) -> UUID | None:
    if not ref or not ref.startswith(REF_PREFIX):
        return None
    try:
        return UUID(ref[len(REF_PREFIX) :])
    except ValueError:
        return None


def _safe_filename(filename: str | None, content_type: str = PDF) -> str:
    """The last path segment, without characters that mean something to a
    file system, a shell or an HTTP header."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(
        ch for ch in name if ch.isprintable() and ch not in "\"<>|:*?;'`$&%\r\n"
    )
    name = name.lstrip(".").strip()
    return name[:255] or f"document{_EXTENSIONS.get(content_type, '')}"


def _looks_like_xml(content: bytes) -> bool:
    head = content[:512]
    for bom in _BOMS:
        if head.startswith(bom):
            head = head[len(bom) :]
            break
    # UTF-16 text has a zero byte next to every ASCII character.
    head = head.replace(b"\x00", b"").lstrip()
    return head.startswith(b"<?xml") or (
        head.startswith(b"<")
        and not head.lower().startswith((b"<!doctype html", b"<html"))
    )


def content_matches(content_type: str, content: bytes) -> bool:
    """Whether the content starts the way a file of this type does."""
    if content_type == PDF:
        return content.startswith(_PDF_MAGIC)
    if content_type == PNG:
        return content.startswith(_PNG_MAGIC)
    if content_type == JPEG:
        return content.startswith(_JPEG_MAGIC)
    if content_type == XML:
        return _looks_like_xml(content)
    return False


def canonical_content_type(declared: str | None) -> str:
    value = (declared or "").split(";", 1)[0].strip().lower()
    return _ALIASES.get(value, value)


async def store_document(
    session: AsyncSession,
    *,
    use: DocumentUse,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    actor: Person | None,
    owner_id: UUID | None = None,
) -> StoredDocument:
    """Store a file for the given use. Refuses a wrong type or size.

    Without ``owner_id`` the caller records the owner with ``assign_owner``
    in the same transaction, for an owner that does not exist yet.
    """
    if not content:
        raise DomainValidationError("Het bestand is leeg.")
    if len(content) > MAX_DOCUMENT_BYTES:
        limit_mb = MAX_DOCUMENT_BYTES // (1024 * 1024)
        raise DomainValidationError(
            f"Het bestand is te groot. De grens is {limit_mb} MB."
        )
    declared = canonical_content_type(content_type)
    if declared not in use.content_types or not content_matches(declared, content):
        raise DomainValidationError(use.accepted_text)
    document = StoredDocument(
        owner_kind=use.owner_kind if owner_id is not None else None,
        owner_id=owner_id,
        filename=_safe_filename(filename, declared),
        content_type=declared,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        uploaded_by_id=actor.id if actor is not None else None,
    )
    session.add(document)
    await session.flush()
    return document


async def store_pdf(
    session: AsyncSession,
    *,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    actor: Person | None,
) -> StoredDocument:
    """Store a signed quote as pdf. Refuses anything that is not a pdf."""
    return await store_document(
        session,
        use=SIGNED_QUOTE,
        content=content,
        filename=filename,
        content_type=content_type,
        actor=actor,
    )


def assign_owner(document: StoredDocument, use: DocumentUse, owner_id: UUID) -> None:
    """Record what a document belongs to, once the owner exists."""
    document.owner_kind = use.owner_kind
    document.owner_id = owner_id


async def load_document(session: AsyncSession, document_id: UUID) -> StoredDocument:
    """The document with its content loaded."""
    document = await session.get(
        StoredDocument, document_id, options=[undefer(StoredDocument.content)]
    )
    if document is None:
        raise NotFoundError("Document", document_id)
    return document


async def documents_of(
    session: AsyncSession, use: DocumentUse, owner_ids: Iterable[UUID]
) -> dict[UUID, list[StoredDocument]]:
    """The documents per owner, oldest first, without their content."""
    ids = list(set(owner_ids))
    if not ids:
        return {}
    rows = await session.execute(
        select(StoredDocument)
        .where(
            StoredDocument.owner_kind == use.owner_kind,
            StoredDocument.owner_id.in_(ids),
        )
        .order_by(StoredDocument.created_at, StoredDocument.id)
    )
    result: dict[UUID, list[StoredDocument]] = defaultdict(list)
    for document in rows.scalars():
        assert document.owner_id is not None
        result[document.owner_id].append(document)
    return result


async def owned_document(
    session: AsyncSession,
    use: DocumentUse,
    owner_id: UUID,
    document_id: UUID,
    *,
    with_content: bool = False,
) -> StoredDocument:
    """A document, only when it belongs to this owner.

    A document of another owner answers like one that does not exist, so an
    id cannot be used to reach a file through an owner one may see.
    """
    if with_content:
        # ``populate_existing``: a document this session already loaded
        # without its content would otherwise come back as it was.
        document = await session.get(
            StoredDocument,
            document_id,
            options=[undefer(StoredDocument.content)],
            populate_existing=True,
        )
    else:
        document = await session.get(StoredDocument, document_id)
    if (
        document is None
        or document.owner_kind != use.owner_kind
        or document.owner_id != owner_id
    ):
        raise NotFoundError("Bijlage", document_id)
    return document


async def delete_document(session: AsyncSession, document: StoredDocument) -> None:
    """Remove the file itself, not only the link to it."""
    await session.delete(document)
    await session.flush()


def content_disposition(filename: str) -> str:
    """An attachment disposition with the name in plain ASCII and in UTF-8.

    Always ``attachment``: an uploaded file is never rendered in the page.
    """
    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    ascii_name = ascii_name.replace("?", "_").replace('"', "_").replace("\\", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def download_headers(document: StoredDocument) -> dict[str, str]:
    """Headers that make a browser save the file and never run or guess it."""
    return {
        "Content-Disposition": content_disposition(document.filename),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, no-store",
    }
