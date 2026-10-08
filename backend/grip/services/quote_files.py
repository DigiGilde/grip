"""The quote as a file: laid out once, kept, and served from then on.

The content of a quote is frozen when it is made, and its fingerprint proves
that content. But what a client holds, reads and signs is a file. Laying the
file out again on every request made it depend on the settings of that
moment (letterhead, typeface, template): the same quote could come out as a
different document. So the PDF is made once, when the quote is made, and
stored with it together with the SHA-256 of its bytes. "Which document was
signed" is answered with those bytes.

Where the bytes live: in the stored-documents mechanism, owned by the quote.
That mechanism already keeps files apart from the rows they belong to (the
content is loaded only when asked for), checks type and size, and is how a
signed quote and a received invoice are kept. The quote row carries the
reference to the document and the hash.

Three origins, recorded truthfully:

- ``issue``: fixed when the quote was made here. If laying out fails at
  that moment, the quote is not made.
- ``afterwards``: a quote from before files were kept. Its file is laid
  out once, now, with today's settings. That is the best available, and the
  record says that it happened after the making.
- ``received``: a quote another instance sent. The contract carries the
  content, not the sender's file, so this is this instance's own lay-out of
  that content, fixed when it is first needed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.models.quote import Quote
from grip.services import stored_documents
from grip.services.errors import DomainError, NotFoundError
from grip.services.quote_document import render_quote_pdf
from grip.services.stored_documents import PDF, DocumentUse

ORIGIN_ISSUE = "issue"
ORIGIN_AFTERWARDS = "afterwards"
ORIGIN_RECEIVED = "received"

ORIGIN_TEXTS = {
    ORIGIN_ISSUE: "vastgelegd bij het maken van de offerte",
    ORIGIN_AFTERWARDS: "vastgelegd na het maken van de offerte",
    ORIGIN_RECEIVED: (
        "in deze instantie opgemaakt uit de ontvangen inhoud; niet het bestand "
        "van de afzender"
    ),
}

QUOTE_DOCUMENT = DocumentUse(
    owner_kind="quote",
    content_types=frozenset({PDF}),
    accepted_text="Het document van een offerte is een pdf.",
)


class QuoteDocumentError(DomainError):
    """The file of a quote could not be made, so nothing is kept."""


@dataclass(frozen=True)
class QuoteFile:
    content: bytes
    sha256: str
    fixed_at: datetime
    origin: str

    @property
    def origin_text(self) -> str:
        """How the file came to be, as a reader is told."""
        day = f"{self.fixed_at:%d-%m-%Y}"
        return f"document {ORIGIN_TEXTS[self.origin]}, op {day}"


def _file_stem(quote: Quote) -> str:
    return quote.reference or f"{quote.issued_at:%Y%m%d}-{quote.id}"


def late_origin(quote: Quote) -> str:
    """The origin of a file that is fixed after the quote already existed."""
    # A quote that came in from another instance was not issued by anyone here.
    if quote.issued_by_id is not None:
        return ORIGIN_AFTERWARDS
    from grip.core.config import get_settings

    own = get_settings().INSTANCE_BASE_URI.rstrip("/")
    return ORIGIN_AFTERWARDS if quote.uri.startswith(own) else ORIGIN_RECEIVED


async def fix_document(
    session: AsyncSession, quote: Quote, *, origin: str, now: datetime | None = None
) -> None:
    """Lay the quote out once and keep the file. Does nothing if it is kept.

    Raises when the file cannot be made; the caller's transaction then
    leaves nothing behind.
    """
    if quote.document_ref is not None:
        return
    # Imported here: quote_views builds on quotes, which calls this module.
    from grip.services import quote_views

    context = await quote_views.document_context(session, quote)
    snapshot = quote.snapshot
    try:
        # Laying out a page takes a moment; keep the event loop free.
        pdf = await asyncio.to_thread(render_quote_pdf, snapshot, context)
    except DomainError:
        raise
    except Exception as exc:
        raise QuoteDocumentError(
            "Het document van de offerte kon niet worden opgemaakt. De offerte "
            "is niet gemaakt."
        ) from exc
    document = await stored_documents.store_document(
        session,
        use=QUOTE_DOCUMENT,
        content=pdf,
        filename=f"offerte-{_file_stem(quote)}.pdf",
        content_type=PDF,
        actor=None,
        owner_id=quote.id,
        uploaded=False,
    )
    quote.document_ref = stored_documents.document_ref(document.id)
    quote.document_sha256 = document.sha256
    quote.document_fixed_at = now or datetime.now(UTC)
    quote.document_origin = origin
    await session.flush()
    if origin != ORIGIN_ISSUE:
        # Made together with the quote, the file is part of the record of
        # making it. Fixed later, it is a fact of its own: when, and that it
        # was not there before.
        record_audit(
            session,
            actor=None,
            action=UPDATE,
            entity="quote",
            entity_id=quote.id,
            old_value={"document_sha256": None},
            new_value={
                "document_sha256": quote.document_sha256,
                "document_origin": origin,
                "document_fixed_at": quote.document_fixed_at.isoformat(),
            },
        )


async def file_of(session: AsyncSession, quote: Quote) -> QuoteFile:
    """The file of a quote: the kept bytes, never a new lay-out.

    A quote without a file (made before files were kept, or received from
    another instance) gets one now, once, and the record says so.
    """
    if quote.document_ref is None:
        await fix_document(session, quote, origin=late_origin(quote))
    document_id = stored_documents.parse_document_ref(quote.document_ref)
    if document_id is None:
        raise NotFoundError("Document", quote.id)
    document = await stored_documents.owned_document(
        session, QUOTE_DOCUMENT, quote.id, document_id, with_content=True
    )
    assert quote.document_fixed_at is not None and quote.document_origin is not None
    return QuoteFile(
        content=bytes(document.content),
        sha256=document.sha256,
        fixed_at=quote.document_fixed_at,
        origin=quote.document_origin,
    )


async def fix_missing(session: AsyncSession) -> int:
    """Give every quote without a file its file. Returns how many got one.

    For the one-time catch-up after this change; ``file_of`` does the same
    for a single quote the first time its file is asked for.
    """
    quotes = (
        await session.execute(select(Quote).where(Quote.document_ref.is_(None)))
    ).scalars()
    fixed = 0
    for quote in list(quotes):
        await fix_document(session, quote, origin=late_origin(quote))
        fixed += 1
    return fixed
