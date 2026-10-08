"""Deciding on a received quote in the client's own instance.

A tekenbevoegde of this instance accepts or rejects a quote that a
contractor sent. The acceptance is signed with the key of this instance: a
JWS over the message as it will cross the boundary. The domain records it
and announces it; the bridge then sends exactly the signed message to the
contractor, who verifies it against the keys this instance publishes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.federation import signing, terms
from grip.federation.bridge.organisations import own_reference
from grip.models.person import Person
from grip.models.quote import QuoteAcceptance, QuoteRejection
from grip.services import quotes


def signer_of(person: Person, function: str | None = None) -> dict[str, Any]:
    signer: dict[str, Any] = {
        "name": person.name,
        "email": person.email.strip().lower(),
    }
    if function:
        signer["function"] = function
    return signer


async def accept_received_quote(
    db: AsyncSession,
    quote_id: UUID,
    *,
    actor: Person,
    signer_function: str | None = None,
) -> QuoteAcceptance:
    """Accept a received quote on behalf of this instance, and sign that.

    Whether ``actor`` may do this is for the caller to ask the access model
    (action accept_quote); this function assumes the answer was yes.
    """
    settings = get_settings()
    quote = await quotes.get_quote(db, quote_id)
    acceptance_id = uuid.uuid4()
    signed_at = datetime.now(UTC)
    organisation = own_reference(settings)
    # The message as the contractor will receive it. Every value here is
    # what the domain event will carry, so the signature keeps fitting.
    message = {
        "id": str(acceptance_id),
        "quote_id": str(quote.id),
        "quote_hash": quote.snapshot_hash,
        "signer": signer_of(actor, signer_function),
        "organisation": organisation,
        "signed_at": signed_at.isoformat(),
        "form": "own_instance",
    }
    jws = signing.sign_acceptance(terms.to_contract(message), settings)
    return await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=actor.name,
        signer_email=actor.email,
        signer_function=signer_function,
        signer_person_id=actor.id,
        organisation=organisation,
        form="own_instance",
        actor=actor,
        signed_at=signed_at,
        jws=jws,
        acceptance_id=acceptance_id,
    )


async def reject_received_quote(
    db: AsyncSession,
    quote_id: UUID,
    *,
    actor: Person,
    reason: str | None = None,
) -> QuoteRejection:
    quote = await quotes.get_quote(db, quote_id)
    return await quotes.reject_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        actor=actor,
        reason=reason,
        organisation=own_reference(),
    )
