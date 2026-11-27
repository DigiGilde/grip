"""Quotes: issue one, and record acceptance or rejection.

A quote is the one place where derived values are stored. When a quote is
issued its content is put in the canonical form (the contract's own terms,
as canonical JSON), those bytes are stored, and the hash over them is the
hash of the quote. That one hash is on the document, in an acceptance of
every form and in the messages to another instance (ADR 0020). After issue
nothing computes a hash of a quote again; a check compares with the stored
hash, which the database ties to the stored bytes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.chronicle.facts import ACCEPTANCE, INVITATION, OFFER, QUOTE, REJECTION
from grip.chronicle.writer import Established, changes_of, establish, row_of
from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.core.config import get_settings
from grip.events import stream
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import (
    ACCEPTANCE_FORMS,
    OFFER_CHANNELS,
    OFFER_CLIENT_INSTANCE,
    OFFER_DOCUMENT,
    OFFER_SIGNING_LINK,
    Quote,
    QuoteAcceptance,
    QuoteInvitation,
    QuoteOffer,
    QuoteRejection,
)
from grip.repositories.domain import AssignmentRepository
from grip.services import events, quote_approval, quote_channels, stale
from grip.services.assignments import (
    after_transition,
    check_transition,
    get_assignment,
    is_shared_with,
    mint_uri,
)
from grip.services.canonical import (
    canonical_form,
    hash_of,
    read,
    snapshot_hash,  # noqa: F401 - callers use quotes.snapshot_hash
)
from grip.services.errors import (
    DomainValidationError,
    NotFoundError,
    QuoteAlreadyDecidedError,
    QuoteHashMismatchError,
)
from grip.services.guards import (
    DossierClosedError,
    dossier_closed,
    ensure_dossier_open,
)
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    load_rate_book,
    to_calc_line,
)
from grip.services.quote_content import (
    QuoteLineSource,
    check_content,
    line_rates,
    line_source,
)
from grip.services.quote_reference import next_reference

CURRENCY = "EUR"


def _money(cents: int) -> dict[str, Any]:
    return {"amount_cents": cents, "currency": CURRENCY}


def _decimal_text(value: Decimal) -> str:
    """Exact decimal as text, without exponent or trailing zeros."""
    text = format(Decimal(value).normalize(), "f")
    return text if text != "-0" else "0"


def _snapshot_line(
    line: QuoteLineSource, rates: calc.RateBook, options: PricingOptions
) -> dict[str, Any]:
    calc_line = to_calc_line(line)
    amount = calc.budgeted(calc_line, rates, partial_months=options.partial_months)
    entry: dict[str, Any] = {
        "position": line.position,
        "description": line.description,
        "kind": line.kind,
    }
    if line.kind == "personnel":
        assert line.start_date and line.end_date and line.fte is not None
        if line.role:
            entry["role"] = line.role
        entry["fte"] = _decimal_text(line.fte)
        entry["rate_category"] = line.rate_category
        scales = _scales_of(rates, line.start_date, line.rate_category)
        if scales:
            entry["scales"] = scales
        entry["period"] = {
            "start_date": line.start_date.isoformat(),
            "end_date": line.end_date.isoformat(),
        }
        months = calc.budget_line_months(
            calc_line, rates, partial_months=options.partial_months
        )
        # One rate, or the rates per period of validity the line touches: a
        # rate card can change on any day (grip.services.quote_content).
        entry.update(line_rates(months))
    else:
        entry["year"] = line.year
    entry["amount"] = _money(amount)
    return entry


def _scales_of(rates: calc.RateBook, day: date, category: str | None) -> list[int]:
    """The scales that bill in this category on the card valid that day."""
    try:
        card = rates.card(day)
    except calc.CalcError:
        return []
    return sorted(band.scale for band in card.scale_bands if band.category == category)


def budget_part(
    lines: Sequence[QuoteLineSource], rates: calc.RateBook, options: PricingOptions
) -> dict[str, Any]:
    """The part of a quote's content that comes from the budget."""
    subtotals: dict[int, int] = {}
    for line in lines:
        for year, cents in calc.budgeted_by_year(
            to_calc_line(line), rates, partial_months=options.partial_months
        ).items():
            subtotals[year] = subtotals.get(year, 0) + cents
    return {
        "lines": [_snapshot_line(line, rates, options) for line in lines],
        "subtotals_per_year": [
            {"year": year, "amount": _money(cents)}
            for year, cents in sorted(subtotals.items())
        ],
        "total": _money(sum(subtotals.values())),
    }


def _cards_touched(
    lines: Sequence[QuoteLineSource], rates: calc.RateBook
) -> list[dict[str, str]]:
    """The rate cards whose validity meets the period of a priced line."""
    periods = [
        (line.start_date, line.end_date)
        for line in lines
        if line.kind == "personnel" and line.start_date and line.end_date
    ]
    return [
        {"id": card.id, "name": card.name}
        for card in rates.cards
        if (rates.include_draft or card.status is not calc.RateCardStatus.DRAFT)
        and any(
            card.valid_from <= end and (card.valid_to is None or card.valid_to >= start)
            for start, end in periods
        )
    ]


async def sender_name(session: AsyncSession, assignment: Assignment) -> str:
    """The organisation a quote is sent by: never the name of the software."""
    # What the beheerder set under Beheer goes first; the environment is
    # only its starting value.
    from grip.services import quote_sender

    stored = (await quote_sender.current_sender(session))["organisation"]
    if stored:
        return stored
    settings = get_settings()
    if settings.ORGANISATION_NAME.strip():
        return settings.ORGANISATION_NAME.strip()
    if assignment.contractor_organisation_id is not None:
        contractor = await session.get(
            Organisation, assignment.contractor_organisation_id
        )
        if contractor is not None:
            return contractor.name
    return settings.INSTANCE_NAME


