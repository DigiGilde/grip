"""The example data: valid by construction, refuses where it should."""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.dev import seed as seed_module
from grip.dev.seed import (
    EMAIL_DOMAIN,
    PEOPLE,
    SeedRefusedError,
    describe,
    ensure_local_instance,
    seed,
)
from grip.models.assignment import Assignment
from grip.models.audit_log import AuditLog
from grip.models.person import Person
from grip.models.role import FUNCTIONS, PersonRole
from grip.services import events, pricing


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@pytest.fixture
async def seeded(db_session: AsyncSession):
    return await seed(db_session)


async def test_seeding_an_empty_database_succeeds(db_session, seeded):
    names = set((await db_session.execute(select(Assignment.name))).scalars().all())
    assert {"Opdracht Alfa 2026", "Opdracht Beta 2026"} <= names
    assert len(names) == 6
    statuses = dict(
        (await db_session.execute(select(Assignment.name, Assignment.status))).all()
    )
    assert statuses["Opdracht Gamma 2025"] == "completed"
    assert statuses["Opdracht Epsilon 2027"] == "quoted"
    assert statuses["Interne opdracht Kennisdeling 2026"] == "in_progress"
    assert seeded.counts["vacancies"] == 4
    # Everything went through the services, so the audit log is filled.
    audit_rows = (
        await db_session.execute(select(func.count()).select_from(AuditLog))
    ).scalar_one()
    assert audit_rows > 100


async def test_every_function_is_held_by_someone(db_session, seeded):
    held = set((await db_session.execute(select(PersonRole.role_id))).scalars().all())
    assert held == set(FUNCTIONS)


async def test_running_twice_refuses(db_session, seeded):
    with pytest.raises(SeedRefusedError):
        await seed(db_session)


async def test_reset_empties_and_seeds_again(db_session, seeded):
    again = await seed(db_session, reset=True)
    count = (
        await db_session.execute(select(func.count()).select_from(Assignment))
    ).scalar_one()
    assert count == 6
    assert again.people["bente.beheer"].id != seeded.people["bente.beheer"].id


def test_refuses_outside_local_development():
    settings = get_settings()
    deployed = settings.model_copy(update={"DEV_NO_AUTH": False})
    with pytest.raises(SeedRefusedError):
        ensure_local_instance(deployed)
    with_idp = settings.model_copy(
        update={"OIDC_ISSUER": "https://idp.voorbeeld.example/realms/x"}
    )
    with pytest.raises(SeedRefusedError):
        ensure_local_instance(with_idp)
    ensure_local_instance(settings)


async def test_totals_of_alfa_match_the_pricing_service(db_session, seeded):
    alfa = seeded.assignments["alfa"]
    overview = await pricing.assignment_overview(db_session, alfa.id)
    totals = await pricing.assignment_totals(db_session, alfa.id)
    assert sum(line.budgeted_cents for line in overview.lines) == totals.budgeted_cents
    assert overview.budgeted_cents == totals.budgeted_cents
    by_line = {line.budget_line_id: line for line in overview.lines}
    # 0.8 FTE in category D for twelve months at 18,000: the worked example.
    assert by_line[seeded.lines["alfa_productmanager"]].budgeted_cents == 17_280_000
    # 30 percent of the hosting forecast of 15,000 plus the tooling licences.
    fixed = by_line[seeded.lines["alfa_fixed"]]
    assert fixed.coverage_cents == 450_000 + 600_000
    # January and February are closed, so part of the inzet is realised.
    assert overview.realised_cents > 0
    assert overview.forecast_cents > 0
    assert overview.used_cents == totals.used_cents
    assert overview.available_cents == overview.budgeted_cents - overview.used_cents


async def test_the_promotion_gives_a_category_signal(db_session, seeded):
    signals = await pricing.category_signals(db_session, seeded.assignments["alfa"].id)
    assert signals, "the mid-year promotion should produce an R14 signal"


async def test_no_email_address_uses_a_real_domain(db_session, seeded):
    emails = (await db_session.execute(select(Person.email))).scalars().all()
    assert len(emails) == len(PEOPLE) + 1
    for email in emails:
        domain = email.rsplit("@", 1)[1]
        assert domain.endswith((".example", ".invalid")), email
    # Also every address written literally in the module.
    source = inspect.getsource(seed_module)
    for domain in re.findall(r"@([a-z0-9.-]+\.[a-z]{2,})", source):
        assert domain.endswith((".example", ".invalid")), domain
    assert EMAIL_DOMAIN.endswith(".example")


async def test_describe_lists_every_person_with_an_id(seeded):
    listing = describe(seeded)
    for example in PEOPLE:
        assert example.name in listing
        assert str(seeded.people[example.key].id) in listing
