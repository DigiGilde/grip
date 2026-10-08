"""Domain events: the seam between the domain and the federation module.

The service layer emits an event inside the transaction of the change it
describes. The event is written to the stream (``grip.events.stream``, ADR
0028) and then handed to the handlers of its type, in that same
transaction. Nothing is registered by default; the federation module
registers handlers that write to its outbox. The domain never imports from
federation and knows nothing about transport (ADR 0015).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grip.events import stream
from grip.models.stream_event import StreamEvent

ASSIGNMENT_REQUEST_CREATED = "assignment_request.created"
QUOTE_ISSUED = "quote.issued"
# An issued quote is put before the client, through a channel.
QUOTE_OFFERED = "quote.offered"
# Internal approval of a quote, before it may be offered. Knowledge of this
# organisation only: no handler may send any of these to another instance.
QUOTE_APPROVAL_REQUESTED = "quote_approval.requested"
QUOTE_APPROVAL_APPROVED = "quote_approval.approved"
QUOTE_APPROVAL_SENT_BACK = "quote_approval.sent_back"
QUOTE_APPROVAL_WITHDRAWN = "quote_approval.withdrawn"
QUOTE_ACCEPTED = "quote.accepted"
QUOTE_REJECTED = "quote.rejected"
ASSIGNMENT_STATUS_CHANGED = "assignment.status_changed"
FINAL_REPORT_ISSUED = "final_report.issued"
VACANCY_PUBLISHED = "vacancy.published"
# Someone recorded that an invoice was sent for delivered billing data, or
# took such a record back.
INVOICE_RECORDED = "invoice.recorded"
INVOICE_WITHDRAWN = "invoice.withdrawn"
# The billing scale of a person was recorded or changed.
PERSON_SCALE_CHANGED = "person_scale.changed"
# The price of a month that was already delivered changed (a promotion or a
# rate card with effect in the past): the difference is to be delivered.
BILLING_CORRECTION_AROSE = "billing_correction.arose"

EVENT_TYPES = (
    ASSIGNMENT_REQUEST_CREATED,
    QUOTE_ISSUED,
    QUOTE_OFFERED,
    QUOTE_APPROVAL_REQUESTED,
    QUOTE_APPROVAL_APPROVED,
    QUOTE_APPROVAL_SENT_BACK,
    QUOTE_APPROVAL_WITHDRAWN,
    QUOTE_ACCEPTED,
    QUOTE_REJECTED,
    ASSIGNMENT_STATUS_CHANGED,
    FINAL_REPORT_ISSUED,
    VACANCY_PUBLISHED,
    INVOICE_RECORDED,
    INVOICE_WITHDRAWN,
    PERSON_SCALE_CHANGED,
    BILLING_CORRECTION_AROSE,
)

Handler = Callable[[AsyncSession, str, dict[str, Any]], Awaitable[None]]

# Each handler is registered with the stream through an adapter that gives
# it the payload it has always received.
_adapters: dict[tuple[str, Handler], stream.TransactionalHandler] = {}


def _adapt(handler: Handler) -> stream.TransactionalHandler:
    async def call(session: AsyncSession, event: StreamEvent) -> None:
        payload = getattr(event, "_raw_payload", None)
        await handler(session, event.type, payload or dict(event.payload or {}))

    return call


def register_handler(event_type: str, handler: Handler) -> None:
    """Register a handler for one event type. Registering twice is a no-op.

    The handler runs in the transaction of the event: what it writes is
    undone when the change is, and when it raises it refuses the change.
    For an effect outside the database use ``stream.after_commit``.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    key = (event_type, handler)
    if key not in _adapters:
        _adapters[key] = _adapt(handler)
        stream.on_event(event_type, _adapters[key])


def unregister_handler(event_type: str, handler: Handler) -> None:
    adapter = _adapters.pop((event_type, handler), None)
    if adapter is not None:
        stream.remove_handler(event_type, adapter)


def clear_handlers() -> None:
    """Remove every handler. For tests."""
    for (event_type, _handler), adapter in list(_adapters.items()):
        stream.remove_handler(event_type, adapter)
    _adapters.clear()


async def emit(session: AsyncSession, event_type: str, payload: dict[str, Any]) -> None:
    """Record a domain event and call its handlers, in the caller's transaction.

    A handler that raises aborts the change it belongs to: an event that
    cannot be recorded must not be lost silently.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    await stream.record(session, event_type, payload=payload)