async def build_snapshot(
    session: AsyncSession,
    assignment: Assignment,
    *,
    valid_until: date | None = None,
    conditions: str | None = None,
    reference: str | None = None,
    client_reference: str | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
    letter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The content of a quote as it would be issued now.

    Lines, rates and totals come from the budget of the assignment through
    the calculation module, so a quote adds up to the budget.
    """
    budget_lines = await AssignmentRepository(session).budget_lines([assignment.id])
    if not budget_lines:
        raise DomainValidationError(
            "Een offerte heeft minstens een begrotingsregel nodig."
        )
    # From here on only the columns a quote may be built from exist: the
    # builder never holds a budget line (grip.services.quote_content).
    lines = [line_source(line) for line in budget_lines]
    rates = await load_rate_book(session, include_draft=options.include_draft)
    snapshot: dict[str, Any] = {
        "name": assignment.name,
        "context_refs": list(assignment.context_refs or []),
        **budget_part(lines, rates, options),
    }
    if valid_until is not None:
        snapshot["valid_until"] = valid_until.isoformat()
    if conditions:
        snapshot["conditions"] = conditions
    snapshot["sender"] = await sender_name(session, assignment)
    # A preview has no reference yet: it is given out when the quote is issued.
    if reference:
        snapshot["reference"] = reference
    if client_reference and client_reference.strip():
        snapshot["client_reference"] = client_reference.strip()
    # The words of the quote, from the draft of the assignment. Part of the
    # content, so part of what is hashed and signed.
    if letter is not None:
        snapshot["letter"] = letter
    return check_content(snapshot)


def read_total(canonical: bytes) -> int:
    """The total of a quote in cents, read from its canonical form."""
    return int(read(canonical)["total"]["amount_cents"])


async def get_quote(session: AsyncSession, quote_id: UUID) -> Quote:
    quote = await session.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    return quote


def _instant(moment: datetime) -> datetime:
    """A moment given without a zone, read as ``clock.local_date`` reads it."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=clock.zone())


def check_signing_day(quote: Quote, signed_at: datetime) -> None:
    """Refuse a day of signing that cannot be true: after today, or before the
    day the quote was made.

    Compared as instants: a moment at the far end of the calendar does not
    survive ``clock.local_date``.
    """
    moment = _instant(signed_at)
    if moment >= _start_of(clock.today() + timedelta(days=1)):
        raise DomainValidationError(
            "Deze datum ligt in de toekomst. Kies de datum van tekenen."
        )
    if moment < _start_of(clock.local_date(quote.issued_at)):
        raise DomainValidationError(
            "Deze datum ligt voor de dag waarop de offerte is gemaakt. "
            "Kies de datum van tekenen."
        )


async def _open_quotes(session: AsyncSession, assignment_id: UUID) -> list[UUID]:
    """The quotes a new quote for this assignment replaces."""
    result = await session.execute(
        select(Quote.id).where(
            Quote.assignment_id == assignment_id, Quote.status == "issued"
        )
    )
    return list(result.scalars())


async def issue_quote(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    actor: Person | None,
    valid_until: date | None = None,
    conditions: str | None = None,
    request_id: UUID | None = None,
    issued_at: datetime | None = None,
    client_reference: str | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> Quote:
    """Issue a quote for an assignment: freeze the budget as it is now.

    An earlier quote that is still open is superseded. The assignment moves
    to status quoted. Emits ``quote.issued``.

    Issuing sends nothing to anyone. The quote reaches the client when it is
    offered, through a channel chosen then (``offer_quote``).
    """
    assignment = await get_assignment(session, assignment_id)
    # Asked again under the lock on the stream once the file is laid out:
    # laying it out under that lock would keep everyone else from writing.
    if await dossier_closed(session, assignment.id):
        raise DossierClosedError()
    if assignment.status not in ("draft", "requested", "quoted", "rejected"):
        raise DomainValidationError(
            f"Voor een opdracht met status '{assignment.status}' kan geen offerte "
            "meer worden gemaakt."
        )
    issued_at = _instant(issued_at or clock.now())
    # The text of the quote, when the assignment has a draft. Checked here
    # in full: a drafted section nobody settled, an empty section or the
    # name of a colleague in the text stops the making.
    from grip.services import quote_drafts

    frozen = await quote_drafts.frozen_letter(session, assignment, strict=True)
    letter = frozen.letter if frozen is not None else None
    # Build once without a reference first: a quote that cannot be built
    # (no lines, no rate card) must not use up a number.
    await build_snapshot(
        session,
        assignment,
        valid_until=valid_until,
        conditions=conditions,
        client_reference=client_reference,
        options=options,
        letter=letter,
    )
    # The reference is given out inside this transaction and becomes part of
    # the frozen content, so it is covered by the hash.
    reference = await next_reference(session, clock.local_date(issued_at).year)
    snapshot = await build_snapshot(
        session,
        assignment,
        valid_until=valid_until,
        conditions=conditions,
        reference=reference,
        client_reference=client_reference,
        options=options,
        letter=letter,
    )
    quote_id = uuid.uuid4()
    uri = mint_uri("offerte", quote_id)
    # The one moment the canonical form is made. From here on the bytes are
    # the quote; the working data they were built from may change freely.
    canonical = canonical_form(snapshot)
    quote_hash = hash_of(canonical)
    # The quote is also a file. It is laid out here, once, and kept: what a
    # client later reads and signs are these bytes, whatever the letterhead
    # or the template has become by then. If the file cannot be made, the
    # quote is not made (the error undoes the transaction).
    from grip.services import quote_files

    document = await quote_files.lay_out(
        session,
        quote_files.QuoteSource(
            id=quote_id,
            uri=uri,
            assignment_id=assignment_id,
            snapshot_hash=quote_hash,
            issued_at=issued_at,
            reference=reference,
            snapshot=read(canonical),
        ),
        quote_files.ORIGIN_ISSUE,
        issued_at,
    )
    await ensure_dossier_open(session, assignment.id)
    old_status = assignment.status
    moves = old_status != "quoted"
    if moves:
        await check_transition(session, assignment, "quoted", None)
    budget_lines = await AssignmentRepository(session).budget_lines([assignment_id])
    rates = await load_rate_book(session, include_draft=options.include_draft)
    established = await establish(
        session,
        "quote_issued",
        assignment_id=assignment_id,
        actor=actor,
        effective_on=clock.local_date(issued_at),
        basis={
            "rate_cards": _cards_touched(
                [line_source(line) for line in budget_lines], rates
            )
        },
        refs={
            "quote_hash": quote_hash,
            "document_sha256": document["document_sha256"],
        },
        fields={
            "quote": row_of(
                Quote,
                id=quote_id,
                uri=uri,
                reference=reference,
                assignment_id=assignment_id,
                request_id=request_id,
                status="issued",
                canonical=canonical,
                snapshot_hash=quote_hash,
                total_cents=snapshot["total"]["amount_cents"],
                issued_at=issued_at,
                issued_by_id=actor.id if actor is not None else None,
                prose_provenance=frozen.provenance if frozen is not None else None,
                **document,
            ),
            "supersedes": await _open_quotes(session, assignment_id),
            "assignment": changes_of(
                Assignment,
                quote_date=clock.local_date(issued_at),
                **({"status": "quoted"} if moves else {}),
            ),
        },
    )
    quote: Quote = established.row(QUOTE, quote_id)
    if moves:
        await after_transition(
            session, assignment, old_status, "quoted", None, actor, "local"
        )
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="quote",
        entity_id=quote.id,
        new_value={
            "assignment_id": str(assignment_id),
            "snapshot_hash": quote.snapshot_hash,
            "total_cents": quote.total_cents,
            "reference": reference,
            "document_sha256": quote.document_sha256,
        },
    )
    await events.emit(
        session,
        events.QUOTE_ISSUED,
        {
            "quote_id": str(quote.id),
            "quote_uri": quote.uri,
            "quote_reference": reference,
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "request_id": str(request_id) if request_id else None,
            "parent_assignment_uri": assignment.parent_assignment_uri,
            "snapshot": snapshot,
            "snapshot_hash": quote.snapshot_hash,
            "issued_at": issued_at.isoformat(),
            "origin": "local",
        },
    )
    return quote


async def receive_quote(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    quote_id: UUID,
    uri: str,
    claimed_hash: str,
    issued_at: datetime,
    canonical: bytes | None = None,
    snapshot: dict[str, Any] | None = None,
    request_id: UUID | None = None,
    received: Mapping[str, Any] | None = None,
) -> Quote:
    """Client side: record a quote that came in from a contractor.

    ``canonical`` is the canonical form as it was received; it is stored
    unchanged, so both sides hold the same bytes. The stated hash must be
    the hash of those bytes, otherwise the quote is refused. Idempotent on
    the quote id.

    A caller on this side that has the content in code names (a quote typed
    over from paper, a test) passes ``snapshot`` instead; the canonical form
    is then made here, as at issue.

    ``received`` names the peer, its message and the organisation that sent it
    when the quote came in from another instance.
    """
    existing = await session.get(Quote, quote_id)
    if existing is not None:
        return existing
    if canonical is None:
        if snapshot is None:
            raise DomainValidationError("Een ontvangen offerte heeft inhoud nodig.")
        canonical = canonical_form(snapshot)
    if hash_of(canonical) != claimed_hash:
        raise QuoteHashMismatchError()
    try:
        total_cents = int(read_total(canonical))
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainValidationError(
            "De ontvangen offerte heeft geen leesbaar totaal."
        ) from exc
    assignment = await get_assignment(session, assignment_id)
    await ensure_dossier_open(session, assignment.id)
    issued_at = _instant(issued_at)
    old_status = assignment.status
    moves = old_status != "quoted"
    if moves:
        await check_transition(session, assignment, "quoted", None)
    # The issuing instance's reference, when its quote carries one.
    received_reference = read(canonical).get("reference")
    fields: dict[str, Any] = {
        "quote": row_of(
            Quote,
            id=quote_id,
            uri=uri,
            reference=received_reference
            if isinstance(received_reference, str)
            else None,
            assignment_id=assignment_id,
            request_id=request_id,
            status="issued",
            canonical=canonical,
            snapshot_hash=claimed_hash,
            total_cents=total_cents,
            issued_at=issued_at,
            issued_by_id=None,
        ),
        "supersedes": await _open_quotes(session, assignment_id),
        "assignment": changes_of(
            Assignment,
            quote_date=clock.local_date(issued_at),
            **({"status": "quoted"} if moves else {}),
        ),
    }
    if received is not None:
        fields["received"] = received
    established = await establish(
        session,
        "quote_received",
        assignment_id=assignment_id,
        effective_on=clock.local_date(issued_at),
        refs={"quote_hash": claimed_hash},
        fields=fields,
    )
    if moves:
        await after_transition(
            session, assignment, old_status, "quoted", None, None, "remote"
        )
    quote: Quote = established.row(QUOTE, quote_id)
    return quote


# How long a signing link works when nobody says otherwise.
INVITATION_DAYS = 30


def default_invitation_expiry(now: datetime | None = None) -> datetime:
    return (now or clock.now()) + timedelta(days=INVITATION_DAYS)


async def get_invitation(
    session: AsyncSession, quote_id: UUID, invitation_id: UUID
) -> QuoteInvitation:
    invitation = await session.get(QuoteInvitation, invitation_id)
    if invitation is None or invitation.quote_id != quote_id:
        raise NotFoundError("Uitnodiging", invitation_id)
    return invitation


async def withdraw_invitation(
    session: AsyncSession, quote_id: UUID, invitation_id: UUID, *, actor: Person | None
) -> QuoteInvitation:
    """Take a signing link back: from now on it opens nothing."""
    invitation = await get_invitation(session, quote_id, invitation_id)
    if invitation.used_at is not None:
        raise DomainValidationError(
            "Met deze tekenlink is al getekend; intrekken kan niet meer."
        )
    if invitation.withdrawn_at is None:
        quote = await get_quote(session, quote_id)
        await ensure_dossier_open(session, quote.assignment_id)
        await establish(
            session,
            "invitation_withdrawn",
            assignment_id=quote.assignment_id,
            actor=actor,
            fields={
                "invitation_id": invitation.id,
                "withdrawn_at": clock.now(),
                "withdrawn_by_id": actor.id if actor is not None else None,
            },
        )
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="quote_invitation",
            entity_id=invitation.id,
            old_value={"withdrawn": False},
            new_value={"withdrawn": True},
        )
    return invitation


async def renew_invitation(
    session: AsyncSession, quote_id: UUID, invitation_id: UUID, *, actor: Person | None
) -> QuoteInvitation:
    """Make a signing link work again for the standard period from now."""
    invitation = await get_invitation(session, quote_id, invitation_id)
    quote = await get_quote(session, quote_id)
    await ensure_dossier_open(session, quote.assignment_id)
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    await _renew(session, quote, invitation, default_invitation_expiry(), actor)
    return invitation


async def _renew(
    session: AsyncSession,
    quote: Quote,
    invitation: QuoteInvitation,
    expires_at: datetime,
    actor: Person | None,
) -> None:
    old = invitation.expires_at
    await establish(
        session,
        "invitation_renewed",
        assignment_id=quote.assignment_id,
        actor=actor,
        fields={"invitation_id": invitation.id, "expires_at": expires_at},
    )
    _audit_renewal(session, invitation, old, expires_at, actor)


def _audit_renewal(
    session: AsyncSession,
    invitation: QuoteInvitation,
    old: datetime | None,
    expires_at: datetime,
    actor: Person | None,
) -> None:
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="quote_invitation",
        entity_id=invitation.id,
        old_value={"expires_at": old.isoformat() if old else None},
        new_value={"expires_at": expires_at.isoformat()},
    )


