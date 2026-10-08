"""Process messages that were stored before a domain handler existed."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core.config import Settings
from grip.federation import terms
from grip.federation.models import FederationInbox
from grip.federation.problems import FederationProblem
from grip.federation.registry import InboundMessage, get_inbound_handler

logger = logging.getLogger(__name__)


async def process_pending(db: AsyncSession, *, limit: int = 50) -> int:
    """Hand unprocessed messages to their handler, oldest first.

    A message is normally processed when it arrives. This catches up on the
    ones that arrived while no handler was registered. The receipt has
    already been given, so a handler that refuses the message now cannot
    tell the sender; the refusal is recorded with the message instead.
    """
    rows = (
        (
            await db.execute(
                select(FederationInbox)
                .where(FederationInbox.processed_at.is_(None))
                .order_by(FederationInbox.received_at)
                .limit(limit)
                .with_for_update(skip_locked=True, of=FederationInbox)
            )
        )
        .scalars()
        .all()
    )
    processed = 0
    for row in rows:
        handler = get_inbound_handler(row.operation)
        if handler is None:
            continue
        message = InboundMessage(
            message_id=row.message_id,
            operation=row.operation,
            payload=terms.from_contract(row.payload),
            path_parameters={},
            received_at=row.received_at,
        )
        try:
            async with db.begin_nested():
                result = await handler(db, row.peer, message)
            row.result = result or {}
        except FederationProblem as problem:
            logger.warning(
                "Stored message %s (%s) was refused afterwards: %s",
                row.message_id,
                row.operation,
                problem,
            )
            row.result = {"refused": problem.body()}
        row.processed_at = datetime.now(UTC)
        processed += 1
    await db.flush()
    return processed


async def run_inbox_loop(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Catch up on unprocessed messages forever. Started by the worker."""
    while True:
        try:
            async with session_factory() as db:
                count = await process_pending(db)
                await db.commit()
            if count:
                logger.info("Inbox: processed %d stored message(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Inbox loop failed; trying again later")
        await asyncio.sleep(settings.FEDERATION_OUTBOX_INTERVAL_SECONDS)
