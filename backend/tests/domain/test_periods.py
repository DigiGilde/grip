"""Whose period a budget line and an allocation have."""

# The rows for the migration test are SQL, one row per line.
# ruff: noqa: E501

import os
import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from grip.calc import Month
from grip.core.config import get_settings
from grip.models.audit_log import AuditLog
from grip.services import (
    assignments,
    budget_intent,
    month_close,
    periods,
    pricing,
    quotes,
)
from grip.services.errors import DomainValidationError
from grip.services.periods import PeriodChangeBlockedError
from grip.services.pricing import MissingPeriodError

BACKEND = Path(__file__).resolve().parents[2]
YEAR = (date(2026, 1, 1), date(2026, 12, 31))


async def _line(db_session, assignment, actor, **kwargs):
    values = dict(
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        rate_category="D",
    )
    values.update(kwargs)
    return await assignments.add_budget_line(
        db_session, assignment.id, actor=actor, **values
    )


async def _allocate(db_session, line, person, actor, **kwargs):
    kwargs.setdefault("fte_pct", Decimal(50))
    return await assignments.add_allocation(
        db_session, line.id, person.id, actor=actor, **kwargs
    )


# -- following and deviating -----------------------------------------------------------


async def test_a_line_follows_the_assignment_unless_it_gets_its_own_dates(
    db_session, rate_cards, beheerder, make_assignment
):
    assignment = await make_assignment(end_date=YEAR[1])

    following = await _line(db_session, assignment, beheerder)
    same_dates = await _line(
        db_session, assignment, beheerder, start_date=YEAR[0], end_date=YEAR[1]
    )
    own = await _line(
        db_session,
        assignment,
        beheerder,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 9, 30),
    )
    forced_own = await _line(
        db_session,
        assignment,
        beheerder,
        period_source="own",
        start_date=YEAR[0],
        end_date=YEAR[1],
    )
    ignores_dates = await _line(
        db_session,
        assignment,
        beheerder,
        period_source="assignment",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 9, 30),
    )
    fixed = await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=100,
        year=2026,
        actor=beheerder,
    )

    assert [
        (line.period_source, line.start_date, line.end_date)
        for line in (following, same_dates, own, forced_own, ignores_dates)
    ] == [
        ("assignment", *YEAR),
        ("assignment", *YEAR),
        ("own", date(2026, 4, 1), date(2026, 9, 30)),
        ("own", *YEAR),
        ("assignment", *YEAR),
    ]
    assert fixed.period_source == "own"
    with pytest.raises(DomainValidationError, match="eigen periode"):
        await _line(db_session, assignment, beheerder, period_source="own")
    with pytest.raises(DomainValidationError, match="Onbekende bron"):
        await _line(db_session, assignment, beheerder, period_source="quarter")


async def test_changing_the_source_of_a_line(
    db_session, rate_cards, beheerder, make_assignment
):
    assignment = await make_assignment(end_date=YEAR[1])
    line = await _line(db_session, assignment, beheerder)

    # Dates sent make the period the line's own ...
    await assignments.update_budget_line(
        db_session, line.id, actor=beheerder, end_date=date(2026, 6, 30)
    )
    assert (line.period_source, line.end_date) == ("own", date(2026, 6, 30))
    # ... another field leaves it alone ...
    await assignments.update_budget_line(
        db_session, line.id, actor=beheerder, fte=Decimal("0.5")
    )
    assert line.period_source == "own"
    # ... and following again takes the assignment's dates back.
    await assignments.update_budget_line(
        db_session, line.id, actor=beheerder, period_source="assignment"
    )
    assert (line.period_source, line.start_date, line.end_date) == ("assignment", *YEAR)
    # Own, keeping the dates it had.
    await assignments.update_budget_line(
        db_session, line.id, actor=beheerder, period_source="own"
    )
    assert (line.period_source, line.start_date, line.end_date) == ("own", *YEAR)


