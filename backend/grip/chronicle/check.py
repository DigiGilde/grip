"""Compare the read models of every assignment with its chronicle::

    python -m grip.chronicle.check

Only reads, so it runs on any instance. Exit code 0 when the tables say what
the chronicles say, 1 when they do not or when one could not be read.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle.verify import differences
from grip.models.assignment import Assignment

logger = logging.getLogger(__name__)


async def check(db: AsyncSession) -> int:
    """Print what differs per assignment. Returns how many differ or broke."""
    rows = (await db.execute(select(Assignment.id, Assignment.name))).all()
    whole = 0
    differing = 0
    broke = 0
    skipped: dict[str, int] = {}
    for assignment_id, name in rows:
        try:
            # A savepoint, so a failed query does not end the check of the rest.
            async with db.begin_nested():
                report = await differences(db, assignment_id)
        except Exception as error:
            broke += 1
            logger.exception("Check of assignment %s failed", assignment_id)
            print(  # noqa: T201
                f"{name} ({assignment_id}): niet te controleren "
                f"({type(error).__name__})."
            )
            continue
        if not report.checked:
            reason = report.reason or "onbekend"
            skipped[reason] = skipped.get(reason, 0) + 1
        elif report.differences:
            differing += 1
            print(f"{name} ({assignment_id}):")  # noqa: T201
            for item in report.differences:
                print(f"  {item}")  # noqa: T201
        else:
            whole += 1
    print(  # noqa: T201
        f"{len(rows)} opdrachten: {whole} zonder verschillen, "
        f"{differing} met verschillen, {sum(skipped.values())} overgeslagen, "
        f"{broke} niet te controleren."
    )
    for reason, count in sorted(skipped.items()):
        print(f"  overgeslagen, {reason}: {count}")  # noqa: T201
    return differing + broke


async def _main() -> int:
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            return 1 if await check(db) else 0
    finally:
        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
