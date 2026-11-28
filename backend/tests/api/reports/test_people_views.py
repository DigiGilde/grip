"""Which views of the people a reader has: only those that show something."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select

from grip.models.stream_event import StreamEvent
from grip.services import assignments

ALL = ["list", "board", "occupancy", "billability"]


async def _views(person, as_person):
    response = await as_person(person).get("/api/people/views")
    assert response.status_code == 200, response.text
    return response.json()["views"]


async def _reads(db_session) -> int:
    await db_session.flush()
    return await db_session.scalar(
        select(func.count())
        .select_from(StreamEvent)
        .where(StreamEvent.type == "data.read")
    )


@pytest.mark.parametrize(
    ("who", "views"),
    [
        ("beheerder", ALL),
        ("planner", ["list", "board", "occupancy"]),
        ("leader", ALL),
        # Their own figure lives on the page of the person, not in a view.
        ("member", ["list", "board", "occupancy"]),
        ("owner", ["list", "board"]),
        ("lezer", ["list"]),
        ("outsider", ["list"]),
    ],
)
async def test_a_reader_gets_the_views_they_have_something_in(
    as_person, world, who, views
):
    assert await _views(getattr(world, who), as_person) == views


async def test_the_views_follow_the_blocks_of_the_steering_overview(as_person, world):
    """Bezetting is offered exactly when its block would be in the overview;
    Declarabiliteit only when the block holds someone besides the reader."""
    for person in (
        world.beheerder,
        world.planner,
        world.leader,
        world.member,
        world.owner,
        world.lezer,
        world.outsider,
    ):
        views = await _views(person, as_person)
        steering = (
            await as_person(person).get("/api/reports/steering", params={"year": 2026})
        ).json()
        assert ("occupancy" in views) == ("occupancy" in steering), person.name
        if "billability" in views:
            assert "billability" in steering, person.name
            others = [
                row
                for row in steering["billability"]["persons"]
                if row["person_id"] != str(person.id)
            ]
            assert others, person.name


async def test_asking_for_the_views_is_no_read_of_a_figure(
    as_person, world, db_session
):
    """The log says who read a billability figure. A menu that is opened is
    not that, for any reader."""
    # The control: the overview does write the read, so the count can see it.
    before = await _reads(db_session)
    await as_person(world.beheerder).get("/api/reports/steering", params={"year": 2026})
    assert await _reads(db_session) > before

    for person in (
        world.beheerder,
        world.leader,
        world.member,
        world.planner,
        world.owner,
        world.lezer,
        world.outsider,
    ):
        before = await _reads(db_session)
        await _views(person, as_person)
        assert await _reads(db_session) == before, person.name


async def test_the_views_carry_nothing_but_their_names(as_person, world):
    response = await as_person(world.planner).get("/api/people/views")
    assert set(response.json()) == {"views"}
    assert "Mila" not in response.text and "cents" not in response.text


READERS = ("beheerder", "planner", "leader", "member", "owner", "lezer", "outsider")


async def test_the_board_is_offered_exactly_when_the_board_has_something(
    as_person, world
):
    for who in READERS:
        person = getattr(world, who)
        board = (await as_person(person).get("/api/allocations/board")).json()
        shown = "board" in await _views(person, as_person)
        assert shown == bool(board["persons"] or board["open_roles"]), who


async def _statements(as_person, person, db_session) -> int:
    engine = db_session.bind.sync_engine
    count = 0

    def _count(*_):
        nonlocal count
        count += 1

    await _views(person, as_person)
    event.listen(engine, "before_cursor_execute", _count)
    try:
        await _views(person, as_person)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return count


async def test_the_views_cost_a_few_statements_however_much_there_is(
    as_person, world, db_session, create_person
):
    first = {
        who: await _statements(as_person, getattr(world, who), db_session)
        for who in READERS
    }
    assert max(first.values()) <= 16, first
    for index in range(10):
        extra = await create_person(f"extra{index}@example.org", name=f"Extra {index}")
        assignment = await assignments.create_assignment(
            db_session, name=f"Opdracht Extra {index}", actor=world.owner
        )
        line = await assignments.add_budget_line(
            db_session,
            assignment.id,
            description="Adviseur",
            kind="personnel",
            role="Adviseur",
            fte=Decimal("1"),
            rate_category="D",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            actor=world.owner,
        )
        await assignments.add_allocation(
            db_session,
            line.id,
            extra.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            fte_pct=Decimal("10"),
            actor=world.owner,
        )
    await db_session.flush()
    for who in READERS:
        now = await _statements(as_person, getattr(world, who), db_session)
        assert now <= first[who] + 5, (who, first[who], now)
