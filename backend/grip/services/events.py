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
QUOTE_ACCEPTED = "quote.accepted"
QUOTE_REJECTED = "quote.rejected"
ASSIGNMENT_STATUS_CHANGED = "assignment.status_changed"
FINAL_REPORT_ISSUED = "final_report.issued"
VACANCY_PUBLISHED = "vacancy.published"

EVENT_TYPES = (
    ASSIGNMENT_REQUEST_CREATED,
    QUOTE_ISSUED,
    QUOTE_ACCEPTED,
    QUOTE_REJECTED,
    ASSIGNMENT_STATUS_CHANGED,
    FINAL_REPORT_ISSUED,
    VACANCY_PUBLISHED,
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
