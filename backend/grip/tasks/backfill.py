"""Give every case its tasks: ``python -m grip.tasks.backfill``.

Run once after the tasks tables exist, and safe to run again: the engine
only changes the difference between the plan and the tasks that exist.
"""

from __future__ import annotations

import asyncio

from grip.core import clock
from grip.core.config import get_settings
from grip.core.database import async_session, close_db
from grip.tasks import engine


async def run() -> engine.Outcome:
    settings = get_settings()
    async with async_session() as db:
        outcome = await engine.evaluate_all(
            db, today=clock.today(), instance_base_uri=settings.INSTANCE_BASE_URI
        )
        await db.commit()
    return outcome


async def main() -> None:
    try:
        outcome = await run()
    finally:
        await close_db()
    print(
        f"{outcome.cases} zaken bekeken: {outcome.created} taken gemaakt, "
        f"{outcome.closed} gesloten, {outcome.obsolete} vervallen, "
        f"{outcome.reopened} heropend."
    )


if __name__ == "__main__":
    asyncio.run(main())