async def test_inzet_follows_its_line_unless_it_gets_its_own_dates(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    assignment = await make_assignment(end_date=YEAR[1])
    line = await _line(db_session, assignment, beheerder)
    people = [await make_person(14) for _ in range(3)]

    following = await _allocate(db_session, line, people[0], beheerder)
    own = await _allocate(
        db_session,
        line,
        people[1],
        beheerder,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
    )
    same = await _allocate(
        db_session, line, people[2], beheerder, start_date=YEAR[0], end_date=YEAR[1]
    )
    assert [
        (a.period_source, a.start_date, a.end_date) for a in (following, own, same)
    ] == [
        ("line", *YEAR),
        ("own", date(2026, 3, 1), date(2026, 5, 31)),
        ("line", *YEAR),
    ]

    # The line gets a period of its own: followers move, the deviating one stays.
    await assignments.update_budget_line(
        db_session,
        line.id,
        actor=beheerder,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 10, 31),
    )
    assert (following.start_date, following.end_date) == (
        date(2026, 2, 1),
        date(2026, 10, 31),
    )
    assert (own.start_date, own.end_date) == (date(2026, 3, 1), date(2026, 5, 31))

    # Changing dates of inzet makes it deviate; "line" brings it back.
    await assignments.update_allocation(
        db_session, following.id, actor=beheerder, end_date=date(2026, 8, 31)
    )
    assert following.period_source == "own"
    await assignments.update_allocation(
        db_session, following.id, actor=beheerder, period_source="line"
    )
    assert (following.period_source, following.end_date) == ("line", date(2026, 10, 31))
    await assignments.update_allocation(
        db_session, following.id, actor=beheerder, fte_pct=Decimal(40)
    )
    assert following.period_source == "line"


# -- the assignment's period changes -------------------------------------------------------


async def test_assignment_period_moves_followers_and_is_audited_once(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    assignment = await make_assignment(end_date=YEAR[1])
    following = await _line(db_session, assignment, beheerder)
    own = await _line(
        db_session,
        assignment,
        beheerder,
        description="Developer",
        role="Developer",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 9, 30),
    )
    person, other = await make_person(14), await make_person(14)
    with_line = await _allocate(db_session, following, person, beheerder)
    with_own_dates = await _allocate(
        db_session,
        following,
        other,
        beheerder,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
    )
    on_own_line = await _allocate(db_session, own, other, beheerder)
    before = (
        await pricing.assignment_overview(db_session, assignment.id)
    ).budgeted_cents

    new = (date(2026, 2, 1), date(2026, 11, 30))
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, start_date=new[0], end_date=new[1]
    )

    assert (following.start_date, following.end_date) == new
    assert (with_line.start_date, with_line.end_date) == new
    assert (own.start_date, own.end_date) == (date(2026, 4, 1), date(2026, 9, 30))
    assert (with_own_dates.start_date, with_own_dates.end_date) == (
        date(2026, 3, 1),
        date(2026, 5, 31),
    )
    assert (on_own_line.start_date, on_own_line.end_date) == (
        date(2026, 4, 1),
        date(2026, 9, 30),
    )
    after = (
        await pricing.assignment_overview(db_session, assignment.id)
    ).budgeted_cents
    assert before - after == round(2 * 0.8 * 18_000_00)  # two months shorter

    await db_session.flush()
    rows = list(
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity.in_(("assignment", "budget_line", "allocation"))
                )
            )
        ).scalars()
    )
    moves = [r for r in rows if (r.new_value or {}).get("moved_budget_lines")]
    assert len(moves) == 1 and moves[0].entity == "assignment"
    assert moves[0].new_value["moved_budget_lines"] == [str(following.id)]
    assert moves[0].new_value["moved_allocations"] == [str(with_line.id)]
    assert moves[0].old_value["start_date"] == "2026-01-01"
    # No separate rows for the lines and inzet that moved along.
    assert not [
        r
        for r in rows
        if r.entity in ("budget_line", "allocation") and r.action == "update"
    ]


async def test_closed_month_blocks_a_change_of_the_assignment_period(
    db_session, rate_cards, beheerder, make_person, make_assignment, accept
):
    assignment = await make_assignment(end_date=YEAR[1])
    line = await _line(db_session, assignment, beheerder)
    allocation = await _allocate(db_session, line, await make_person(14), beheerder)
    await accept(assignment)
    await month_close.close_month(
        db_session, assignment.id, Month(2026, 1), actor=beheerder
    )

    with pytest.raises(PeriodChangeBlockedError) as blocked:
        await assignments.update_assignment(
            db_session, assignment.id, actor=beheerder, start_date=date(2026, 2, 1)
        )
    message = str(blocked.value)
    assert "inzet op 'Productmanager'" in message
    assert "afgesloten maand 2026-01" in message
    assert "Heropen de maand, of geef die inzet een eigen periode" in message
    # Nothing changed, not the assignment, not the line, not the inzet.
    assert assignment.start_date == YEAR[0]
    assert (line.start_date, allocation.start_date) == (YEAR[0], YEAR[0])

    # A change outside the closed month goes through.
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, end_date=date(2026, 10, 31)
    )
    assert (line.end_date, allocation.end_date) == (date(2026, 10, 31),) * 2

    # With a period of its own the inzet stays, and the rest may move.
    await assignments.update_allocation(
        db_session, allocation.id, actor=beheerder, period_source="own"
    )
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, start_date=date(2026, 2, 1)
    )
    assert line.start_date == date(2026, 2, 1)
    assert allocation.start_date == YEAR[0]


