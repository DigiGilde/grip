"""The programma dataset: a programme team with a budget of a ministry."""

from __future__ import annotations

import inspect
import re
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.dev.datasets import programma
from grip.dev.seed import SeedRefusedError, describe, seed
from grip.federation.models import FederationOutbox
from grip.models.assignment import Assignment, BudgetLine
from grip.models.cost import CostItem
from grip.models.organisation import Organisation
from grip.models.quote import Quote
from grip.repositories.domain import CostRepository
from grip.services import cost_references, events, pricing


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@pytest.fixture
async def seeded(db_session: AsyncSession):
    return await seed(db_session, dataset="programma")


async def test_the_dataset_follows_the_setting(db_session: AsyncSession):
    settings = get_settings().model_copy(update={"SEED_DATASET": "programma"})
    result = await seed(db_session, settings=settings)
    assert set(result.assignments) == {"programme", "portal", "hosting"}


async def test_an_unknown_dataset_is_refused_before_anything_happens(db_session):
    with pytest.raises(SeedRefusedError, match="programma"):
        await seed(db_session, dataset="bestaat-niet")


async def test_the_programme_and_its_suppliers(db_session, seeded):
    statuses = dict(
        (await db_session.execute(select(Assignment.name, Assignment.status))).all()
    )
    assert statuses == {
        "Voorbeeldprogramma 2026": "in_progress",
        "Ontwikkeling ondernemersportaal 2026": "in_progress",
        "Beheer en hosting 2026": "in_progress",
    }
    programme = seeded.assignments["programme"]
    for key in ("portal", "hosting"):
        given = seeded.assignments[key]
        assert given.parent_assignment_uri == programme.uri
        # The client side holds the received quote, not a budget of its own.
        lines = await db_session.execute(
            select(BudgetLine.id).where(BudgetLine.assignment_id == given.id)
        )
        assert lines.all() == []
        quote = (
            await db_session.execute(
                select(Quote).where(Quote.assignment_id == given.id)
            )
        ).scalar_one()
        assert quote.status == "accepted"
        assert quote.issued_by_id is None


async def test_organisations_match_the_instances(db_session, seeded):
    rows = {
        row.name: row
        for row in (await db_session.execute(select(Organisation))).scalars()
    }
    assert rows["Voorbeeldprogramma"].instance_uri == get_settings().INSTANCE_BASE_URI
    assert rows["Voorbeeldgilde"].instance_uri == programma.DIGIGILDE_INSTANCE_URI
    assert rows["Voorbeeldministerie"].instance_uri == programma.MINISTRY_INSTANCE_URI
    assert rows["Voorbeeldbeheerorganisatie"].instance_uri is None
    # The identifiers of the default dataset, so the instances agree.
    assert rows["Voorbeeldministerie"].tooi_uri.endswith("/ministerie/mnre9001")
    assert rows["Voorbeeldgilde"].tooi_uri.endswith("/oorg/oorg99002")


async def test_totals_of_the_programme_come_from_the_pricing_service(
    db_session, seeded
):
    programme = seeded.assignments["programme"]
    overview = await pricing.assignment_overview(db_session, programme.id)
    totals = await pricing.assignment_totals(db_session, programme.id)
    assert overview.budgeted_cents == totals.budgeted_cents
    assert overview.used_cents == totals.used_cents
    by_line = {line.budget_line_id: line for line in overview.lines}
    # 1 FTE in category E for twelve months at 21,500.
    assert by_line[seeded.lines["programme_manager"]].budgeted_cents == 25_800_000
    # Hotel (actual 3,864), fully covered. The zaalhuur waits for the guild:
    # it does not count, and the line says it is incomplete.
    events_line = by_line[seeded.lines["events"]]
    assert events_line.coverage_cents == 386_400
    assert events_line.incomplete_by == ("Voorbeeldgilde",)
    # January to September are closed, so part of the inzet is realised.
    assert overview.realised_cents > 0
    assert 0 < overview.used_cents < overview.budgeted_cents
    assert overview.available_cents == overview.budgeted_cents - overview.used_cents


async def test_describe_lists_the_programme_team(seeded):
    listing = describe(seeded)
    for example in programma.PEOPLE:
        assert example.name in listing
        assert str(seeded.people[example.key].id) in listing


def test_no_address_in_the_dataset_uses_a_real_domain():
    source = inspect.getsource(programma)
    for domain in re.findall(r"@([a-z0-9.-]+\.[a-z]{2,})", source):
        assert domain.endswith((".example", ".invalid")), domain


async def test_the_venue_is_asked_of_the_guild_and_nothing_is_sent(db_session, seeded):
    items = {
        item.description: item
        for item in (await db_session.execute(select(CostItem))).scalars()
    }
    guild = (
        await db_session.execute(
            select(Organisation).where(Organisation.name == "Voorbeeldgilde")
        )
    ).scalar_one()
    venue = items["Zaalhuur bijeenkomst ondernemers november"]
    assert venue.executor_organisation_id == guild.id
    assert (venue.request_status, venue.request_sequence) == ("waiting", 1)
    assert venue.request_period == date(2026, 11, 1)
    assert not venue.executor_has_item
    # A reference has no invoice lines of its own.
    assert await CostRepository(db_session).invoice_lines([venue.id]) == []
    # The request waits for the worker: the seed sends nothing.
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []
    assert [item.id for item in await cost_references.waiting(db_session)] == [venue.id]
    hotel = items["Hotelovernachtingen werksessie september"]
    assert hotel.executor_organisation_id is None
