"""Quotes: issue a frozen snapshot, and record acceptance or rejection.

A quote is the one place where derived values are stored. The snapshot has
the shape of the contract (grip-opdrachtverkeer, quote.snapshot), so the same
object is hashed, stored, shown and sent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment, BudgetLine
from grip.models.person import Person
from grip.models.quote import (
    ACCEPTANCE_FORMS,
    Quote,
    QuoteAcceptance,
    QuoteInvitation,
    QuoteRejection,
)
from grip.repositories.domain import AssignmentRepository
from grip.services import events
from grip.services.assignments import get_assignment, mint_uri, transition
from grip.services.canonical import snapshot_hash
from grip.services.errors import (
    DomainValidationError,
    NotFoundError,
    QuoteAlreadyDecidedError,
    QuoteHashMismatchError,
)
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    load_rate_book,
    to_calc_line,
)

CURRENCY = "EUR"


def _money(cents: int) -> dict[str, Any]:
    return {"amount_cents": cents, "currency": CURRENCY}


def _decimal_text(value: Decimal) -> str:
    """Exact decimal as text, without exponent or trailing zeros."""
    text = format(Decimal(value).normalize(), "f")
    return text if text != "-0" else "0"


def _snapshot_line(
    line: BudgetLine, rates: calc.RateBook, options: PricingOptions
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
        entry["period"] = {
            "start_date": line.start_date.isoformat(),
            "end_date": line.end_date.isoformat(),
        }
        months = calc.budget_line_months(
            calc_line, rates, partial_months=options.partial_months
        )
        per_year: dict[int, int] = {}
        for month in months:
            per_year[month.month.year] = month.monthly_rate_cents
        if len(set(per_year.values())) == 1:
            entry["monthly_rate"] = _money(next(iter(per_year.values())))
        else:
            # The rate differs per year; the contract's single monthly_rate
            # cannot say that, so the rates are listed per year.
            entry["monthly_rates_per_year"] = [
                {"year": year, "monthly_rate": _money(cents)}
                for year, cents in sorted(per_year.items())
            ]
    else:
        entry["year"] = line.year
    entry["amount"] = _money(amount)
    return entry


async def build_snapshot(
    session: AsyncSession,
    assignment: Assignment,
    *,
    valid_until: date | None = None,
    conditions: str | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> dict[str, Any]:
    """The content of a quote as it would be issued now.

    Lines, rates and totals come from the budget of the assignment through
    the calculation module, so a quote adds up to the budget.
    """
    lines = await AssignmentRepository(session).budget_lines([assignment.id])
    if not lines:
        raise DomainValidationError(
            "Een offerte heeft minstens een begrotingsregel nodig."
        )
    rates = await load_rate_book(session, include_draft=options.include_draft)
    subtotals: dict[int, int] = {}
    for line in lines:
        for year, cents in calc.budgeted_by_year(
            to_calc_line(line), rates, partial_months=options.partial_months
        ).items():
            subtotals[year] = subtotals.get(year, 0) + cents
    snapshot: dict[str, Any] = {
        "name": assignment.name,
        "context_refs": list(assignment.context_refs or []),
        "lines": [_snapshot_line(line, rates, options) for line in lines],
        "subtotals_per_year": [
            {"year": year, "amount": _money(cents)}
            for year, cents in sorted(subtotals.items())
        ],
        "total": _money(sum(subtotals.values())),
    }
    if valid_until is not None:
        snapshot["valid_until"] = valid_until.isoformat()
    if conditions:
        snapshot["conditions"] = conditions
    return snapshot


async def get_quote(session: AsyncSession, quote_id: UUID) -> Quote:
    quote = await session.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    return quote


async def _supersede_open_quotes(session: AsyncSession, assignment_id: UUID) -> None:
    result = await session.execute(
        select(Quote).where(
            Quote.assignment_id == assignment_id, Quote.status == "issued"
        )
    )
    for quote in result.scalars():
        quote.status = "superseded"


async def issue_quote(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    actor: Person | None,
    valid_until: date | None = None,
    conditions: str | None = None,
    request_id: UUID | None = None,
    issued_at: datetime | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> Quote:
    """Issue a quote for an assignment: freeze the budget as it is now.

    An earlier quote that is still open is superseded. The assignment moves
    to status quoted. Emits ``quote.issued``.
    """
    assignment = await get_assignment(session, assignment_id)
    if assignment.status not in ("draft", "requested", "quoted", "rejected"):
        raise DomainValidationError(
            f"Voor een opdracht met status '{assignment.status}' kan geen offerte "
            "meer worden uitgegeven."
        )
    snapshot = await build_snapshot(
        session,
        assignment,
        valid_until=valid_until,
        conditions=conditions,
        options=options,
    )
    await _supersede_open_quotes(session, assignment_id)
    quote_id = uuid.uuid4()
    issued_at = issued_at or datetime.now(UTC)
    quote = Quote(
        id=quote_id,
        uri=mint_uri("offerte", quote_id),
        assignment_id=assignment_id,
        request_id=request_id,
        status="issued",
        snapshot=snapshot,
        snapshot_hash=snapshot_hash(snapshot),
        total_cents=snapshot["total"]["amount_cents"],
        issued_at=issued_at,
        issued_by_id=actor.id if actor is not None else None,
    )
    session.add(quote)
    assignment.quote_date = issued_at.date()
    await session.flush()
    if assignment.status != "quoted":
        await transition(session, assignment_id, "quoted", actor=actor)
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
        },
    )
    await events.emit(
        session,
        events.QUOTE_ISSUED,
        {
            "quote_id": str(quote.id),
            "quote_uri": quote.uri,
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
    snapshot: dict[str, Any],
    claimed_hash: str,
    issued_at: datetime,
    request_id: UUID | None = None,
) -> Quote:
    """Client side: record a quote that came in from a contractor.

    The hash is recomputed; a quote whose hash does not match its snapshot
    is refused. Idempotent on the quote id.
    """
    existing = await session.get(Quote, quote_id)
    if existing is not None:
        return existing
    if snapshot_hash(snapshot) != claimed_hash:
        raise QuoteHashMismatchError()
    assignment = await get_assignment(session, assignment_id)
    await _supersede_open_quotes(session, assignment_id)
    quote = Quote(
        id=quote_id,
        uri=uri,
        assignment_id=assignment_id,
        request_id=request_id,
        status="issued",
        snapshot=snapshot,
        snapshot_hash=claimed_hash,
        total_cents=snapshot["total"]["amount_cents"],
        issued_at=issued_at,
        issued_by_id=None,
    )
    session.add(quote)
    assignment.quote_date = issued_at.date()
    await session.flush()
    if assignment.status != "quoted":
        await transition(session, assignment_id, "quoted", actor=None, origin="remote")
    return quote


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
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    email = email.strip().lower()
    result = await session.execute(
        select(QuoteInvitation).where(
            QuoteInvitation.quote_id == quote_id,
            func.lower(QuoteInvitation.email) == email,
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is not None:
        invitation.expires_at = expires_at
        await session.flush()
        return invitation
    invitation = QuoteInvitation(
        quote_id=quote_id,
        email=email,
        invited_by_id=actor.id if actor is not None else None,
        expires_at=expires_at,
    )
    session.add(invitation)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="quote_invitation",
        entity_id=invitation.id,
        new_value={"quote_id": str(quote_id), "email": email},
    )
    return invitation


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
    if invitation.expires_at is not None and invitation.expires_at < at:
        raise DomainValidationError("De uitnodiging om te tekenen is verlopen.")
    return invitation


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
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    if quote_hash != quote.snapshot_hash:
        raise QuoteHashMismatchError()
    signed_at = signed_at or datetime.now(UTC)

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

    acceptance = QuoteAcceptance(
        id=acceptance_id or uuid.uuid4(),
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
    )
    session.add(acceptance)
    quote.status = "accepted"
    if invitation is not None:
        invitation.used_at = signed_at
        if signer_person_id is not None:
            invitation.person_id = signer_person_id
    await session.flush()
    assignment = await transition(
        session, quote.assignment_id, "accepted", actor=actor, origin=origin
    )
    if assignment.quoted_amount_cents is None:
        assignment.quoted_amount_cents = quote.total_cents
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
) -> QuoteRejection:
    """Record that the client rejected a quote. Emits ``quote.rejected``."""
    if rejection_id is not None:
        existing = await session.get(QuoteRejection, rejection_id)
        if existing is not None:
            if existing.quote_id != quote_id or existing.quote_hash != quote_hash:
                raise DomainValidationError(
                    "Deze afwijzing is al vastgelegd met een andere inhoud."
                )
            return existing
    quote = await get_quote(session, quote_id)
    if quote.status != "issued":
        raise QuoteAlreadyDecidedError(quote.status)
    if quote_hash != quote.snapshot_hash:
        raise QuoteHashMismatchError()
    rejected_at = rejected_at or datetime.now(UTC)
    rejection = QuoteRejection(
        id=rejection_id or uuid.uuid4(),
        quote_id=quote_id,
        quote_hash=quote_hash,
        organisation=organisation,
        reason=reason,
        rejected_at=rejected_at,
        recorded_by_id=actor.id if actor is not None else None,
    )
    session.add(rejection)
    quote.status = "rejected"
    await session.flush()
    assignment = await transition(
        session,
        quote.assignment_id,
        "rejected",
        actor=actor,
        reason=reason,
        origin=origin,
    )
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="quote",
        entity_id=quote.id,
        old_value={"status": "issued"},
        new_value={"status": "rejected", "reason": reason},
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
        },
    )
    return rejection