async def mark_invitation_opened(
    session: AsyncSession, quote_id: UUID, email: str
) -> None:
    """Remember the first time the invited person opened the quote."""
    result = await session.execute(
        select(QuoteInvitation).where(
            QuoteInvitation.quote_id == quote_id,
            func.lower(QuoteInvitation.email) == email.strip().lower(),
            QuoteInvitation.opened_at.is_(None),
            QuoteInvitation.withdrawn_at.is_(None),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is not None:
        # Two openings at once both get past the question above: ask it again
        # once whatever was recorded earlier is committed.
        await stream.hold_head(session)
        await session.refresh(invitation)
        if invitation.opened_at is not None or invitation.withdrawn_at is not None:
            return
        quote = await get_quote(session, quote_id)
        if await dossier_closed(session, quote.assignment_id):
            return
        opened_at = clock.now()
        await establish(
            session,
            "invitation_opened",
            assignment_id=quote.assignment_id,
            fields={"invitation_id": invitation.id, "opened_at": opened_at},
        )
        # The actor is the guest who opened it (grip.events.context).
        record_audit(
            session,
            actor=None,
            action=UPDATE,
            entity="quote_invitation",
            entity_id=invitation.id,
            old_value={"opened_at": None},
            new_value={"opened_at": opened_at.isoformat()},
        )


async def invitations_by_id(
    session: AsyncSession, invitation_ids: set[UUID]
) -> dict[UUID, QuoteInvitation]:
    if not invitation_ids:
        return {}
    result = await session.execute(
        select(QuoteInvitation).where(QuoteInvitation.id.in_(invitation_ids))
    )
    return {invitation.id: invitation for invitation in result.scalars()}


async def invite_signer(
    session: AsyncSession,
    quote_id: UUID,
    email: str,
    *,
    actor: Person | None,
    expires_at: datetime | None = None,
) -> QuoteInvitation:
    """Invite someone at the client to sign a quote through a signing link.

    The invited person logs in with SSO Rijk and sees only this quote.
    """
    quote = await get_quote(session, quote_id)
    await ensure_dossier_open(session, quote.assignment_id)
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    # Inviting a signer is offering the quote; a quote that still needs
    # internal approval cannot be offered through any channel.
    await quote_approval.require_for_offer(session, quote)
    email = email.strip().lower()
    invitation = await _invitation_for(session, quote_id, email)
    expires_at = _instant(expires_at or default_invitation_expiry())
    if invitation is not None:
        # Inviting the same person again renews the invitation, also after
        # it was withdrawn.
        await _renew(session, quote, invitation, expires_at, actor)
        return invitation
    # Inviting someone to sign here is offering the quote through the
    # signing link.
    _, invitation = await _offer_with_new_invitation(
        session, quote, email, expires_at, actor
    )
    return invitation


async def _invitation_for(
    session: AsyncSession, quote_id: UUID, email: str
) -> QuoteInvitation | None:
    result = await session.execute(
        select(QuoteInvitation).where(
            QuoteInvitation.quote_id == quote_id,
            func.lower(QuoteInvitation.email) == email,
        )
    )
    return result.scalar_one_or_none()


async def _offer_with_new_invitation(
    session: AsyncSession,
    quote: Quote,
    email: str,
    expires_at: datetime,
    actor: Person | None,
) -> tuple[QuoteOffer, QuoteInvitation]:
    invitation_id = uuid.uuid4()
    established, offer = await _establish_offer(
        session,
        quote,
        OFFER_SIGNING_LINK,
        actor=actor,
        recipient=email,
        invitation_id=invitation_id,
        invitation=row_of(
            QuoteInvitation,
            id=invitation_id,
            quote_id=quote.id,
            email=email,
            invited_by_id=actor.id if actor is not None else None,
            expires_at=expires_at,
        ),
    )
    invitation: QuoteInvitation = established.row(INVITATION, invitation_id)
    _audit_offer(session, quote, offer, actor)
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="quote_invitation",
        entity_id=invitation.id,
        new_value={"quote_id": str(quote.id), "email": email},
    )
    return offer, invitation


# -- offering -----------------------------------------------------------------


async def _establish_offer(
    session: AsyncSession,
    quote: Quote,
    channel: str,
    *,
    actor: Person | None,
    recipient: str | None = None,
    invitation_id: UUID | None = None,
    invitation: dict[str, Any] | None = None,
    renewed: dict[str, Any] | None = None,
    shared: dict[str, Any] | None = None,
) -> tuple[Established, QuoteOffer]:
    """One offer as one fact, with what arose together with it."""
    offer_id = uuid.uuid4()
    established = await establish(
        session,
        "quote_offered",
        assignment_id=quote.assignment_id,
        actor=actor,
        fields={
            "assignment_id": quote.assignment_id,
            "offer": row_of(
                QuoteOffer,
                id=offer_id,
                quote_id=quote.id,
                channel=channel,
                recipient=recipient,
                invitation_id=invitation_id,
                offered_at=clock.now(),
                offered_by_id=actor.id if actor is not None else None,
            ),
            "invitation": invitation,
            "renewed": renewed,
            "shared": shared,
        },
    )
    return established, established.row(OFFER, offer_id)


def _audit_offer(
    session: AsyncSession, quote: Quote, offer: QuoteOffer, actor: Person | None
) -> None:
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="quote_offer",
        entity_id=offer.id,
        new_value={
            "quote_id": str(quote.id),
            "channel": offer.channel,
            "recipient": offer.recipient,
        },
    )