async def test_issued_quote_keeps_the_period_it_was_issued_with(
    db_session, rate_cards, beheerder, make_assignment
):
    assignment = await make_assignment(end_date=YEAR[1])
    await _line(db_session, assignment, beheerder)
    quote = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    issued_bytes, issued_hash = bytes(quote.canonical), quote.snapshot_hash
    assert quote.snapshot["lines"][0]["period"] == {
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    }

    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, end_date=date(2026, 6, 30)
    )

    assert bytes(quote.canonical) == issued_bytes
    assert quote.snapshot_hash == issued_hash
    assert quote.snapshot["lines"][0]["period"]["end_date"] == "2026-12-31"
    assert quote.total_cents == 172_800_00
    # What would be issued now does follow the new period.
    preview = await quotes.build_snapshot(db_session, assignment)
    assert preview["lines"][0]["period"]["end_date"] == "2026-06-30"
    assert "period_source" not in str(preview)


# -- an assignment without a period --------------------------------------------------------------


async def test_line_on_an_assignment_without_period_waits_and_is_not_priced(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    assignment = await make_assignment(start_date=None)
    person = await make_person(14)

    line = await _line(db_session, assignment, beheerder)
    assert (line.period_source, line.start_date, line.end_date) == (
        "assignment",
        None,
        None,
    )
    waiting = await periods.lines_without_period(db_session, assignment.id)
    assert [w.id for w in waiting] == [line.id]
    # Not priced, and never as zero.
    with pytest.raises(MissingPeriodError):
        await pricing.assignment_overview(db_session, assignment.id)
    # No inzet on it yet, unless that has dates of its own.
    with pytest.raises(DomainValidationError, match="nog geen periode"):
        await _allocate(db_session, line, person, beheerder)
    # No quote, with the same thing to do.
    with pytest.raises(MissingPeriodError):
        await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    with pytest.raises(DomainValidationError, match="Vul eerst de periode"):
        await assignments.transition(
            db_session, assignment.id, "quoted", actor=beheerder
        )
    # Half a period is no period.
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, start_date=YEAR[0]
    )
    assert line.start_date is None

    # One action prices every following line.
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, end_date=YEAR[1]
    )
    assert (line.start_date, line.end_date) == YEAR
    overview = await pricing.assignment_overview(db_session, assignment.id)
    assert overview.budgeted_cents == 172_800_00
    await quotes.issue_quote(db_session, assignment.id, actor=beheerder)


async def test_reservation_waits_for_the_period_of_the_assignment(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    assignment = await make_assignment(start_date=None)
    person = await make_person(14)
    line = await budget_intent.add_line(
        db_session,
        assignment.id,
        actor=beheerder,
        intended_person_id=person.id,
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
    )
    assert line.rate_category == "D"  # what the person bills now
    assert await budget_intent.reservation_of(db_session, line.id) is None

    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, start_date=YEAR[0], end_date=YEAR[1]
    )
    reservation = await budget_intent.reservation_of(db_session, line.id)
    assert reservation is not None
    assert (
        reservation.period_source,
        reservation.start_date,
        reservation.end_date,
    ) == (
        "line",
        *YEAR,
    )
    # And it keeps following.
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, end_date=date(2026, 9, 30)
    )
    assert reservation.end_date == date(2026, 9, 30)


