"""The periodic look of the task engine, run by the worker.

Time makes tasks too: a month ends, a deadline passes. Nothing in the
domain changes at that moment, so no event tells the engine. This loop
evaluates every open case on an interval.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core import clock
from grip.core.config import Settings
from grip.tasks import engine

logger = logging.getLogger(__name__)


async def run_once(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> engine.Outcome:
    async with session_factory() as db:
        outcome = await engine.evaluate_all(
            db, today=clock.today(), instance_base_uri=settings.INSTANCE_BASE_URI
        )
        await db.commit()
    return outcome


async def run_task_loop(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    interval = settings.TASKS_EVALUATE_INTERVAL_SECONDS
    while True:
        try:
            outcome = await run_once(session_factory, settings)
            if outcome.changes:
                logger.info(
                    "Taken bijgewerkt: %s gemaakt, %s gesloten, %s vervallen",
                    outcome.created,
                    outcome.closed,
                    outcome.obsolete,
                )
        except Exception:
            logger.exception("De taken konden niet worden bijgewerkt")
        await asyncio.sleep(interval)