async def offers_of(session: AsyncSession, quote_id: UUID) -> list[QuoteOffer]:
    """Every time this quote was offered, oldest first."""
    result = await session.execute(
        select(QuoteOffer)
        .where(QuoteOffer.quote_id == quote_id)
        .order_by(QuoteOffer.offered_at, QuoteOffer.created_at)
    )
    return list(result.scalars())


async def _client_instance_uri(
    session: AsyncSession, assignment: Assignment
) -> tuple[bool, str | None]:
    """Whether the assignment has a client, and the client's instance if known."""
    if assignment.client_organisation_id is None:
        return False, None
    client = await session.get(Organisation, assignment.client_organisation_id)
    return client is not None, client.instance_uri if client is not None else None


async def channel_options(
    session: AsyncSession, quote_id: UUID
) -> list[quote_channels.ChannelOption]:
    """The channels this quote can be offered through, and why one cannot.

    A quote that was decided on, or replaced by a newer one, can no longer
    be offered at all. For an assignment that is already shared with the
    client's instance, that channel is the suggestion; it is never forced.
    """
    quote = await get_quote(session, quote_id)
    assignment = await get_assignment(session, quote.assignment_id)
    closed = None
    if quote.status != "issued":
        closed = "Over deze offerte is al beslist, of er is een nieuwere gemaakt."
    has_client, instance_uri = await _client_instance_uri(session, assignment)
    federated = closed or await quote_channels.client_instance_unavailable(
        session, instance_uri, has_client=has_client
    )
    shared = bool(assignment.shared_with_instance_uri) and federated is None
    return [
        quote_channels.ChannelOption(
            OFFER_CLIENT_INSTANCE, federated is None, federated, suggested=shared
        ),
        quote_channels.ChannelOption(
            OFFER_SIGNING_LINK, closed is None, closed, suggested=False
        ),
        quote_channels.ChannelOption(
            OFFER_DOCUMENT,
            closed is None,
            closed,
            suggested=not shared and closed is None,
        ),
    ]


