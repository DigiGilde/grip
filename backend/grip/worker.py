"""Background loops of grip, run as a separate process::

    python -m grip.worker

Today these are the federation loops: sending outbox messages through the
outway, and catching up on received messages that were stored before a
handler existed. Both are safe to run in more than one process; rows are
claimed with SKIP LOCKED.
"""

from __future__ import annotations

import asyncio
import logging

from grip.core.config import Settings, get_settings
from grip.core.database import async_session, close_db
from grip.federation.events import register_event_handlers
from grip.federation.inbox import run_inbox_loop
from grip.federation.outbox import run_outbox_loop
from grip.tasks.loop import run_task_loop

logger = logging.getLogger(__name__)


def _loops(settings: Settings) -> list:
    loops = []
    if settings.FEDERATION_OUTBOUND_ENABLED:
        loops.append(run_outbox_loop(async_session, settings))
    else:
        logger.info("FEDERATION_OUTBOUND_ENABLED is off: outbox is not sent")
    if settings.FEDERATION_INBOUND_ENABLED:
        loops.append(run_inbox_loop(async_session, settings))
    if settings.TASKS_EVALUATE_INTERVAL_SECONDS > 0:
        loops.append(run_task_loop(async_session, settings))
    return loops


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    register_event_handlers()
    loops = _loops(settings)
    if not loops:
        logger.info("Nothing to run: federation is off in both directions")
        return
    try:
        await asyncio.gather(*loops)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
