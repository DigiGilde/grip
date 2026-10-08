"""From domain events to messages for other instances.

The domain announces what happened, in its own terms. A message builder that
the domain side registers turns that into the contract-shaped message; this
module then decides which peer has to receive it and queues it. A
counterpart that does not run grip is not an error: there is simply nothing
to send.

What a builder returns (``built`` below) is a dict with:

- ``message``: the body in the shape of the contract;
- ``recipient`` (optional): an organisation reference, when the receiver
  does not follow from the message itself;
- ``recipients`` (optional, vacancies): a list of organisation references;
  without it a vacancy goes to every active instance peer.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.federation.models import (
    PEER_ROLE_CHILD,
    PEER_ROLE_COUNTERPART,
    PEER_ROLE_PARENT,
    FederationOutbox,
    Peer,
)
from grip.federation.outbox import enqueue
from grip.federation.peers import find_peer_for_organisation
from grip.federation.registry import get_message_builder

logger = logging.getLogger(__name__)

EventHandler = Callable[
    [AsyncSession, dict[str, Any]], Awaitable[list[FederationOutbox]]
]


def _uuid_from_uri(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


async def _to_one(
    db: AsyncSession,
    payload: dict[str, Any],
    operation_id: str,
    recipient_field: str | None,
    **path_parameters: str,
) -> list[FederationOutbox]:
    message = payload["message"]
    organisation = payload.get("recipient") or (
        message.get(recipient_field) if recipient_field else None
    )
    if not organisation:
        return []
    peer = await find_peer_for_organisation(db, organisation)
    if peer is None:
        logger.info("%s: the recipient runs no known instance; not sent", operation_id)
        return []
    return [await enqueue(db, peer, operation_id, message, **path_parameters)]


async def on_assignment_request_created(
    db: AsyncSession, payload: dict[str, Any]
) -> list[FederationOutbox]:
    """This instance, as client, asks a contractor for a quote."""
    return await _to_one(db, payload, "sendAssignmentRequest", "contractor")


async def on_quote_issued(
    db: AsyncSession, payload: dict[str, Any]
) -> list[FederationOutbox]:
    """This instance, as contractor, issued a quote."""
    return await _to_one(db, payload, "sendQuote", "client")


async def on_quote_accepted(
    db: AsyncSession, payload: dict[str, Any]
) -> list[FederationOutbox]:
    """This instance, as client, accepted a quote of a contractor.

    The acceptance does not name the contractor, so the event carries it as
    ``recipient``. Acceptances that arise at the contractor itself (signing
    link, uploaded pdf) have no recipient and are not sent.
    """
    quote_id = payload["message"]["quote_id"]
    return await _to_one(db, payload, "sendAcceptance", None, quoteId=quote_id)


async def on_quote_rejected(
    db: AsyncSession, payload: dict[str, Any]
) -> list[FederationOutbox]:
    quote_id = payload["message"]["quote_id"]
    return await _to_one(db, payload, "sendRejection", None, quoteId=quote_id)


async def on_final_report_issued(
    db: AsyncSession, payload: dict[str, Any]
) -> list[FederationOutbox]:
    """This instance, as contractor, sends the final report to the client."""
    assignment_id = _uuid_from_uri(payload["message"]["assignment_uri"])
    return await _to_one(
        db, payload, "sendFinalReport", None, assignmentId=assignment_id
    )


async def on_vacancy_published(
    db: AsyncSession, payload: dict[str, Any]
) -> list[FederationOutbox]:
    """An open role is put out to other instances."""
    message = payload["message"]
    if payload.get("recipients") is not None:
        peers = [
            peer
            for organisation in payload["recipients"]
            if (peer := await find_peer_for_organisation(db, organisation)) is not None
        ]
    else:
        peers = list(
            (
                await db.execute(
                    select(Peer).where(
                        Peer.is_active.is_(True),
                        Peer.role.in_(
                            [PEER_ROLE_COUNTERPART, PEER_ROLE_PARENT, PEER_ROLE_CHILD]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
    return [await enqueue(db, peer, "sendVacancy", message) for peer in peers]


# Domain event type to the handler that queues the built message.
EVENT_HANDLERS: dict[str, EventHandler] = {
    "assignment_request.created": on_assignment_request_created,
    "quote.issued": on_quote_issued,
    "quote.accepted": on_quote_accepted,
    "quote.rejected": on_quote_rejected,
    "final_report.issued": on_final_report_issued,
    "vacancy.published": on_vacancy_published,
}


async def dispatch(
    db: AsyncSession, event_type: str, payload: dict[str, Any]
) -> list[FederationOutbox]:
    """Handle one domain event: build the message and queue it.

    Runs inside the transaction of the domain change. An invalid message
    raises and aborts that change: an event that cannot be delivered as the
    contract describes must not be lost silently.
    """
    handler = EVENT_HANDLERS.get(event_type)
    builder = get_message_builder(event_type)
    if handler is None or builder is None:
        return []
    built = await builder(db, payload)
    if built is None:
        return []
    return await handler(db, built)


async def _on_domain_event(
    db: AsyncSession, event_type: str, payload: dict[str, Any]
) -> None:
    await dispatch(db, event_type, payload)


def register_event_handlers() -> list[str]:
    """Subscribe to the domain events this module has a message for.

    Also registers the bridge to the domain, which holds the message
    builders. Returns the event types that were subscribed. An event type
    the domain does not announce yet is skipped.
    """
    from grip.federation.bridge import register_bridge
    from grip.services import events as domain_events

    # Without builders an event leads to no message.
    register_bridge()
    subscribed = []
    for event_type in EVENT_HANDLERS:
        if event_type not in domain_events.EVENT_TYPES:
            logger.info("Domain does not announce %s yet; not subscribed", event_type)
            continue
        domain_events.register_handler(event_type, _on_domain_event)
        subscribed.append(event_type)
    return subscribed