async def offer_quote(
    session: AsyncSession,
    quote_id: UUID,
    channel: str,
    *,
    actor: Person | None,
    email: str | None = None,
    expires_at: datetime | None = None,
) -> QuoteOffer:
    """Put an issued quote before the client, through one channel.

    Issuing a quote freezes it and sends nothing. This is the act that makes
    it reach the client:

    - ``client_instance``: to the client's own grip instance. Possible only
      when that instance is connected. The assignment is from then on shared
      with that instance. Emits ``quote.offered``.
    - ``signing_link``: ``email`` is invited to sign in this instance.
    - ``document``: the quote goes out as a document; the signed copy is
      recorded later as an acceptance.

    A quote may be offered more than once and through more than one channel.
    One decision closes it, whichever channel it came through.
    """
    if channel not in OFFER_CHANNELS:
        raise DomainValidationError(f"Onbekend kanaal: {channel}")
    quote = await get_quote(session, quote_id)
    await ensure_dossier_open(session, quote.assignment_id)
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    assignment = await get_assignment(session, quote.assignment_id)
    await quote_approval.require_for_offer(session, quote)

    if channel == OFFER_SIGNING_LINK:
        if not email or not email.strip():
            raise DomainValidationError(
                "Voor een tekenlink is het e-mailadres van de ondertekenaar nodig."
            )
        # Imported here: the mail service reads names through this module.
        from grip.services import signing_mail

        address = email.strip().lower()
        until = _instant(expires_at or default_invitation_expiry())
        invitation = await _invitation_for(session, quote_id, address)
        if invitation is None:
            offer, invitation = await _offer_with_new_invitation(
                session, quote, address, until, actor
            )
        else:
            # The same person was invited before: offering again renews the
            # invitation and is a new offer on it.
            old_expiry = invitation.expires_at
            _, offer = await _establish_offer(
                session,
                quote,
                OFFER_SIGNING_LINK,
                actor=actor,
                recipient=invitation.email,
                invitation_id=invitation.id,
                renewed={"invitation_id": invitation.id, "expires_at": until},
            )
            _audit_renewal(session, invitation, old_expiry, until, actor)
            _audit_offer(session, quote, offer, actor)
        # The link goes to the invited address by mail, queued with this
        # offer; where the instance does not mail, whoever offers hands the
        # link over.
        await signing_mail.queue(
            session, quote, invitation, actor=actor, occasion=f"offer:{offer.id}"
        )
        return offer

    if channel == OFFER_DOCUMENT:
        _, offer = await _establish_offer(session, quote, OFFER_DOCUMENT, actor=actor)
        _audit_offer(session, quote, offer, actor)
        return offer

    has_client, instance_uri = await _client_instance_uri(session, assignment)
    reason = await quote_channels.client_instance_unavailable(
        session, instance_uri, has_client=has_client
    )
    if reason is not None:
        raise DomainValidationError(reason)
    assert instance_uri is not None
    recipient = instance_uri.strip().rstrip("/")
    _, offer = await _establish_offer(
        session,
        quote,
        OFFER_CLIENT_INSTANCE,
        actor=actor,
        recipient=recipient,
        # Sharing once is enough; a later offer leaves the moment as it was.
        shared=None
        if is_shared_with(assignment, instance_uri)
        else {"shared_with_instance_uri": recipient, "shared_at": clock.now()},
    )
    _audit_offer(session, quote, offer, actor)
    await events.emit(
        session,
        events.QUOTE_OFFERED,
        {
            "offer_id": str(offer.id),
            "channel": channel,
            "quote_id": str(quote.id),
            "quote_uri": quote.uri,
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "request_id": str(quote.request_id) if quote.request_id else None,
            "snapshot_hash": quote.snapshot_hash,
            "issued_at": quote.issued_at.isoformat(),
            "recipient_instance_uri": offer.recipient,
            "origin": "local",
        },
    )
    return offer


