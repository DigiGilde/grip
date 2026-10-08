"""A quote that a contractor sent: accept or reject it in this instance.

For the tekenbevoegde of an instance that is the client. The acceptance is
signed with the key of this instance and sent to the contractor.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select

from grip.access import Action, Resource
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import CurrentPerson
from grip.federation.bridge.acceptance import (
    accept_received_quote,
    reject_received_quote,
)
from grip.federation.models import FederationOutbox
from grip.models.quote import Quote
from grip.schema.received_quotes import (
    ReceivedQuoteAccept,
    ReceivedQuoteDecisionOut,
    ReceivedQuoteReject,
)
from grip.services.errors import NotFoundError

router = APIRouter(prefix="/received-quotes", tags=["received-quotes"])


async def _quote(db: DbSession, access: RequestAccess, quote_id: UUID) -> Quote:
    """The quote, if this person may decide on it; otherwise as if absent."""
    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    await access.require(
        Action.ACCEPT_QUOTE,
        Resource.quote(quote.id, quote.assignment_id),
        hide_existence=True,
    )
    return quote


async def _queued(db: DbSession, message_id: UUID) -> bool:
    return (
        await db.scalar(
            select(FederationOutbox.id).where(FederationOutbox.message_id == message_id)
        )
    ) is not None


@router.post(
    "/{quote_id}/acceptance",
    response_model=ReceivedQuoteDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
async def accept(
    quote_id: UUID,
    body: ReceivedQuoteAccept,
    access: RequestAccess,
    db: DbSession,
    person: CurrentPerson,
) -> dict[str, Any]:
    quote = await _quote(db, access, quote_id)
    acceptance = await accept_received_quote(
        db, quote.id, actor=person, signer_function=body.signer_function
    )
    return {
        "quote_id": quote.id,
        "assignment_id": quote.assignment_id,
        "decision": "accepted",
        "decided_at": acceptance.signed_at,
        "sent_to_contractor": await _queued(db, acceptance.id),
    }


@router.post(
    "/{quote_id}/rejection",
    response_model=ReceivedQuoteDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
async def reject(
    quote_id: UUID,
    body: ReceivedQuoteReject,
    access: RequestAccess,
    db: DbSession,
    person: CurrentPerson,
) -> dict[str, Any]:
    quote = await _quote(db, access, quote_id)
    rejection = await reject_received_quote(
        db, quote.id, actor=person, reason=body.reason
    )
    return {
        "quote_id": quote.id,
        "assignment_id": quote.assignment_id,
        "decision": "rejected",
        "decided_at": rejection.rejected_at,
        "sent_to_contractor": await _queued(db, rejection.id),
    }
