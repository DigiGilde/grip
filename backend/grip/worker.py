"""Background loops of grip, run as a separate process::

    python -m grip.worker

These are the federation loops (sending outbox messages through the outway,
and catching up on received messages that were stored before a handler
existed; both are safe to run in more than one process, rows are claimed
with SKIP LOCKED) and the task loop, which brings the tasks of every open
case in line with the facts on an interval, and the mail loop, which sends
what was queued with a change.
"""

from __future__ import annotations

import asyncio
import logging

from grip.core.config import Settings, get_settings
from grip.core.database import async_session, close_db
from grip.federation.events import register_event_handlers
from grip.federation.inbox import run_inbox_loop
from grip.federation.outbox import run_outbox_loop
from grip.integrations.mail.config import is_configured as mail_is_configured
from grip.integrations.mail.outbox import run_mail_loop
from grip.integrations.push.config import is_configured as push_is_configured
from grip.integrations.push.outbox import run_push_loop
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
    return loops


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    register_event_handlers()
    loops = _loops(settings)
    # Tasks: time makes work too (a month ends, a deadline passes).
    if settings.TASKS_EVALUATE_INTERVAL_SECONDS > 0:
        loops.append(run_task_loop(async_session, settings))
    # Mail that was queued with a change (a signing link, for one).
    if mail_is_configured(settings):
        loops.append(run_mail_loop(async_session, settings))
    else:
        logger.info("SMTP_HOST or SMTP_FROM is not set: no mail is sent")
    # Notifications on people's devices: look for what waits, send what is due.
    if push_is_configured(settings):
        loops.append(run_push_loop(async_session, settings))
    else:
        logger.info("PUSH_VAPID_PRIVATE_KEY is not set: no notifications are sent")
    # An example instance goes back to its starting state every night.
    if settings.is_example and settings.EXAMPLE_RESET_HOUR.strip():
        from grip.core.example import run_reset_loop

        loops.append(run_reset_loop(async_session, settings))
    if not loops:
        logger.info("Nothing to run: federation, the task loop and mail are off")
        return
    try:
        await asyncio.gather(*loops)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