async def _open_invitation(
    session: AsyncSession, quote_id: UUID, email: str, at: datetime
) -> QuoteInvitation:
    result = await session.execute(
        select(QuoteInvitation).where(
            QuoteInvitation.quote_id == quote_id,
            func.lower(QuoteInvitation.email) == email.strip().lower(),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise DomainValidationError(
            "Voor dit e-mailadres is geen uitnodiging om deze offerte te tekenen."
        )
    if invitation.withdrawn_at is not None:
        raise DomainValidationError("De uitnodiging om te tekenen is ingetrokken.")
    if invitation.expires_at is not None and invitation.expires_at < at:
        raise DomainValidationError("De uitnodiging om te tekenen is verlopen.")
    return invitation


def _evidence(
    quote_hash: str, statement_hash: str | None, document_sha256: str | None = None
) -> dict[str, str]:
    """The hashes a decision on a quote rests on, for the chain to cover."""
    return {
        "quote_hash": quote_hash,
        **({"statement_hash": statement_hash} if statement_hash else {}),
        **({"document_sha256": document_sha256} if document_sha256 else {}),
    }


async def accept_quote(
    session: AsyncSession,
    quote_id: UUID,
    *,
    quote_hash: str,
    signer_name: str,
    signer_email: str,
    organisation: dict[str, Any],
    form: str,
    actor: Person | None = None,
    signer_function: str | None = None,
    signer_person_id: UUID | None = None,
    signed_at: datetime | None = None,
    jws: str | None = None,
    document_sha256: str | None = None,
    document_ref: str | None = None,
    acceptance_id: UUID | None = None,
    origin: str = "local",
    evidence_id: UUID | None = None,
    statement_hash: str | None = None,
    received: Mapping[str, Any] | None = None,
    declared_mandate: bool = False,
) -> QuoteAcceptance:
    """Record that the client accepted a quote, in one of the three forms.

    - ``own_instance``: signed in the client's own instance; needs the JWS.
    - ``signing_link``: signed here by an invited guest; needs an invitation
      for ``signer_email``.
    - ``uploaded_pdf``: the signed document, recorded by ``actor``; needs the
      SHA-256 of the document.

    The hash must be that of the issued quote. Idempotent on
    ``acceptance_id``. The assignment moves to status accepted. Emits
    ``quote.accepted``; ``origin`` tells a handler whether the acceptance
    was made here ("local") or came in from another instance ("remote").

    ``evidence_id`` and ``statement_hash`` name the statement this acceptance
    was made from (see ``grip.proof``): the values passed here were read from
    it. The hash goes into the audit row and the event, so both can point at
    the proof; the statement itself does not.

    ``received`` names the peer and its message when the acceptance came in
    from another instance. ``declared_mandate``: the signer of a signing link
    confirmed being allowed to sign.
    """
    if form not in ACCEPTANCE_FORMS:
        raise DomainValidationError(f"Onbekende vorm van akkoord: {form}")
    if acceptance_id is not None:
        existing = await session.get(QuoteAcceptance, acceptance_id)
        if existing is not None:
            if existing.quote_id != quote_id or existing.quote_hash != quote_hash:
                raise DomainValidationError(
                    "Dit akkoord is al vastgelegd met een andere inhoud."
                )
            return existing
    quote = await get_quote(session, quote_id)
    await ensure_dossier_open(session, quote.assignment_id)
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    if quote_hash != quote.snapshot_hash:
        raise QuoteHashMismatchError()
    signed_at = _instant(signed_at or clock.now())

    if form == "own_instance" and not jws:
        raise DomainValidationError(
            "Een akkoord uit de eigen instantie van de opdrachtgever heeft een "
            "handtekening nodig."
        )
    if form == "uploaded_pdf":
        if not document_sha256:
            raise DomainValidationError(
                "Bij een getekende pdf hoort de hash van het document."
            )
        if actor is None:
            raise DomainValidationError(
                "Een getekende pdf wordt vastgelegd door een medewerker."
            )
    invitation = None
    if form == "signing_link":
        invitation = await _open_invitation(session, quote_id, signer_email, signed_at)

    assignment = await get_assignment(session, quote.assignment_id)
    await check_transition(session, assignment, "accepted", None)
    old_status = assignment.status
    acceptance_id = acceptance_id or uuid.uuid4()
    assignment_changes: dict[str, Any] = {"status": "accepted"}
    if assignment.quoted_amount_cents is None:
        assignment_changes["quoted_amount_cents"] = quote.total_cents
    fields: dict[str, Any] = {
        "assignment_id": assignment.id,
        "quote_id": quote_id,
        "acceptance": row_of(
            QuoteAcceptance,
            id=acceptance_id,
            quote_id=quote_id,
            quote_hash=quote_hash,
            signer_name=signer_name,
            signer_email=signer_email.strip().lower(),
            signer_function=signer_function,
            signer_person_id=signer_person_id,
            organisation=organisation,
            signed_at=signed_at,
            form=form,
            jws=jws,
            document_sha256=document_sha256,
            document_ref=document_ref,
            recorded_by_id=actor.id if actor is not None else None,
            evidence_id=evidence_id,
        ),
        "assignment": changes_of(Assignment, **assignment_changes),
        "invitation": None
        if invitation is None
        else {
            "id": invitation.id,
            "used_at": signed_at,
            "person_id": signer_person_id,
        },
    }
    if received is not None:
        fields["received"] = received
    if declared_mandate:
        fields["declared_mandate"] = True
    established = await establish(
        session,
        "quote_accepted",
        assignment_id=assignment.id,
        actor=actor,
        effective_on=clock.local_date(signed_at),
        refs=_evidence(quote_hash, statement_hash, document_sha256),
        fields=fields,
    )
    acceptance: QuoteAcceptance = established.row(ACCEPTANCE, acceptance_id)
    if invitation is not None:
        record_audit(
            session,
            actor=None,
            action=UPDATE,
            entity="quote_invitation",
            entity_id=invitation.id,
            old_value={"used_at": None},
            new_value={"used_at": signed_at.isoformat()},
        )
    await after_transition(
        session, assignment, old_status, "accepted", None, actor, origin
    )
    # Within one flush the stream numbers audit rows first; this keeps the event
    # of the step ahead of the audit row of the acceptance.
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="quote_acceptance",
        entity_id=acceptance.id,
        new_value={
            "quote_id": str(quote_id),
            "quote_hash": quote_hash,
            "form": form,
            "signed_at": signed_at.isoformat(),
            **({"statement_hash": statement_hash} if statement_hash else {}),
        },
    )
    await events.emit(
        session,
        events.QUOTE_ACCEPTED,
        {
            "acceptance_id": str(acceptance.id),
            "quote_id": str(quote.id),
            "quote_uri": quote.uri,
            "quote_hash": quote_hash,
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "signer": {
                "name": signer_name,
                "email": acceptance.signer_email,
                **({"function": signer_function} if signer_function else {}),
            },
            "organisation": organisation,
            "signed_at": signed_at.isoformat(),
            "form": form,
            "jws": jws,
            "document_sha256": document_sha256,
            "origin": origin,
            # Refers to the statement of this decision; never its content.
            "statement_hash": statement_hash,
        },
    )
    return acceptance


async def reject_quote(
    session: AsyncSession,
    quote_id: UUID,
    *,
    quote_hash: str,
    actor: Person | None = None,
    reason: str | None = None,
    organisation: dict[str, Any] | None = None,
    rejected_at: datetime | None = None,
    rejection_id: UUID | None = None,
    origin: str = "local",
    evidence_id: UUID | None = None,
    statement_hash: str | None = None,
    received: Mapping[str, Any] | None = None,
    recorded: bool = False,
) -> QuoteRejection:
    """Record that the client rejected a quote. Emits ``quote.rejected``.

    ``evidence_id`` and ``statement_hash`` name the statement this rejection
    was made from, as for an acceptance, and ``received`` the peer and its
    message when the rejection came in from another instance. ``recorded``:
    ``actor`` notes a rejection made elsewhere, and does not reject it.
    """
    if rejection_id is not None:
        existing = await session.get(QuoteRejection, rejection_id)
        if existing is not None:
            if existing.quote_id != quote_id or existing.quote_hash != quote_hash:
                raise DomainValidationError(
                    "Deze afwijzing is al vastgelegd met een andere inhoud."
                )
            return existing
    quote = await get_quote(session, quote_id)
    await ensure_dossier_open(session, quote.assignment_id)
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    if quote_hash != quote.snapshot_hash:
        raise QuoteHashMismatchError()
    rejected_at = _instant(rejected_at or clock.now())
    assignment = await get_assignment(session, quote.assignment_id)
    await check_transition(session, assignment, "rejected", reason)
    old_status = assignment.status
    rejection_id = rejection_id or uuid.uuid4()
    fields: dict[str, Any] = {
        "assignment_id": assignment.id,
        "quote_id": quote_id,
        "rejection": row_of(
            QuoteRejection,
            id=rejection_id,
            quote_id=quote_id,
            quote_hash=quote_hash,
            organisation=organisation,
            reason=reason,
            rejected_at=rejected_at,
            recorded_by_id=actor.id if recorded and actor is not None else None,
            evidence_id=evidence_id,
        ),
        "assignment": changes_of(Assignment, status="rejected"),
    }
    if received is not None:
        fields["received"] = received
    established = await establish(
        session,
        "quote_rejected",
        assignment_id=assignment.id,
        actor=actor,
        effective_on=clock.local_date(rejected_at),
        refs=_evidence(quote_hash, statement_hash),
        fields=fields,
    )
    rejection: QuoteRejection = established.row(REJECTION, rejection_id)
    await after_transition(
        session, assignment, old_status, "rejected", reason, actor, origin
    )
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="quote",
        entity_id=quote.id,
        old_value={"status": "issued"},
        new_value={
            "status": "rejected",
            "reason": reason,
            **({"statement_hash": statement_hash} if statement_hash else {}),
        },
    )
    await events.emit(
        session,
        events.QUOTE_REJECTED,
        {
            "rejection_id": str(rejection.id),
            "quote_id": str(quote.id),
            "quote_uri": quote.uri,
            "quote_hash": quote_hash,
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "organisation": organisation,
            "reason": reason,
            "rejected_at": rejected_at.isoformat(),
            "origin": origin,
            "statement_hash": statement_hash,
        },
    )
    return rejection


