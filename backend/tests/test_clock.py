"""One rule for "today": the day on the instance's calendar.

The same scenario at 23:30 and at 00:30 local time, on a month boundary and
around both changes of daylight saving. Between local midnight and the offset
of the zone the day in UTC is still yesterday; nothing in the domain may use
that day.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core import clock
from grip.repositories.person import PersonRepository
from grip.services import team

AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def local(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=AMSTERDAM)


@pytest.mark.parametrize(
    ("moment", "day"),
    [
        # A month boundary in winter time (UTC+1).
        (local(2026, 10, 31, 23, 30), date(2026, 10, 31)),
        (local(2026, 11, 1, 0, 30), date(2026, 11, 1)),
        # A year boundary.
        (local(2026, 12, 31, 23, 30), date(2026, 12, 31)),
        (local(2027, 1, 1, 0, 30), date(2027, 1, 1)),
        # The night the clock goes forward (29 March 2026) and the day after.
        (local(2026, 3, 28, 23, 30), date(2026, 3, 28)),
        (local(2026, 3, 29, 0, 30), date(2026, 3, 29)),
        (local(2026, 3, 30, 0, 30), date(2026, 3, 30)),
        # The night the clock goes back (25 October 2026): summer time, UTC+2.
        (local(2026, 10, 24, 23, 30), date(2026, 10, 24)),
        (local(2026, 10, 25, 0, 30), date(2026, 10, 25)),
        (local(2026, 10, 25, 23, 30), date(2026, 10, 25)),
    ],
)
def test_today_is_the_local_day(moment: datetime, day: date) -> None:
    with clock.at(moment):
        assert clock.today() == day
        assert clock.local_date(clock.now()) == day
        assert clock.now().tzinfo is UTC or clock.now().utcoffset().total_seconds() == 0


def test_the_utc_day_differs_just_after_local_midnight() -> None:
    """The case that broke: 00:30 local is still yesterday in UTC."""
    moment = local(2026, 11, 1, 0, 30)
    with clock.at(moment):
        assert clock.now().date() == date(2026, 10, 31)
        assert clock.today() == date(2026, 11, 1)
        assert Month.of(clock.today()) == Month(2026, 11)


def test_an_instant_is_dated_on_the_local_calendar() -> None:
    stored = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
    assert clock.local_date(stored) == date(2027, 1, 1)
    # An instant read back without its zone is UTC, as it was stored.
    assert clock.local_date(stored.replace(tzinfo=None)) == date(2027, 1, 1)


def test_the_clock_takes_no_naive_moment() -> None:
    with pytest.raises(ValueError), clock.at(datetime(2026, 1, 1, 0, 0)):
        pass


@pytest.mark.parametrize(
    "moment",
    [
        local(2026, 10, 31, 23, 30),
        local(2026, 11, 1, 0, 30),
        local(2026, 3, 29, 0, 30),
        local(2026, 10, 25, 0, 30),
    ],
)
async def test_a_right_granted_now_counts_now(
    db_session: AsyncSession, create_person, moment: datetime
) -> None:
    """Granting and reading use the same day, whatever the hour."""
    beheerder = await create_person("beheer@example.org", functions=["beheerder"])
    person = await create_person("nieuw@example.org")
    with clock.at(moment):
        await team.grant_function(db_session, person.id, "planner", actor=beheerder)
        held = await team.functions_by_person(db_session)
        assert held.get(person.id) == ["planner"]
        repo = PersonRepository(db_session)
        assert await repo.active_function_ids(person.id) == ["planner"]
        grants = await team.function_grants_by_person(db_session)
        assert grants[person.id][0].since == clock.today()


async def test_a_right_revoked_today_is_gone_today_on_a_month_boundary(
    db_session: AsyncSession, create_person
) -> None:
    beheerder = await create_person("beheer@example.org", functions=["beheerder"])
    person = await create_person("oud@example.org")
    with clock.at(local(2026, 10, 30, 12, 0)):
        await team.grant_function(db_session, person.id, "lezer", actor=beheerder)
    # 00:30 on the first of the month: the day in UTC is still the 31st.
    with clock.at(local(2026, 11, 1, 0, 30)):
        await team.revoke_function(db_session, person.id, "lezer", actor=beheerder)
        assert (await team.functions_by_person(db_session)).get(person.id) is None
    # Half an hour earlier it was still held.
    with clock.at(local(2026, 10, 31, 23, 30)):
        assert (await team.functions_by_person(db_session)).get(person.id) == ["lezer"]


def test_no_code_asks_another_clock_for_the_day() -> None:
    """Every "today" comes from the one clock.

    The task layer is converted separately; until then its files are named
    here so that the list can only shrink.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "grip"
    pending = {"api/routes/tasks.py", "tasks/backfill.py", "tasks/loop.py"}
    other_clock = re.compile(
        r"\bdate\.today\(\)|datetime\.now\((UTC|timezone\.utc)?\)\.date\(\)"
        r"|\butcnow\(\)|default=date\.today\b"
    )
    found = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "migrations" not in path.parts
        and path.name != "clock.py"
        # A stand-in for another system has its own clock.
        and "corpus_standin" not in path.parts
        and other_clock.search(path.read_text())
    )
    assert set(found) <= pending, sorted(set(found) - pending)