async def test_period_cannot_be_emptied_under_following_inzet(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    assignment = await make_assignment(end_date=YEAR[1])
    line = await _line(db_session, assignment, beheerder)
    await _allocate(db_session, line, await make_person(14), beheerder)

    with pytest.raises(DomainValidationError, match="kan daarom niet leeg worden"):
        await assignments.update_assignment(
            db_session, assignment.id, actor=beheerder, end_date=None
        )
    assert assignment.end_date == YEAR[1] and line.end_date == YEAR[1]


async def test_derive_respects_a_following_line(
    db_session, rate_cards, make_person, make_assignment
):
    person = await make_person(14)
    with_period = await make_assignment(end_date=YEAR[1])
    without = await make_assignment("Zonder periode", start_date=None)

    derived = await budget_intent.derive(
        db_session,
        with_period.id,
        person.id,
        period_source="assignment",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 9, 30),
    )
    assert (derived.start_date, derived.end_date) == YEAR
    assert derived.period_source == "assignment"

    waiting = await budget_intent.derive(
        db_session,
        without.id,
        person.id,
        period_source="assignment",
        today=date(2026, 5, 10),
    )
    assert (waiting.start_date, waiting.end_date, waiting.period_source) == (
        None,
        None,
        None,
    )
    assert periods.NO_PERIOD_MESSAGE in waiting.notes
    assert waiting.fte is None
    assert waiting.rate_category == "D"


# -- the migration ---------------------------------------------------------------------------------


async def test_migration_sorts_existing_rows_into_following_and_deviating():
    """Rows from before 0020: equal dates follow, other dates deviate."""
    url = make_url(get_settings().DATABASE_URL)
    scratch = f"grip_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{scratch}"'))
    env = {
        **os.environ,
        "DEV_NO_AUTH": "1",
        "DATABASE_URL": url.set(database=scratch).render_as_string(hide_password=False),
    }

    def alembic(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    try:
        alembic("upgrade", "0019_person_roles")
        engine = create_async_engine(url.set(database=scratch))
        async with engine.begin() as conn:
            for statement in (
                """
                    INSERT INTO person (id, name, email)
                    VALUES ('00000000-0000-0000-0000-0000000000a1', 'Persoon', 'p@example.org');
                    INSERT INTO assignment (id, uri, name, start_date, end_date) VALUES
                      ('00000000-0000-0000-0000-000000000001', 'https://x.example/1', 'Met periode', '2026-01-01', '2026-12-31'),
                      ('00000000-0000-0000-0000-000000000002', 'https://x.example/2', 'Zonder periode', NULL, NULL);
                    INSERT INTO budget_line (id, assignment_id, description, kind, fte, rate_category, start_date, end_date) VALUES
                      ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000001', 'Gelijk', 'personnel', 1, 'D', '2026-01-01', '2026-12-31'),
                      ('00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000001', 'Afwijkend', 'personnel', 1, 'D', '2026-03-01', '2026-12-31'),
                      ('00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000002', 'Geen opdrachtperiode', 'personnel', 1, 'D', '2026-01-01', '2026-12-31');
                    INSERT INTO budget_line (id, assignment_id, description, kind, amount_cents, year) VALUES
                      ('00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000001', 'Vast', 'fixed', 100, 2026);
                    INSERT INTO allocation (id, person_id, budget_line_id, start_date, end_date, fte_pct) VALUES
                      ('00000000-0000-0000-0000-000000000021', '00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-000000000011', '2026-01-01', '2026-12-31', 50),
                      ('00000000-0000-0000-0000-000000000022', '00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-000000000011', '2026-02-01', '2026-12-31', 10),
                      ('00000000-0000-0000-0000-000000000023', '00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-000000000012', '2026-03-01', '2026-12-31', 10);
                    """
            ).split(";"):
                if statement.strip():
                    await conn.execute(text(statement))
        await engine.dispose()

        alembic("upgrade", "0020_period_source")

        engine = create_async_engine(url.set(database=scratch))
        async with engine.connect() as conn:
            lines = dict(
                (
                    await conn.execute(
                        text("SELECT description, period_source FROM budget_line")
                    )
                ).all()
            )
            allocations = dict(
                (
                    await conn.execute(
                        text("SELECT right(id::text, 2), period_source FROM allocation")
                    )
                ).all()
            )
            dates = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM budget_line WHERE kind = 'personnel' AND start_date IS NULL"
                    )
                )
            ).scalar_one()
        await engine.dispose()
        assert lines == {
            "Gelijk": "assignment",
            "Afwijkend": "own",
            "Geen opdrachtperiode": "own",
            "Vast": "own",
        }
        assert allocations == {"21": "line", "22": "own", "23": "line"}
        assert dates == 0  # every existing line keeps its dates
        alembic("downgrade", "0019_person_roles")
    finally:
        async with admin.connect() as conn:
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            )
        await admin.dispose()