async def correct_acceptance_date(
    session: AsyncSession,
    quote_id: UUID,
    signed_at: datetime,
    reason: str,
    actor: Person | None,
    *,
    expected_signed_at: datetime | None = None,
) -> QuoteAcceptance:
    """Put right the day a signed pdf was signed, as whoever recorded it wrote it.

    Only for an uploaded pdf: every other form carries its moment in what was
    signed. The earlier fact stays; this one says it was corrected, and why.

    ``expected_signed_at`` is the date the form started from: when someone
    corrected it since, this correction is refused. Without it nothing is
    compared, as for a save without ``If-Match``.
    """
    quote = await get_quote(session, quote_id)
    await ensure_dossier_open(session, quote.assignment_id)
    acceptance = await session.scalar(
        select(QuoteAcceptance).where(QuoteAcceptance.quote_id == quote_id)
    )
    if acceptance is None:
        raise NotFoundError("Akkoord", quote_id)
    if acceptance.form != "uploaded_pdf":
        raise DomainValidationError(
            "Alleen de datum van een vastgelegde getekende pdf kan worden gecorrigeerd."
        )
    reason = (reason or "").strip()
    if not reason:
        raise DomainValidationError("Schrijf op waarom de datum wordt gecorrigeerd.")
    signed_at = _instant(signed_at)
    check_signing_day(quote, signed_at)
    # The fact says what stood before it: read once everything recorded earlier
    # is committed, not what this request saw when it started.
    await stream.hold_head(session)
    await session.refresh(acceptance)
    was = acceptance.signed_at
    if expected_signed_at is not None and _instant(expected_signed_at) != was:
        raise stale.StaleWriteError(
            "de datum van tekenen", *await stale.last_change(session, acceptance.id)
        )
    if clock.local_date(signed_at) == clock.local_date(was):
        raise DomainValidationError(
            "Dit is de datum die al is vastgelegd. Kies de juiste datum."
        )
    await establish(
        session,
        "acceptance_date_corrected",
        assignment_id=quote.assignment_id,
        actor=actor,
        effective_on=clock.local_date(signed_at),
        fields={
            "acceptance_id": acceptance.id,
            "signed_at": signed_at,
            "was": was,
            "reason": reason,
        },
    )
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="quote_acceptance",
        entity_id=acceptance.id,
        old_value={"signed_at": was.isoformat()},
        new_value={"signed_at": signed_at.isoformat(), "reason": reason},
    )
    return acceptance
