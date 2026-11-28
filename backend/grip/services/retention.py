"""The retention round: once a day the worker applies the retention periods.

The round is an ordered list of rules (ADR 0057). Each rule runs in its own
transaction, so a rule that fails leaves the others to do their work; the
next day it is tried again. Every rule can run twice without harm.

The worker starts the round at ``RETENTION_HOUR`` on the instance's
calendar. By hand::

    python -m grip.services.retention
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core import clock
from grip.core.config import Settings
from grip.events import context
from grip.events.retention import apply_retention
from grip.services import dossiers, instance_settings
from grip.services.errors import DomainValidationError
from grip.services.standing import purge_withdrawn
from grip.services.vacancies.request_forms import remove_expired

logger = logging.getLogger(__name__)

JOB = "retention"

# Held for the whole round, so two workers never run it at once.
_LOCK_KEY = 0x67726970_0057

DESTROY = "destroy"
KEEP = "keep"
MAX_YEARS = 100


def _case_rule(value: Any) -> dict[str, Any] | None:
    """What the selection list says for a kind of case: destroy so many
    years after closing, or keep for good. None: nothing is destroyed."""
    if value is None:
        return None
    if isinstance(value, dict):
        if value == {"outcome": KEEP}:
            return {"outcome": KEEP}
        if set(value) == {"outcome", "years"} and value["outcome"] == DESTROY:
            years = value["years"]
            if (
                isinstance(years, int)
                and not isinstance(years, bool)
                and 1 <= years <= MAX_YEARS
            ):
                return {"outcome": DESTROY, "years": years}
            raise DomainValidationError(
                "Vernietigen kan na een heel aantal jaren, "
                f"van 1 tot en met {MAX_YEARS}."
            )
    raise DomainValidationError(
        "Kies vernietigen na een aantal jaren, blijvend bewaren of niets."
    )


ASSIGNMENT = instance_settings.declare(
    "retention.assignment",
    None,
    _case_rule,
    "Wat er met een opdracht gebeurt nadat het dossier is gesloten: vernietigen "
    "na een aantal jaren of blijvend bewaren (leeg is niets vernietigen)",
)


Rule = Callable[[AsyncSession, datetime], Awaitable[int]]


async def close_unanswered_dossiers(db: AsyncSession, now: datetime) -> int:
    return await dossiers.close_overdue_dossiers(db, today=clock.local_date(now))


async def erase_old_events(db: AsyncSession, now: datetime) -> int:
    return await apply_retention(db, now=now)


async def remove_withdrawn_prospects(db: AsyncSession, now: datetime) -> int:
    return await purge_withdrawn(db, today=clock.local_date(now))


async def remove_closed_request_forms(db: AsyncSession, now: datetime) -> int:
    return await remove_expired(db, now=now)


RULES: tuple[Rule, ...] = (
    close_unanswered_dossiers,
    erase_old_events,
    remove_withdrawn_prospects,
    remove_closed_request_forms,
)


@dataclass
class Outcome:
    # False when another worker held the round.
    ran: bool = True
    counts: dict[str, int] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> Outcome:
    """Run every rule once, in order. Logs one line per rule."""
    now = now or clock.now()
    outcome = Outcome()
    async with session_factory() as lock:
        held = await lock.scalar(
            text("select pg_try_advisory_xact_lock(:key)"), {"key": _LOCK_KEY}
        )
        if not held:
            logger.info("Retention: another worker is running the round")
            return Outcome(ran=False)
        with context.scope(job=JOB):
            for rule in RULES:
                name = rule.__name__
                try:
                    async with session_factory() as db:
                        count = await rule(db, now)
                        await db.commit()
                except Exception:
                    logger.exception("Retention: %s failed", name)
                    outcome.failed.append(name)
                    continue
                outcome.counts[name] = count
                logger.info("Retention: %s: %s", name, count)
        # Commit, not roll back: when the factory hands out savepoints on one
        # connection, rolling back would undo the rules.
        await lock.commit()
    return outcome


def retention_due(last: datetime | None, settings: Settings) -> bool:
    """Whether the round must run now (the worker asks every minute)."""
    hour = settings.RETENTION_HOUR.strip()
    if not hour:
        return False
    local = clock.now().astimezone(clock.zone())
    if local.hour != int(hour):
        return False
    return last is None or clock.local_date(last) != local.date()


async def run_retention_loop(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    last: datetime | None = None
    while True:
        try:
            if retention_due(last, settings):
                await run_once(session_factory, settings)
                last = clock.now()
        except Exception:
            logger.exception("Retention: the round failed")
        await asyncio.sleep(60)


async def _main() -> int:
    from grip.core.config import get_settings
    from grip.core.database import async_session, close_db

    logging.basicConfig(level=logging.INFO)
    try:
        outcome = await run_once(async_session, get_settings())
    finally:
        await close_db()
    return 1 if outcome.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
