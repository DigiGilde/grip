"""Domain events as a signal to look again.

An event is emitted inside the transaction of the change it describes, at a
moment the change may be half written. So a handler does not compute tasks:
it only notes that something happened, and the next reader, or the worker a
moment later, evaluates the cases against the facts as they then are.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grip.services import events
from grip.tasks import engine


async def _on_event(session: AsyncSession, event_type: str, payload: dict[str, Any]) -> None:
    await engine.invalidate(session)


def register_task_handlers() -> list[str]:
    """Subscribe to every domain event. Registering twice is a no-op."""
    for event_type in events.EVENT_TYPES:
        events.register_handler(event_type, _on_event)
    return list(events.EVENT_TYPES)
