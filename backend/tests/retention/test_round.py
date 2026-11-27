"""The daily retention round: its rules, its lock and its hour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.config import get_settings
from grip.events import stream
from grip.models.stream_event import StreamEvent
from grip.services import retention


@pytest.fixture
async def sessions(db_session: AsyncSession):
    """Sessions on the test's connection; a commit only releases a savepoint."""
    connection = await db_session.connection()

    def factory() -> AsyncSession:
        return AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

    return factory


def _write(db: AsyncSession, note: str) -> None:
    stream.append(
        db, subject=("rate_card", "retention-test"), action="update", note=note
    )


async def _notes(db: AsyncSession) -> list[tuple[str | None, str | None, str | None]]:
    rows = await db.execute(
        select(StreamEvent.note, StreamEvent.actor_kind, StreamEvent.actor_ref)
        .where(StreamEvent.subject_id == "retention-test")
        .order_by(StreamEvent.seq)
    )
    return [tuple(row) for row in rows]


def test_the_rules_and_their_order():
    assert [rule.__name__ for rule in retention.RULES] == [
        "close_unanswered_dossiers",
        "erase_old_events",
        "remove_withdrawn_prospects",
        "remove_closed_request_forms",
    ]


async def test_the_rules_run_in_order_and_a_failure_stops_none(
    sessions, db_session, monkeypatch
):
    ran: list[str] = []

    async def first(db: AsyncSession, now: datetime) -> int:
        ran.append("first")
        _write(db, "eerste")
        return 1

    async def broken(db: AsyncSession, now: datetime) -> int:
        ran.append("broken")
        _write(db, "kapot")
        await db.flush()
        raise RuntimeError("rule fails")

    async def last(db: AsyncSession, now: datetime) -> int:
        ran.append("last")
        _write(db, "laatste")
        return 3

    monkeypatch.setattr(retention, "RULES", (first, broken, last))
    outcome = await retention.run_once(sessions, get_settings())

    assert ran == ["first", "broken", "last"]
    assert outcome.ran is True
    assert outcome.counts == {"first": 1, "last": 3}
    assert outcome.failed == ["broken"]
    # What the failing rule wrote went with its transaction; the others say
    # the job did it.
    assert await _notes(db_session) == [
        ("eerste", "system", "retention"),
        ("laatste", "system", "retention"),
    ]


async def test_the_real_rules_run_on_a_quiet_instance(sessions):
    outcome = await retention.run_once(sessions, get_settings())
    assert outcome.failed == []
    assert outcome.counts == {
        "close_unanswered_dossiers": 0,
        "erase_old_events": 0,
        "remove_withdrawn_prospects": 0,
        "remove_closed_request_forms": 0,
    }


async def test_the_rules_get_the_moment_of_the_round(sessions, monkeypatch):
    seen: list[datetime] = []

    async def rule(db: AsyncSession, now: datetime) -> int:
        seen.append(now)
        return 0

    monkeypatch.setattr(retention, "RULES", (rule,))
    moment = datetime(2026, 11, 25, 3, 0, tzinfo=UTC)
    await retention.run_once(sessions, get_settings(), now=moment)
    with clock.at(moment):
        await retention.run_once(sessions, get_settings())
    assert seen == [moment, moment]


async def test_a_second_worker_leaves_the_round_to_the_first(
    sessions, monkeypatch, _test_engine
):
    ran: list[str] = []

    async def rule(db: AsyncSession, now: datetime) -> int:
        ran.append("rule")
        return 0

    monkeypatch.setattr(retention, "RULES", (rule,))
    async with _test_engine.connect() as other:
        await other.begin()
        await other.execute(
            text("select pg_advisory_xact_lock(:key)"), {"key": retention._LOCK_KEY}
        )
        outcome = await retention.run_once(sessions, get_settings())
        await other.rollback()

    assert outcome.ran is False
    assert ran == []
    assert (await retention.run_once(sessions, get_settings())).ran is True
    assert ran == ["rule"]


def _hour(value: str):
    return get_settings().model_copy(update={"RETENTION_HOUR": value})


def _at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("moment", "due"),
    [
        # Winter: Amsterdam is UTC+1.
        (_at(2026, 1, 15, 2, 59), False),
        (_at(2026, 1, 15, 3, 0), True),
        (_at(2026, 1, 15, 3, 59), True),
        (_at(2026, 1, 15, 4, 0), False),
        # Summer: Amsterdam is UTC+2.
        (_at(2026, 7, 15, 1, 59), False),
        (_at(2026, 7, 15, 2, 0), True),
        (_at(2026, 7, 15, 3, 0), False),
    ],
)
def test_the_round_is_due_in_its_hour_on_the_instance_calendar(moment, due):
    assert get_settings().INSTANCE_TIMEZONE == "Europe/Amsterdam"
    with clock.at(moment):
        assert retention.retention_due(None, _hour("4")) is due


def test_the_round_runs_once_a_day():
    settings = _hour("4")
    with clock.at(_at(2026, 1, 15, 3, 30)):
        assert not retention.retention_due(_at(2026, 1, 15, 3, 1), settings)
        assert retention.retention_due(_at(2026, 1, 14, 3, 1), settings)


def test_the_day_of_the_last_round_is_a_day_of_the_instance():
    settings = _hour("0")
    # 00:30 on the 15th in Amsterdam is still the 14th in UTC.
    with clock.at(_at(2026, 1, 14, 23, 30)):
        assert retention.retention_due(_at(2026, 1, 14, 0, 0), settings)
        assert not retention.retention_due(_at(2026, 1, 14, 23, 5), settings)


def test_an_empty_hour_switches_the_round_off():
    with clock.at(_at(2026, 1, 15, 3, 30)):
        assert not retention.retention_due(None, _hour(""))
        assert not retention.retention_due(None, _hour("  "))


def test_the_default_hour_is_four():
    assert type(get_settings()).model_fields["RETENTION_HOUR"].default == "4"


def test_a_day_later_is_due_again():
    settings = _hour("4")
    first = _at(2026, 1, 15, 3, 0)
    with clock.at(first + timedelta(days=1)):
        assert retention.retention_due(first, settings)
