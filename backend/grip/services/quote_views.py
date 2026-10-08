"""Read functions and small workflows around quotes, for the quote routes.

Everything that changes a quote goes through ``grip.services.quotes``. This
module adds what the screens need on top: quotes with their decision, the
invitations of a signer, the acceptance with an uploaded document, and the
context of the printable quote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.core.config import get_settings
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import Quote, QuoteAcceptance, QuoteInvitation, QuoteRejection
from grip.services import quotes, stored_documents
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.quote_document import QuoteDocumentContext

ISSUABLE_STATUSES = ("draft", "requested", "quoted", "rejected")


@dataclass(frozen=True)
class QuoteBundle:
    quote: Quote
    acceptance: QuoteAcceptance | None
    rejection: QuoteRejection | None
    issued_by_name: str | None


def describe_calc_error(exc: calc.CalcError) -> str:
    """A calculation error as a sentence for the user."""
    if isinstance(exc, calc.MissingRateCardError):
        return (
            "Voor een maand in de periode is er geen actieve tarievenkaart. "
            "Maak de tarievenkaart van dat jaar actief."
        )
    if isinstance(exc, calc.MissingRateError | calc.MissingScaleBandError):
        return (
            "De tarievenkaart mist een tarief of een schaalindeling die voor deze "
            "berekening nodig is."
        )
    if isinstance(exc, calc.MissingPersonScaleError):
        return "Van een ingezette persoon is de inzetschaal in deze periode onbekend."
    return "De bedragen kunnen niet worden berekend met de huidige gegevens."


async def _names(session: AsyncSession, person_ids: set[UUID]) -> dict[UUID, str]:
    if not person_ids:
        return {}
    result = await session.execute(
        select(Person.id, Person.name).where(Person.id.in_(person_ids))
    )
    return {row.id: row.name for row in result}


async def _bundles(session: AsyncSession, quote_list: list[Quote]) -> list[QuoteBundle]:
    ids = [q.id for q in quote_list]
    acceptances: dict[UUID, QuoteAcceptance] = {}
    rejections: dict[UUID, QuoteRejection] = {}
    if ids:
        for acc in (
            await session.execute(
                select(QuoteAcceptance).where(QuoteAcceptance.quote_id.in_(ids))
            )
        ).scalars():
            acceptances[acc.quote_id] = acc
        for rej in (
            await session.execute(
                select(QuoteRejection).where(QuoteRejection.quote_id.in_(ids))
            )
        ).scalars():
            rejections[rej.quote_id] = rej
    names = await _names(
        session, {q.issued_by_id for q in quote_list if q.issued_by_id}
    )
    return [
        QuoteBundle(
            quote=q,
            acceptance=acceptances.get(q.id),
            rejection=rejections.get(q.id),
            issued_by_name=names.get(q.issued_by_id) if q.issued_by_id else None,
        )
        for q in quote_list
    ]


async def quotes_of_assignment(
    session: AsyncSession, assignment_id: UUID
) -> list[QuoteBundle]:
    """The issued quotes of an assignment, newest first, with their decision."""
    result = await session.execute(
        select(Quote)
        .where(Quote.assignment_id == assignment_id)
        .order_by(Quote.issued_at.desc(), Quote.created_at.desc())
    )
    return await _bundles(session, list(result.scalars()))


async def quote_bundle(session: AsyncSession, quote_id: UUID) -> QuoteBundle:
    quote = await quotes.get_quote(session, quote_id)
    return (await _bundles(session, [quote]))[0]


async def invitations_of_quote(
    session: AsyncSession, quote_id: UUID
) -> list[QuoteInvitation]:
    result = await session.execute(
        select(QuoteInvitation)
        .where(QuoteInvitation.quote_id == quote_id)
        .order_by(QuoteInvitation.created_at)
    )
    return list(result.scalars())


async def invited_quotes(
    session: AsyncSession, email: str, *, now: datetime | None = None
) -> list[tuple[QuoteInvitation, Quote, Assignment]]:
    """Quotes this email address is invited to sign, expired ones left out."""
    now = now or datetime.now(UTC)
    result = await session.execute(
        select(QuoteInvitation, Quote, Assignment)
        .join(Quote, Quote.id == QuoteInvitation.quote_id)
        .join(Assignment, Assignment.id == Quote.assignment_id)
        .where(
            func.lower(QuoteInvitation.email) == email.strip().lower(),
            or_(
                QuoteInvitation.expires_at.is_(None),
                QuoteInvitation.expires_at > now,
            ),
        )
        .order_by(Quote.issued_at.desc())
    )
    return [(row[0], row[1], row[2]) for row in result]


async def _organisation(
    session: AsyncSession, organisation_id: UUID | None
) -> Organisation | None:
    if organisation_id is None:
        return None
    return await session.get(Organisation, organisation_id)


def _organisation_ref(organisation: Organisation) -> dict[str, Any]:
    ref: dict[str, Any] = {"name": organisation.name}
    if organisation.tooi_uri:
        ref["tooi_uri"] = organisation.tooi_uri
    if organisation.unit_key:
        ref["unit_key"] = organisation.unit_key
    if organisation.instance_uri:
        ref["instance_uri"] = organisation.instance_uri
    return ref


async def client_reference(
    session: AsyncSession, assignment: Assignment, fallback_name: str | None = None
) -> dict[str, Any]:
    """The organisation an acceptance is made on behalf of.

    The client of the assignment when it has one; otherwise the name given
    by whoever records the acceptance.
    """
    client = await _organisation(session, assignment.client_organisation_id)
    if client is not None:
        return _organisation_ref(client)
    name = (fallback_name or "").strip()
    if not name:
        raise DomainValidationError(
            "De opdracht heeft geen opdrachtgever. Geef de naam van de organisatie "
            "namens wie wordt getekend."
        )
    return {"name": name}


async def document_context(session: AsyncSession, quote: Quote) -> QuoteDocumentContext:
    assignment = await session.get(Assignment, quote.assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", quote.assignment_id)
    contractor = await _organisation(session, assignment.contractor_organisation_id)
    client = await _organisation(session, assignment.client_organisation_id)
    return QuoteDocumentContext(
        quote_uri=quote.uri,
        snapshot_hash=quote.snapshot_hash,
        issued_at=quote.issued_at,
        contractor_name=contractor.name
        if contractor is not None
        else get_settings().INSTANCE_NAME,
        client_name=client.name if client is not None else None,
        client_contact=assignment.client_contact,
    )


async def accept_with_uploaded_pdf(
    session: AsyncSession,
    quote_id: UUID,
    *,
    actor: Person,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    signer_name: str,
    signer_email: str,
    signer_function: str | None = None,
    organisation_name: str | None = None,
    signed_at: datetime | None = None,
) -> QuoteAcceptance:
    """Record an acceptance from a signed pdf that came back outside grip.

    The file is stored with the acceptance. The hash in the acceptance is
    that of the issued quote: the person recording it vouches that the
    signed document is this quote.
    """
    if not signer_name.strip():
        raise DomainValidationError("Geef de naam van wie heeft getekend.")
    if "@" not in signer_email:
        raise DomainValidationError("Geef het e-mailadres van wie heeft getekend.")
    quote = await quotes.get_quote(session, quote_id)
    assignment = await session.get(Assignment, quote.assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", quote.assignment_id)
    organisation = await client_reference(session, assignment, organisation_name)
    document = await stored_documents.store_pdf(
        session,
        content=content,
        filename=filename,
        content_type=content_type,
        actor=actor,
    )
    return await quotes.accept_quote(
        session,
        quote_id,
        quote_hash=quote.snapshot_hash,
        signer_name=signer_name.strip(),
        signer_email=signer_email,
        signer_function=(signer_function or "").strip() or None,
        organisation=organisation,
        form="uploaded_pdf",
        actor=actor,
        signed_at=signed_at,
        document_sha256=document.sha256,
        document_ref=stored_documents.document_ref(document.id),
    )


async def accept_via_signing_link(
    session: AsyncSession,
    quote_id: UUID,
    *,
    quote_hash: str,
    signer_name: str,
    signer_email: str,
    signer_person_id: UUID | None,
    signer_function: str | None = None,
    organisation_name: str | None = None,
) -> QuoteAcceptance:
    """The invited signer accepts the quote they were shown.

    ``quote_hash`` is the hash of what the signer saw; a quote that changed
    in the meantime is a different quote and the service refuses it.
    """
    quote = await quotes.get_quote(session, quote_id)
    assignment = await session.get(Assignment, quote.assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", quote.assignment_id)
    organisation = await client_reference(session, assignment, organisation_name)
    actor = await session.get(Person, signer_person_id) if signer_person_id else None
    return await quotes.accept_quote(
        session,
        quote_id,
        quote_hash=quote_hash,
        signer_name=signer_name,
        signer_email=signer_email,
        signer_function=(signer_function or "").strip() or None,
        signer_person_id=signer_person_id,
        organisation=organisation,
        form="signing_link",
        actor=actor,
    )


async def reject_via_signing_link(
    session: AsyncSession,
    quote_id: UUID,
    *,
    quote_hash: str,
    signer_person_id: UUID | None,
    reason: str | None = None,
) -> QuoteRejection:
    quote = await quotes.get_quote(session, quote_id)
    assignment = await session.get(Assignment, quote.assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", quote.assignment_id)
    client = await _organisation(session, assignment.client_organisation_id)
    actor = await session.get(Person, signer_person_id) if signer_person_id else None
    return await quotes.reject_quote(
        session,
        quote_id,
        quote_hash=quote_hash,
        actor=actor,
        reason=(reason or "").strip() or None,
        organisation=_organisation_ref(client) if client is not None else None,
    )
