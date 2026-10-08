"""Domain events: the seam between the domain and the federation module.

The service layer emits an event inside the transaction of the change it
describes. Nothing is registered by default; the federation module registers
handlers that write to its outbox. The domain never imports from federation
and knows nothing about transport (ADR 0015).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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

_handlers: dict[str, list[Handler]] = defaultdict(list)


def register_handler(event_type: str, handler: Handler) -> None:
    """Register a handler for one event type. Registering twice is a no-op."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    if handler not in _handlers[event_type]:
        _handlers[event_type].append(handler)


def unregister_handler(event_type: str, handler: Handler) -> None:
    if handler in _handlers[event_type]:
        _handlers[event_type].remove(handler)


def clear_handlers() -> None:
    """Remove every handler. For tests."""
    _handlers.clear()


async def emit(session: AsyncSession, event_type: str, payload: dict[str, Any]) -> None:
    """Call the handlers of an event, in the caller's transaction.

    A handler that raises aborts the change it belongs to: an event that
    cannot be recorded must not be lost silently.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    for handler in list(_handlers[event_type]):
        await handler(session, event_type, payload)
