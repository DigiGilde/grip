"""The datasets of the example chain: who is in them and what they hold."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.bootstrap import DEV_BEHEERDER_NAME
from grip.dev.datasets import bzk, chain, ezk, gdi, nldd, odi
from grip.dev.seed import describe, seed
from grip.federation.models import FederationOutbox
from grip.models.assignment import Assignment, BudgetLine
from grip.models.month_close import MonthClose
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.person_details import Hire, PersonScale
from grip.models.quote import Quote
from grip.models.rates import RateCard
from grip.models.role import PersonRole
from grip.services import events

MODULES = {"bzk": bzk, "gdi": gdi, "odi": odi, "ezk": ezk, "nldd": nldd}
# The assignments each instance is party to, and on which side.
SIDES = {
    "bzk": {"delegation": "contractor", "programme": "client", "execution": "client"},
    "gdi": {"delegation": "client"},
    "odi": {"execution": "contractor"},
    "ezk": {},
    "nldd": {"fundament": "client", "regelrecht": "client"},
}


async def _organisations(db: AsyncSession) -> dict[str, Organisation]:
    rows = (await db.execute(select(Organisation))).scalars()
    return {row.name: row for row in rows}


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


async def _functions(db: AsyncSession) -> dict[str, set[str]]:
    rows = await db.execute(
        select(Person.name, PersonRole.role_id).join(
            PersonRole, PersonRole.person_id == Person.id
        )
    )
    held: dict[str, set[str]] = {}
    for name, role in rows:
        held.setdefault(name, set()).add(role)
    return held


@pytest.mark.parametrize("name", list(MODULES))
async def test_the_people_and_their_rights(db_session: AsyncSession, name: str):
    module = MODULES[name]
    result = await seed(db_session, dataset=name)
    held = await _functions(db_session)
    for example in module.PEOPLE:
        assert held.get(example.name, set()) == set(example.functions), example.name
    names = set((await db_session.execute(select(Person.name))).scalars())
    # The stand-in beheerder of dev mode; an example instance has none.
    assert names - {DEV_BEHEERDER_NAME} == {example.name for example in module.PEOPLE}
    assert all(
        example.email.endswith("@voorbeeld.example") for example in module.PEOPLE
    )
    listing = describe(result)
    for example in module.PEOPLE:
        assert str(result.people[example.key].id) in listing


@pytest.mark.parametrize("name", list(MODULES))
async def test_no_rate_card_and_nobody_staffed(db_session: AsyncSession, name: str):
    """Only DigiGilde and MOZa price people; the others hold a fixed amount at
    most, or a quote they received."""
    await seed(db_session, dataset=name)
    for model in (RateCard, PersonScale, Hire):
        count = await db_session.scalar(select(func.count()).select_from(model))
        assert count == 0, model.__name__


@pytest.mark.parametrize("name", list(MODULES))
async def test_the_assignments_of_each_side(db_session: AsyncSession, name: str):
    result = await seed(db_session, dataset=name)
    assignments = {
        a.name: a for a in (await db_session.execute(select(Assignment))).scalars()
    }
    wanted = {chain.SHARED[key].name: side for key, side in SIDES[name].items()}
    assert set(assignments) == set(wanted)
    assert set(result.assignments) == set(SIDES[name])
    for title, side in wanted.items():
        assignment = assignments[title]
        assert assignment.status == "in_progress"
        assert assignment.shared_with_instance_uri
        lines = (
            (
                await db_session.execute(
                    select(BudgetLine).where(BudgetLine.assignment_id == assignment.id)
                )
            )
            .scalars()
            .all()
        )
        quote = (
            await db_session.execute(
                select(Quote).where(Quote.assignment_id == assignment.id)
            )
        ).scalar_one()
        assert quote.status == "accepted"
        if side == "client":
            # Received and signed here; the budget is the contractor's.
            assert lines == []
            assert quote.issued_by_id is None
        else:
            assert {line.kind for line in lines} == {"fixed"}
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []


async def test_ezk_is_the_parent_of_nldd(db_session: AsyncSession):
    await seed(db_session, dataset="ezk")
    rows = {
        row.name: row
        for row in (await db_session.execute(select(Organisation))).scalars()
    }
    assert rows["NLDD voorbeeld"].parent_id == rows["Ministerie van EZK voorbeeld"].id
    assert rows["NLDD voorbeeld"].unit_key == "nldd"


async def test_odi_is_the_parent_of_the_gilde(db_session: AsyncSession):
    await seed(db_session, dataset="odi")
    rows = {
        row.name: row
        for row in (await db_session.execute(select(Organisation))).scalars()
    }
    assert rows["Voorbeeldgilde"].parent_id == rows["ODI voorbeeld"].id
    # The gilde is a unit of ODI: the same TOOI URI and a key of its own.
    assert rows["Voorbeeldgilde"].tooi_uri == rows["ODI voorbeeld"].tooi_uri
    assert rows["ODI voorbeeld"].unit_key is None


async def test_moza_names_bzk_as_parent_and_client(db_session: AsyncSession):
    result = await seed(db_session, dataset="programma")
    rows = {
        row.name: row
        for row in (await db_session.execute(select(Organisation))).scalars()
    }
    ministry = rows["Ministerie van BZK voorbeeld"]
    assert rows["MOZa voorbeeld"].parent_id == ministry.id
    programme = result.assignments["programme"]
    assert programme.client_organisation_id == ministry.id
    assert programme.shared_with_instance_uri == chain.INSTANCES["ministerie"].local_uri
    assert programme.uri.startswith(chain.INSTANCES["ministerie"].local_uri)


async def test_the_gilde_runs_the_work_of_nldd(db_session: AsyncSession):
    result = await seed(db_session)
    assert result.counts["people"] == 19
    assert result.counts["assignments"] == 8
    assert result.counts["organisations"] == 5
    assert result.counts["hires"] == 2
    nldd_base = chain.INSTANCES["nldd"].local_uri
    for key in ("fundament", "regelrecht"):
        assignment = result.assignments[key]
        assert assignment.status == "in_progress"
        assert assignment.uri == f"{nldd_base}/id/opdracht/{chain.SHARED[key].id}"
        assert assignment.shared_with_instance_uri == nldd_base
        closed = set(
            (
                await db_session.execute(
                    select(MonthClose.month).where(
                        MonthClose.assignment_id == assignment.id
                    )
                )
            ).scalars()
        )
        assert closed == {date(2026, 8, 1), date(2026, 9, 1)}
    hire = (
        await db_session.execute(
            select(Hire).where(Hire.person_id == result.people["erik.extern"].id)
        )
    ).scalar_one()
    assert hire.supplier == "Voorbeeld Detachering B.V."
    rows = {
        row.name: row
        for row in (await db_session.execute(select(Organisation))).scalars()
    }
    assert rows["Voorbeeldgilde"].parent_id == rows["ODI voorbeeld"].id
    assert rows["NLDD voorbeeld"].instance_uri == nldd_base
    # Nothing waits for NLDD: its instance holds its own half.
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []
