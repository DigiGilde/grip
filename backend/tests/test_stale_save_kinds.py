"""Per kind of record people edit: two saves from the same version.

The first goes through; the second, which started from the same version, is
refused with who changed it and when (``grip.services.stale``). One test per
kind, at the service that carries the edit. The kinds whose edit lives in a
route (a task, a peer) and the ones that need a vacancy are in the API tests
next to their feature.

All names are fictional.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.vacancy_text_flow import (
    VacancyTextSharedSection,
    VacancyTextTemplate,
)
from grip.services import (
    assignments,
    billing_deliveries,
    function_framework,
    instance_settings,
    organisations,
    person_roles,
    rates,
    stale,
    team,
)
from grip.services.vacancies import library

Edit = Callable[[int], Awaitable[Any]]


async def _twice(key: Any, version: int, edit: Edit) -> stale.StaleWriteError:
    """Save twice from ``version``; give back the refusal of the second."""
    header = f'"{key}:{version}"'
    with stale.expecting(header):
        await edit(1)
    with stale.expecting(header), pytest.raises(stale.StaleWriteError) as refused:
        await edit(2)
    assert "intussen gewijzigd" in str(refused.value)
    assert "Er is niets overschreven" in str(refused.value)
    # On top of what stands there now it goes through.
    with stale.expecting(f'"{key}:{version + 1}"'):
        await edit(3)
    # And without the header nothing is checked.
    await edit(4)
    return refused.value


@pytest.fixture
async def beheerder(create_person):
    return await create_person(
        "beheer@example.org", name="Bea Beheerder", functions=["beheerder"]
    )


@pytest.fixture
async def colleague(create_person):
    return await create_person("collega@example.org", name="Carla Collega")


async def test_person_data(db_session: AsyncSession, beheerder, colleague) -> None:
    async def edit(n: int) -> None:
        await team.update_person(
            db_session, colleague.id, actor=beheerder, changes={"name": f"Carla {n}"}
        )

    await _twice(colleague.id, colleague.version, edit)


async def test_a_system_write_does_not_make_a_persons_form_stale(
    db_session: AsyncSession, beheerder, colleague
) -> None:
    started = colleague.version
    # What a login does: it writes the row, and is nobody's edit.
    colleague.oidc_subject = "subject-of-a-login"
    await db_session.flush()
    assert colleague.version == started
    with stale.expecting(f'"{colleague.id}:{started}"'):
        await team.update_person(
            db_session, colleague.id, actor=beheerder, changes={"name": "Carla C"}
        )
    assert colleague.version == started + 1


async def test_person_scale(db_session: AsyncSession, beheerder, colleague) -> None:
    await rates.create_rate_card(db_session, 2026, actor=beheerder)

    async def edit(n: int) -> None:
        await rates.set_person_scale(
            db_session, colleague.id, date(2026, n, 1), 10 + n, actor=beheerder
        )

    await _twice(colleague.id, colleague.version, edit)


async def test_person_hire(db_session: AsyncSession, beheerder, colleague) -> None:
    async def edit(n: int) -> None:
        await rates.add_hire(
            db_session,
            colleague.id,
            supplier=f"Voorbeeld Detachering {n}",
            cost_monthly_rate_cents=1_000_000,
            valid_from=date(2026, n, 1),
            valid_to=date(2026, n, 28),
            actor=beheerder,
        )

    await _twice(colleague.id, colleague.version, edit)


async def test_person_roles(db_session: AsyncSession, beheerder, colleague) -> None:
    async def edit(n: int) -> None:
        await person_roles.set_person_roles(
            db_session, colleague.id, [], actor=beheerder
        )

    await _twice(colleague.id, colleague.version, edit)


async def test_billability_target(
    db_session: AsyncSession, beheerder, colleague
) -> None:
    await rates.create_rate_card(db_session, 2026, actor=beheerder)
    target = await rates.set_billability_target(
        db_session, colleague.id, 2026, Decimal("80"), actor=beheerder
    )

    async def edit(n: int) -> None:
        await rates.set_billability_target(
            db_session, colleague.id, 2026, Decimal(80 + n), actor=beheerder
        )

    await _twice(rates.target_key(colleague.id, 2026), target.version, edit)


async def test_organisation(db_session: AsyncSession, beheerder) -> None:
    organisation = await organisations.create_manual_organisation(
        db_session, name="Voorbeeldstichting", actor=beheerder
    )

    async def edit(n: int) -> None:
        await organisations.update_organisation(
            db_session,
            organisation.id,
            {"name": f"Voorbeeldstichting {n}"},
            actor=beheerder,
        )

    await _twice(organisation.id, organisation.version, edit)


async def test_instance_settings(db_session: AsyncSession, beheerder) -> None:
    key = next(
        name
        for name, declared in instance_settings._declared.items()
        if isinstance(declared.default, bool)
    )
    default = instance_settings._declared[key].default
    values = [default, not default]

    async def edit(n: int) -> None:
        await instance_settings.set_values(
            db_session, {key: values[n % len(values)]}, actor=beheerder
        )

    started = await instance_settings.version(db_session)
    header = f'"{instance_settings.SETTINGS_KEY}:{started}"'
    with stale.expecting(header):
        await edit(1)
    assert await instance_settings.version(db_session) > started
    with stale.expecting(header), pytest.raises(stale.StaleWriteError):
        await edit(2)


async def test_billing_terms(db_session: AsyncSession, beheerder) -> None:
    assignment = await assignments.create_assignment(
        db_session, name="Opdracht Zeta", actor=beheerder, owner_id=beheerder.id
    )
    await billing_deliveries.set_terms(
        db_session, assignment.id, actor=beheerder, rhythm="quarter"
    )
    from grip.models.billing_delivery import BillingTerms

    row = await db_session.get(BillingTerms, assignment.id)
    assert row is not None

    async def edit(n: int) -> None:
        await billing_deliveries.set_terms(
            db_session,
            assignment.id,
            actor=beheerder,
            names_on_specification=bool(n % 2),
        )

    await _twice(f"terms:{assignment.id}", row.version, edit)


async def test_assignment_roles(
    db_session: AsyncSession, beheerder, colleague, create_person
) -> None:
    assignment = await assignments.create_assignment(
        db_session, name="Opdracht Eta", actor=beheerder, owner_id=beheerder.id
    )
    other = await create_person("ander@example.org", name="Anders Ander")

    async def edit(n: int) -> None:
        await assignments.set_assignment_role(
            db_session,
            assignment.id,
            (colleague if n % 2 else other).id,
            "manager",
            actor=beheerder,
        )
        await db_session.flush()

    await db_session.refresh(assignment)
    await _twice(assignment.id, assignment.version, edit)


async def test_function_family_and_group(db_session: AsyncSession, beheerder) -> None:
    family = await function_framework.create_family(
        db_session, actor=beheerder, name="Voorbeeldfamilie"
    )

    async def edit_family(n: int) -> None:
        await function_framework.update_family(
            db_session,
            family.id,
            actor=beheerder,
            changes={"name": f"Voorbeeldfamilie {n}"},
        )

    await _twice(family.id, family.version, edit_family)

    group = await function_framework.create_group(
        db_session, actor=beheerder, family_id=family.id, name="Groep", scales=[10]
    )

    async def edit_group(n: int) -> None:
        await function_framework.update_group(
            db_session, group.id, actor=beheerder, changes={"name": f"Groep {n}"}
        )

    await _twice(group.id, group.version, edit_group)


async def test_rate_card_scale_and_status(db_session: AsyncSession, beheerder) -> None:
    await rates.create_rate_card(db_session, 2026, actor=beheerder)
    band = await rates.set_scale_band(db_session, 2026, 12, "A", actor=beheerder)

    async def edit(n: int) -> None:
        await rates.set_scale_band(db_session, 2026, 12, "BCDE"[n % 4], actor=beheerder)

    await _twice(band.id, band.version, edit)

    current = await rates.get_card(db_session, 2026)
    header = f'"{current.id}:{current.version + 5}"'
    with stale.expecting(header), pytest.raises(stale.StaleWriteError):
        await rates.set_rate_card_status(db_session, 2026, "active", actor=beheerder)


async def test_standard_vacancy_text_and_shared_section(
    db_session: AsyncSession, beheerder
) -> None:
    section = VacancyTextSharedSection(
        key="voorbeeld", heading="Dit bieden we", body="Tekst.", position=1
    )
    db_session.add(section)
    await db_session.flush()

    async def edit_shared(n: int) -> None:
        await library.update_shared_section(
            db_session,
            "voorbeeld",
            heading="Dit bieden we",
            body=f"Tekst {n}.",
            actor=beheerder,
        )

    await _twice("shared:voorbeeld", section.version, edit_shared)

    template = await library.save_template(
        db_session,
        None,
        actor=beheerder,
        role_name="Voorbeeldrol",
        sections=[{"key": "werk", "heading": "Dit ga je doen", "body": "Werk."}],
    )
    assert isinstance(template, VacancyTextTemplate)

    async def edit_template(n: int) -> None:
        await library.save_template(
            db_session,
            template.id,
            actor=beheerder,
            role_name="Voorbeeldrol",
            sections=[
                {"key": "werk", "heading": "Dit ga je doen", "body": f"Werk {n}."}
            ],
        )

    await _twice(template.id, template.version, edit_template)
