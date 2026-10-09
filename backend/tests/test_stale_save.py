"""A save on top of someone else's change is refused, per kind of record.

All names and amounts are fictional.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from grip.services import assignments, costs, rates, stale
from grip.services.stale import StaleWriteError, parse


def test_the_header_names_a_record_and_its_version():
    assert parse('"abc:3"') == ("abc", 3)
    assert parse('W/"abc:3"') == ("abc", 3)
    assert parse("abc:3") == ("abc", 3)
    assert parse(None) is None
    assert parse('"abc"') is None
    assert parse('"abc:x"') is None


@pytest.fixture
async def things(db_session, create_person):
    db = db_session
    beheerder = await create_person(
        "beheer@example.org", name="Bea Beheerder", functions=["beheerder"]
    )
    await rates.create_rate_card(db, 2026, actor=beheerder)
    await rates.set_rate_band(db, 2026, "D", 1800000, actor=beheerder)
    await rates.set_scale_band(db, 2026, 14, "D", actor=beheerder)
    await rates.set_rate_card_status(db, 2026, "active", actor=beheerder)
    worker = await create_person("werker@example.org", name="Wim Werker")
    await rates.set_person_scale(db, worker.id, date(2026, 1, 1), 14, actor=beheerder)
    assignment = await assignments.create_assignment(
        db, name="Opdracht Voorbeeld", actor=beheerder, owner_id=beheerder.id
    )
    line = await assignments.add_budget_line(
        db,
        assignment.id,
        description="Developer",
        kind="personnel",
        role="Developer",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        actor=beheerder,
    )
    allocation = await assignments.add_allocation(
        db,
        line.id,
        worker.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("50"),
        actor=beheerder,
    )
    item = await costs.create_cost_item(
        db, description="Hosting", budgeted_cents=100000, actor=beheerder
    )
    await db.flush()
    return {
        "actor": beheerder,
        "assignment": assignment,
        "line": line,
        "allocation": allocation,
        "item": item,
    }


async def test_a_record_counts_its_changes(db_session, things):
    line = things["line"]
    assert line.version == 1
    await assignments.update_budget_line(
        db_session, line.id, actor=things["actor"], description="Tester"
    )
    await db_session.flush()
    assert line.version == 2


@pytest.mark.parametrize(
    "kind",
    ["assignment", "budget_line", "allocation", "cost_item"],
)
async def test_a_stale_save_is_refused_and_a_fresh_one_goes_through(
    db_session, things, kind
):
    db = db_session
    actor = things["actor"]

    async def change(text: str) -> None:
        if kind == "assignment":
            await assignments.update_assignment(
                db, things["assignment"].id, actor=actor, notes=text
            )
        elif kind == "budget_line":
            await assignments.update_budget_line(
                db, things["line"].id, actor=actor, description=text
            )
        elif kind == "allocation":
            await assignments.update_allocation(
                db,
                things["allocation"].id,
                actor=actor,
                fte_pct=Decimal("40") if text == "een" else Decimal("30"),
            )
        else:
            await costs.update_cost_item(
                db, things["item"].id, actor=actor, description=text
            )
        await db.flush()

    row = {
        "assignment": things["assignment"],
        "budget_line": things["line"],
        "allocation": things["allocation"],
        "cost_item": things["item"],
    }[kind]
    started_from = row.version

    # A colleague saves first.
    await change("een")
    assert row.version == started_from + 1

    # The save that started from the older version is refused, with nothing
    # written; the same save on the version of now goes through.
    with stale.expecting(f'"{row.id}:{started_from}"'):
        with pytest.raises(StaleWriteError) as refused:
            await change("twee")
    assert "intussen gewijzigd" in str(refused.value)
    assert "Er is niets overschreven" in str(refused.value)
    with stale.expecting(f'"{row.id}:{row.version}"'):
        await change("twee")
    assert row.version == started_from + 2

    # A header about another record does not stand in the way.
    with stale.expecting(f'"00000000-0000-0000-0000-000000000000:{started_from}"'):
        await change("een")


async def test_without_the_header_nothing_is_checked(db_session, things):
    await assignments.update_budget_line(
        db_session,
        things["line"].id,
        actor=things["actor"],
        description="Zonder kop",
    )
