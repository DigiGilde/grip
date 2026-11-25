"""What the client gives for the invoice, and where it goes from there.

The client gives its billing details (the annex "Factuurinformatie" of a
quote: where the invoice goes, a reference, a contact) when it accepts a
quote, and may give new ones later. The contractor takes them into the
billing terms of the assignment (ADR 0039), from its next delivery on; a
delivery that was made keeps what it had.

The client owns these details (ADR 0053). Its own instance keeps the latest
it gave; a change it gives later goes to the contractor as a domain event,
which the federation bridge turns into a message.

Whether someone may give or take them is for the caller to ask the access
model; these functions assume the answer was yes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.core.config import get_settings
from grip.models.assignment import Assignment
from grip.models.billing_delivery import BillingTerms, ClientBillingDetails
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import Quote
from grip.services import billing_deliveries, events
from grip.services.assignments import get_assignment
from grip.services.billing_deliveries import DETAIL_LABELS, REQUIRED_DETAILS
from grip.services.errors import DomainValidationError


class MissingBillingDetailsError(DomainValidationError):
    """Details were given, or are asked for, without what an invoice needs."""

    def __init__(self, missing: list[str]) -> None:
        labels = [DETAIL_LABELS[key] for key in missing]
        text = labels[0] if len(labels) == 1 else ", ".join(labels[:-1])
        if len(labels) > 1:
            text += " en " + labels[-1]
        verb = "ontbreekt" if len(labels) == 1 else "ontbreken"
        super().__init__(
            f"{text[0].upper()}{text[1:]} {verb}. "
            "Vul de factuurgegevens van de opdrachtgever in."
        )
        self.missing = missing
        self.problem_extra = {"missing_details": missing}


def asks_for_details(quote: Quote) -> bool:
    """Whether the quote has the annex Factuurinformatie for the client to fill."""
    letter = (quote.snapshot or {}).get("letter") or {}
    return bool(letter.get("billing_annex"))


def given(
    details: Mapping[str, Any] | None, *, required: bool
) -> dict[str, str] | None:
    """The details as given, cleaned; None when nothing was given.

    Without organisation, address and postcode_city nothing counts as given,
    so a form that only carries a reference filled in beforehand gives
    nothing. With one of the three, all three are needed; ``required`` asks
    for them in any case.
    """
    cleaned = billing_deliveries.clean_details(
        {key: value for key, value in (details or {}).items() if value is not None}
    )
    if not required and not any(cleaned.get(key) for key in REQUIRED_DETAILS):
        return None
    missing = [key for key in REQUIRED_DETAILS if not cleaned.get(key)]
    if missing:
        raise MissingBillingDetailsError(missing)
    return cleaned


def for_acceptance(
    quote: Quote, details: Mapping[str, Any] | None, *, form: str
) -> dict[str, str] | None:
    """What an acceptance in this form gives, or why it cannot be made.

    Signing the quote asks for the details when its annex asks for them. A
    signed pdf is recorded by someone here, who may type over the annex.
    """
    required = form != "uploaded_pdf" and asks_for_details(quote)
    return given(details, required=required)


# -- at the contractor ---------------------------------------------------------


async def take(
    session: AsyncSession,
    assignment_id: UUID,
    details: Mapping[str, str],
    *,
    given_at: datetime,
    actor: Person | None,
) -> bool:
    """Take what the client gave into the billing terms. False when older.

    The details replace what the terms held, also what someone here typed
    in before. A change the client gave before the moment of what the terms
    hold from the client is received and not taken over.
    """
    # A moment in the future (a typed-in signing date, a peer's clock) would
    # make every later change look older and never be taken over.
    given_at = min(given_at, clock.now())
    row = await session.get(BillingTerms, assignment_id)
    if (
        row is not None
        and row.details_given_at is not None
        and given_at <= row.details_given_at
    ):
        return False
    await billing_deliveries.set_terms(
        session,
        assignment_id,
        actor=actor,
        details=dict(details),
        details_given_at=given_at,
    )
    return True


# -- at the client -------------------------------------------------------------


async def kept(
    session: AsyncSession, assignment_id: UUID
) -> ClientBillingDetails | None:
    """The details this instance last gave for the assignment, as client."""
    return await session.get(ClientBillingDetails, assignment_id)


async def keep(
    session: AsyncSession,
    assignment_id: UUID,
    details: Mapping[str, str],
    *,
    given_at: datetime,
    actor: Person | None,
) -> ClientBillingDetails:
    """Keep what this instance, as client, gave. Sends nothing."""
    row = await kept(session, assignment_id)
    before = dict(row.details or {}) if row is not None else None
    if row is None:
        row = ClientBillingDetails(assignment_id=assignment_id, given_at=given_at)
        session.add(row)
    row.details = dict(details)
    row.given_at = given_at
    row.given_by_id = actor.id if actor is not None else None
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE if before is None else UPDATE,
        entity="client_billing_details",
        entity_id=assignment_id,
        old_value={"details": before} if before is not None else None,
        new_value={"details": dict(details), "given_at": given_at.isoformat()},
        assignment_id=assignment_id,
    )
    return row


async def _contractor_is_here(session: AsyncSession, assignment: Assignment) -> bool:
    if assignment.contractor_organisation_id is None:
        return True
    contractor = await session.get(Organisation, assignment.contractor_organisation_id)
    own = get_settings().INSTANCE_BASE_URI.rstrip("/")
    return (
        contractor is not None
        and bool(contractor.instance_uri)
        and contractor.instance_uri.rstrip("/") == own
    )


async def given_at_acceptance(
    session: AsyncSession,
    assignment_id: UUID,
    details: Mapping[str, str],
    *,
    signed_at: datetime,
    actor: Person | None,
) -> None:
    """The client accepted here, in its own instance, and gave these details.

    Kept as given. The acceptance itself carries them to a contractor
    elsewhere; a contractor in this same instance takes them right away.
    """
    await keep(session, assignment_id, details, given_at=signed_at, actor=actor)
    assignment = await get_assignment(session, assignment_id)
    if await _contractor_is_here(session, assignment):
        await take(session, assignment_id, details, given_at=signed_at, actor=actor)


async def change(
    session: AsyncSession,
    assignment_id: UUID,
    details: Mapping[str, Any] | None,
    *,
    actor: Person | None,
) -> ClientBillingDetails:
    """This instance, as client, gives new billing details for an assignment.

    They replace what it gave before and apply from the contractor's next
    delivery on. Emits ``client_billing_details.given``.
    """
    cleaned = given(details, required=True)
    assert cleaned is not None
    assignment = await get_assignment(session, assignment_id)
    given_at = datetime.now(UTC)
    row = await keep(session, assignment_id, cleaned, given_at=given_at, actor=actor)
    if await _contractor_is_here(session, assignment):
        await take(session, assignment_id, cleaned, given_at=given_at, actor=actor)
    await events.emit(
        session,
        events.CLIENT_BILLING_DETAILS_GIVEN,
        {
            "change_id": str(uuid.uuid4()),
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "given_at": given_at.isoformat(),
            "origin": "local",
        },
    )
    return row
