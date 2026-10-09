"""An example instance: only fictional data, for showing grip.

``INSTANCE_MODE=voorbeeld`` makes an instance an example. It then:

- loads the fictional example data by itself on an empty database, once;
- lets a visitor who logs in through the identity provider, and whose
  address is on the list of ``EXAMPLE_VISITORS``, look as one of the example
  persons (the visitor has no person record of their own);
- goes back to its starting state every night (``EXAMPLE_RESET_HOUR``);
- marks every page and every document as an example and never carries the
  Rijkslogo;
- never talks to another system (see ``Settings._validate_instance_mode``).

The separation from real work is enforced here, not left to discipline:

- an example instance refuses to start on a database that holds anything
  that is not its own example data;
- a database that was ever filled as an example carries a marker, and an
  instance for real work refuses to start on it. An example instance is
  thrown away, never promoted.

Local development (``DEV_NO_AUTH`` without ``PUBLIC_HOST``) is not an
example instance and is untouched by all of this: there the seed is run by
hand, as before.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.audit import CREATE, record_audit
from grip.core.config import Settings
from grip.models.instance_setting import InstanceSetting
from grip.models.person import Person
from grip.models.role import BEHEERDER
from grip.repositories.person import PersonRepository

logger = logging.getLogger(__name__)

# Row in instance_setting that says: this database holds example data.
MARKER_KEY = "instance.example"

# Session key of a visitor of an example instance: who really logged in.
# The session's ``person_id`` is the example person they look as.
VISITOR_SESSION_KEY = "example_visitor"

# Advisory lock held while an example instance fills itself.
_LOCK_KEY = 0x67726970_0050


class ExampleModeError(RuntimeError):
    """The database and the mode of the instance do not go together."""


async def marker(db: AsyncSession) -> dict[str, Any] | None:
    row = await db.get(InstanceSetting, MARKER_KEY)
    return row.value if row is not None else None


async def _person_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Person))).scalar_one()


async def _fill(db: AsyncSession, settings: Settings, *, reset: bool) -> None:
    from grip.dev import seed

    await seed.seed(db, settings=settings, reset=reset)
    now = clock.now()
    db.add(
        InstanceSetting(
            key=MARKER_KEY,
            value={"seeded_at": now.isoformat(), "reset": reset},
        )
    )
    record_audit(
        db,
        actor=None,
        action=CREATE,
        entity="instance_setting",
        entity_id=MARKER_KEY,
        new_value={"key": MARKER_KEY, "reset": reset},
    )


async def prepare(db: AsyncSession, settings: Settings) -> str:
    """Bring database and mode in line at start, or refuse. Returns what was done.

    The caller commits.
    """
    marked = await marker(db)
    if not settings.is_example:
        if marked is not None:
            raise ExampleModeError(
                "Deze database is gevuld als voorbeeld en kan niet worden gebruikt "
                "voor echt werk. Een voorbeeldinstantie gooi je weg; begin een "
                "echte instantie op een lege database."
            )
        return "normal"
    # Two replicas may start at once: one fills, the other waits and finds
    # the marker.
    await db.execute(text("select pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
    marked = await marker(db)
    if marked is not None:
        return "kept"
    if await _person_count(db):
        raise ExampleModeError(
            "INSTANCE_MODE=voorbeeld kan alleen op een lege database: deze bevat "
            "al personen. Een voorbeeldinstantie krijgt een eigen, lege database."
        )
    await _fill(db, settings, reset=False)
    logger.info("Example instance: the example data was loaded")
    return "seeded"


async def reset(db: AsyncSession, settings: Settings) -> None:
    """Back to the starting state: empty everything and load the example again.

    Only in an example instance, and only on a database that carries the
    marker. Sessions go too, so every visitor logs in again. The caller
    commits.
    """
    if not settings.is_example:
        raise ExampleModeError(
            "Terugzetten kan alleen in een voorbeeldinstantie "
            "(INSTANCE_MODE=voorbeeld)."
        )
    if await marker(db) is None:
        raise ExampleModeError(
            "Deze database draagt geen voorbeeldmarkering; er wordt niets teruggezet."
        )
    await _fill(db, settings, reset=True)
    logger.info("Example instance: back to the starting state")


def visitor_allowed(email: str, settings: Settings) -> bool:
    """Whether this verified address may enter the example instance."""
    address = email.strip().lower()
    if not address or "@" not in address:
        return False
    domain = address.rsplit("@", 1)[1]
    for entry in settings.example_visitors:
        if "@" in entry:
            if entry == address:
                return True
        elif entry.lstrip("@.") == domain:
            return True
    return False


async def default_person(db: AsyncSession) -> Person | None:
    """The example person a visitor looks as until they choose another."""
    return await PersonRepository(db).first_active_with_function(BEHEERDER)


def visitor_of(session: dict[str, Any]) -> dict[str, Any] | None:
    visitor = session.get(VISITOR_SESSION_KEY)
    return visitor if isinstance(visitor, dict) else None


def reset_due(last: datetime | None, settings: Settings) -> bool:
    """Whether the nightly reset must run now (the worker asks every minute)."""
    hour = settings.EXAMPLE_RESET_HOUR.strip()
    if not settings.is_example or not hour:
        return False
    local = clock.now().astimezone(clock.zone())
    if local.hour != int(hour):
        return False
    return last is None or clock.local_date(last) != local.date()


async def run_reset_loop(session_factory: Any, settings: Settings) -> None:
    """Put the example back to its starting state once a night (worker)."""
    import asyncio

    last: datetime | None = None
    while True:
        try:
            if reset_due(last, settings):
                async with session_factory() as db:
                    await reset(db, settings)
                    await db.commit()
                last = clock.now()
        except Exception:
            logger.exception("Example instance: the nightly reset failed")
        await asyncio.sleep(60)


async def _main() -> int:
    from grip.core.config import get_settings
    from grip.core.database import async_session, close_db

    settings = get_settings()
    try:
        async with async_session() as db:
            try:
                await reset(db, settings)
            except ExampleModeError as exc:
                print(f"Geweigerd: {exc}")
                return 1
            await db.commit()
        print("De voorbeeldinstantie staat weer in de beginstand.")
        return 0
    finally:
        await close_db()


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(_main()))
