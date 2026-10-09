"""Whether a session changed anything since something was read through it.

A request may keep what it read for as long as it changes nothing: the
relations of the reader, the rows of a list. ``generation`` gives a number
that moves with every flush that wrote; a holder of read data compares it
with the number it saw when it read.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_GENERATION = "grip_change_generation"


@sa_event.listens_for(Session, "before_flush")
def _count(session: Session, flush_context: Any, instances: Any) -> None:
    if session.new or session.dirty or session.deleted:
        session.info[_GENERATION] = session.info.get(_GENERATION, 0) + 1


def generation(session: AsyncSession | Session) -> int | None:
    """The number of writing flushes so far; None while changes are pending.

    With pending changes nothing read earlier can be trusted: the next
    statement flushes them first.
    """
    if session.new or session.dirty or session.deleted:
        return None
    return int(session.info.get(_GENERATION, 0))
