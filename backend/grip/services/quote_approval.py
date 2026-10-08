"""Internal approval of a quote, before it may be offered to the client.

Optional per instance. Where the instance is set up for it, a made quote
needs the approval of someone inside the organisation who holds the right
to give it, before it can be offered through any channel.

- The beheerder sets when approval is needed: never (the default), always,
  or from an amount upward.
- The maker (owner or manager of the assignment) asks for approval, with an
  optional note. Someone with the right approves, or sends the quote back
  with a note.
- An approval is about exactly the bytes of the quote: it cites the hash.
  An approval that cites another hash approves nothing.
- Sending back does not change the quote, which is frozen. The maker makes
  a new quote; the old one is superseded and the reason stays on record.
- Whoever asked cannot approve the own request (four eyes), unless the
  instance allows it; the record and the audit row then say so.
- An approval can be withdrawn as long as the quote was not offered.

Internal approval is knowledge of this organisation, like a verbal
agreement. It is not part of the content of a quote, does not change the
status of the quote or the assignment as others see them, and none of its
events leads to a message to another instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.person import Person
from grip.models.quote import (
    APPROVAL_APPROVED,
    APPROVAL_REQUESTED,
    APPROVAL_SENT_BACK,
    APPROVAL_WITHDRAWN,
    Quote,
    QuoteApproval,
    QuoteOffer,
)
from grip.models.role import PersonRole
from grip.services import events, instance_settings
from grip.services.errors import DomainValidationError, NotFoundError

# The right to approve quotes internally. The user-facing word is "recht";
# in code a right is a function.
APPROVER_FUNCTION = "offertegoedkeurder"
APPROVER_LABEL = "Interne goedkeurder van offertes"

MODE_NEVER = "never"
MODE_ALWAYS = "always"
MODE_FROM_AMOUNT = "from_amount"

MODE = instance_settings.declare(
    "quote_approval.mode",
    MODE_NEVER,
    instance_settings.one_of(MODE_NEVER, MODE_ALWAYS, MODE_FROM_AMOUNT),
    "Wanneer een offerte intern moet worden goedgekeurd voor ze wordt "
    "aangeboden: nooit, altijd, of vanaf een bedrag.",
)
THRESHOLD = instance_settings.declare(
    "quote_approval.threshold_cents",
    0,
    instance_settings.whole_cents,
    "Het offertebedrag in centen vanaf waar interne goedkeuring nodig is.",
)
ALLOW_SELF = instance_settings.declare(
    "quote_approval.allow_self_approval",
    False,
    instance_settings.boolean,
    "Of wie de goedkeuring vroeg de eigen offerte ook mag goedkeuren.",
)

# Event types, announced through grip.services.events.
EVENT_REQUESTED = events.QUOTE_APPROVAL_REQUESTED
EVENT_APPROVED = events.QUOTE_APPROVAL_APPROVED
EVENT_SENT_BACK = events.QUOTE_APPROVAL_SENT_BACK
EVENT_WITHDRAWN = events.QUOTE_APPROVAL_WITHDRAWN

NO_APPROVER = (
    f"Niemand heeft het recht '{APPROVER_LABEL}'. De beheerder kent het toe "
    "bij Team, onder Rechten in grip van een persoon."
)


def _euro(cents: int) -> str:
    whole, fraction = divmod(abs(cents), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"€ {grouped}" if fraction == 0 else f"€ {grouped},{fraction:02d}"


@dataclass(frozen=True)
class Requirement:
    required: bool
    # Why approval is needed, in words for the screen; None when it is not.
    reason: str | None = None


@dataclass(frozen=True)
class ApprovalState:
    """Where a quote stands with internal approval."""

    requirement: Requirement
    # The request that is open or approved, if any.
    current: QuoteApproval | None
    # Every request for this quote, oldest first.
    history: tuple[QuoteApproval, ...]
    # Whether anyone holds the right to approve at all.
    approver_available: bool
    offered: bool
    # The hash of the quote this state is about.
    quote_hash: str = ""

    @property
    def approved(self) -> bool:
        return self.current is not None and self.current.status == APPROVAL_APPROVED

    @property
    def status(self) -> str:
        """none, requested, approved, sent_back or withdrawn.

        Only a request about the quote as it is now counts; one that cites
        another hash is history and says nothing about this quote.
        """
        if self.current is not None:
            return self.current.status
        for row in reversed(self.history):
            if row.quote_hash == self.quote_hash:
                return row.status
        return "none"

    @property
    def blocks_offering(self) -> bool:
        return self.requirement.required and not self.approved

    @property
    def blocked_message(self) -> str | None:
        """Why the quote cannot be offered yet, or None when it can."""
        if not self.blocks_offering:
            return None
        reason = self.requirement.reason or ""
        if self.status == APPROVAL_REQUESTED:
            text = (
                "Deze offerte wacht op interne goedkeuring en kan nog niet "
                f"worden aangeboden ({reason})."
            )
        elif self.status == APPROVAL_SENT_BACK:
            text = (
                "Deze offerte is intern teruggestuurd en kan niet worden "
                "aangeboden. Maak een nieuwe offerte en vraag daarvoor "
                "goedkeuring."
            )
        else:
            text = (
                "Deze offerte moet eerst intern worden goedgekeurd voor ze kan "
                f"worden aangeboden ({reason}). Vraag goedkeuring aan."
            )
        if not self.approver_available:
            text = f"{text} {NO_APPROVER}"
        return text


async def requirement_for(db: AsyncSession, quote: Quote) -> Requirement:
    """Whether this quote needs internal approval before it is offered."""
    mode = await instance_settings.get(db, MODE.key)
    if mode == MODE_ALWAYS:
        return Requirement(True, "elke offerte wordt intern goedgekeurd")
    if mode == MODE_FROM_AMOUNT:
        threshold = int(await instance_settings.get(db, THRESHOLD.key))
        if quote.total_cents >= threshold:
            return Requirement(True, f"vanaf {_euro(threshold)}")
    return Requirement(False)


async def approver_available(db: AsyncSession) -> bool:
    """Whether at least one active person holds the right to approve today."""
    # The same day a grant starts on (``team.grant_function``): the local
    # date. A UTC date lags behind it after midnight, and a right granted
    # then would not count until the UTC day turned.
    today = clock.today()
    count = await db.scalar(
        select(func.count())
        .select_from(PersonRole)
        .join(Person, Person.id == PersonRole.person_id)
        .where(
            Person.is_active.is_(True),
            PersonRole.role_id == APPROVER_FUNCTION,
            PersonRole.start_date <= today,
            (PersonRole.end_date.is_(None)) | (PersonRole.end_date >= today),
        )
    )
    return bool(count)


async def _history(db: AsyncSession, quote_id: UUID) -> list[QuoteApproval]:
    result = await db.execute(
        select(QuoteApproval)
        .where(QuoteApproval.quote_id == quote_id)
        .order_by(QuoteApproval.requested_at, QuoteApproval.created_at)
    )
    return list(result.scalars())


async def _offered(db: AsyncSession, quote_id: UUID) -> bool:
    count = await db.scalar(
        select(func.count())
        .select_from(QuoteOffer)
        .where(QuoteOffer.quote_id == quote_id)
    )
    return bool(count)


async def state_of(db: AsyncSession, quote: Quote) -> ApprovalState:
    history = await _history(db, quote.id)
    # A request counts only for the bytes it cites. One that cites another
    # hash approves nothing, whatever its status says.
    current = next(
        (
            row
            for row in reversed(history)
            if row.status in (APPROVAL_REQUESTED, APPROVAL_APPROVED)
            and row.quote_hash == quote.snapshot_hash
        ),
        None,
    )
    return ApprovalState(
        requirement=await requirement_for(db, quote),
        current=current,
        history=tuple(history),
        approver_available=await approver_available(db),
        offered=await _offered(db, quote.id),
        quote_hash=quote.snapshot_hash,
    )


async def require_for_offer(db: AsyncSession, quote: Quote) -> None:
    """Refuse to offer a quote that still needs internal approval.

    Called before a quote is offered through any channel. Does nothing when
    the instance asks for no approval of this quote.
    """
    state = await state_of(db, quote)
    message = state.blocked_message
    if message is not None:
        raise DomainValidationError(message)


async def _quote(db: AsyncSession, quote_id: UUID) -> Quote:
    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    return quote


def _payload(approval: QuoteApproval, quote: Quote) -> dict[str, object]:
    """What an event carries: ids and the reference, never an amount."""
    return {
        "approval_id": str(approval.id),
        "quote_id": str(quote.id),
        "quote_reference": quote.reference,
        "assignment_id": str(quote.assignment_id),
        "requested_by_id": str(approval.requested_by_id)
        if approval.requested_by_id
        else None,
        "decided_by_id": str(approval.decided_by_id)
        if approval.decided_by_id
        else None,
        "origin": "local",
    }


async def request_approval(
    db: AsyncSession,
    quote_id: UUID,
    *,
    actor: Person | None,
    note: str | None = None,
) -> QuoteApproval:
    """Ask for internal approval of a made quote.

    Possible for a quote that is still open and has no request that is open
    or approved. Also possible when the instance does not require approval:
    a maker may want a second pair of eyes anyway.
    """
    quote = await _quote(db, quote_id)
    if quote.status != "issued":
        raise DomainValidationError(
            "Voor deze offerte kan geen goedkeuring meer worden gevraagd: er is "
            "al over beslist, of er is een nieuwere gemaakt."
        )
    state = await state_of(db, quote)
    if state.current is not None:
        raise DomainValidationError(
            "Voor deze offerte is al goedkeuring gevraagd."
            if state.current.status == APPROVAL_REQUESTED
            else "Deze offerte is al intern goedgekeurd."
        )
    approval = QuoteApproval(
        quote_id=quote.id,
        quote_hash=quote.snapshot_hash,
        status=APPROVAL_REQUESTED,
        requested_by_id=actor.id if actor is not None else None,
        requested_at=datetime.now(UTC),
        request_note=(note or "").strip() or None,
    )
    db.add(approval)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="quote_approval",
        entity_id=approval.id,
        new_value={
            "quote_id": str(quote.id),
            "quote_hash": quote.snapshot_hash,
            "status": APPROVAL_REQUESTED,
        },
    )
    await events.emit(db, EVENT_REQUESTED, _payload(approval, quote))
    return approval


async def decide(
    db: AsyncSession,
    quote_id: UUID,
    *,
    approve: bool,
    actor: Person,
    quote_hash: str,
    note: str | None = None,
    evidence_id: UUID | None = None,
    statement_hash: str | None = None,
    decided_at: datetime | None = None,
) -> QuoteApproval:
    """Approve the quote, or send it back to the maker.

    ``evidence_id`` and ``statement_hash`` name the statement this decision
    was made from (see ``grip.proof``), and ``decided_at`` is the time in
    it. The hash goes into the audit row and the event.

    ``quote_hash`` is the hash the approver saw: the decision is about those
    bytes and no others. Whether ``actor`` holds the right to decide is for
    the caller to ask the access model. The four-eyes rule is checked here.
    """
    quote = await _quote(db, quote_id)
    state = await state_of(db, quote)
    approval = state.current
    if approval is None or approval.status != APPROVAL_REQUESTED:
        raise DomainValidationError(
            "Voor deze offerte staat geen verzoek om goedkeuring open."
        )
    if quote_hash != quote.snapshot_hash or approval.quote_hash != quote.snapshot_hash:
        raise DomainValidationError(
            "De goedkeuring gaat over een andere versie van de offerte dan er "
            "nu ligt. Open de offerte opnieuw."
        )
    # Internal approval is a second person: not who asked for it, and not
    # who made the quote, whatever rights they hold.
    asked = (
        approval.requested_by_id is not None and approval.requested_by_id == actor.id
    )
    made = quote.issued_by_id is not None and quote.issued_by_id == actor.id
    own = asked or made
    self_approved = False
    if own and approve:
        if not await instance_settings.get(db, ALLOW_SELF.key):
            raise DomainValidationError(
                "Je kunt een offerte waarvoor je zelf goedkeuring vroeg niet zelf "
                "goedkeuren. Iemand anders met dit recht beslist."
                if asked
                else "Je kunt een offerte die je zelf maakte niet zelf goedkeuren. "
                "Iemand anders met dit recht beslist."
            )
        self_approved = True
    note = (note or "").strip() or None
    if not approve and note is None:
        raise DomainValidationError(
            "Geef bij terugsturen aan wat er anders moet, zodat de maker verder kan."
        )
    approval.status = APPROVAL_APPROVED if approve else APPROVAL_SENT_BACK
    approval.decided_by_id = actor.id
    approval.decided_at = decided_at or datetime.now(UTC)
    approval.evidence_id = evidence_id
    approval.decision_note = note
    approval.self_approved = self_approved
    await db.flush()
    new_value: dict[str, object] = {
        "status": approval.status,
        "quote_hash": approval.quote_hash,
    }
    if self_approved:
        # Four eyes were not applied; the instance allows that and it shows.
        new_value["self_approved"] = True
    if statement_hash:
        new_value["statement_hash"] = statement_hash
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="quote_approval",
        entity_id=approval.id,
        old_value={"status": APPROVAL_REQUESTED},
        new_value=new_value,
    )
    await events.emit(
        db,
        EVENT_APPROVED if approve else EVENT_SENT_BACK,
        # Refers to the statement of this decision; never its content.
        {**_payload(approval, quote), "statement_hash": statement_hash},
    )
    return approval


async def withdraw(
    db: AsyncSession, quote_id: UUID, *, actor: Person | None
) -> QuoteApproval:
    """Take back an open request, or an approval of a quote not yet offered."""
    quote = await _quote(db, quote_id)
    state = await state_of(db, quote)
    approval = state.current
    if approval is None:
        raise DomainValidationError(
            "Voor deze offerte is niets om in te trekken: er staat geen verzoek "
            "open en ze is niet goedgekeurd."
        )
    if approval.status == APPROVAL_APPROVED and state.offered:
        raise DomainValidationError(
            "De goedkeuring kan niet meer worden ingetrokken: de offerte is al "
            "aangeboden aan de opdrachtgever."
        )
    old = approval.status
    approval.status = APPROVAL_WITHDRAWN
    approval.withdrawn_by_id = actor.id if actor is not None else None
    approval.withdrawn_at = datetime.now(UTC)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="quote_approval",
        entity_id=approval.id,
        old_value={"status": old},
        new_value={"status": APPROVAL_WITHDRAWN},
    )
    await events.emit(db, EVENT_WITHDRAWN, _payload(approval, quote))
    return approval


async def waiting(db: AsyncSession) -> list[tuple[QuoteApproval, Quote]]:
    """Open requests on quotes that are still open, oldest first."""
    result = await db.execute(
        select(QuoteApproval, Quote)
        .join(Quote, Quote.id == QuoteApproval.quote_id)
        .where(
            QuoteApproval.status == APPROVAL_REQUESTED,
            QuoteApproval.quote_hash == Quote.snapshot_hash,
            Quote.status == "issued",
        )
        .order_by(QuoteApproval.requested_at)
    )
    return [(row[0], row[1]) for row in result.all()]


async def has_request(db: AsyncSession, quote_id: UUID) -> bool:
    """Whether approval was ever asked for this quote.

    The fact the access rule needs: an approver reads a quote in full only
    when that quote was put before an approver.
    """
    count = await db.scalar(
        select(func.count())
        .select_from(QuoteApproval)
        .where(QuoteApproval.quote_id == quote_id)
    )
    return bool(count)
