"""The export Wies pulls: what is in it, what "open" means, and what never leaves."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from grip.access.fields import schema_classes, unclassified_fields
from grip.access.types import DataClass
from grip.core.config import get_settings
from grip.integrations.wies.export import EXPORTED_STATUSES, build_export
from grip.models.vacancy import Vacancy
from grip.schema.integrations_wies import WiesExport

from .conftest import EXPORT_KEY, TODAY, TOOI

AUTH = {"Authorization": f"Bearer {EXPORT_KEY}"}
URL = "/api/integrations/wies/export"


def _settings():
    return get_settings().model_copy(update={"FRONTEND_URL": "https://grip.example"})


async def _export(db_session, today=TODAY):
    return await build_export(db_session, _settings(), today=today)


# --- contents -----------------------------------------------------------------


async def test_assignment_with_client_owner_role_and_placement(db_session, make):
    owner = await make.person("Eigenaar@Example.org", "Eige Naar")
    colleague = await make.person("collega@example.org", "Co Llega")
    assignment = await make.assignment(owner=owner, client=await make.organisation())
    line = await make.line(assignment)
    allocation = await make.allocation(line, colleague)

    export = await _export(db_session)

    assert len(export.assignments) == 1
    item = export.assignments[0]
    assert item.id == str(assignment.id)
    assert item.url == f"https://grip.example/opdrachten/{assignment.id}"
    assert item.name == "Opdracht Alfa"
    assert item.client_tooi_uri == TOOI
    assert item.owner_email == "eigenaar@example.org"
    assert (item.start_date, item.end_date) == (date(2026, 1, 1), date(2026, 12, 31))
    assert len(item.roles) == 1
    role = item.roles[0]
    assert (role.id, role.description, role.fte, role.open) == (
        str(allocation.id),
        "Developer",
        "1",
        False,
    )
    assert [(p.id, p.person_email) for p in role.placements] == [
        (str(allocation.id), "collega@example.org")
    ]


async def test_only_agreed_work_is_exported(db_session, make):
    for status in (
        "draft",
        "requested",
        "quoted",
        "rejected",
        "cancelled",
        *EXPORTED_STATUSES,
    ):
        await make.assignment(f"Opdracht {status}", status=status)

    export = await _export(db_session)

    assert {a.status for a in export.assignments} == set(EXPORTED_STATUSES)


async def test_fixed_lines_are_not_roles(db_session, make):
    assignment = await make.assignment()
    await make.fixed_line(assignment)

    export = await _export(db_session)

    assert export.assignments[0].roles == []


async def test_assignment_without_client_or_owner(db_session, make):
    await make.assignment()

    item = (await _export(db_session)).assignments[0]

    assert item.client_tooi_uri is None
    assert item.owner_email is None


# --- what "open" means --------------------------------------------------------


async def test_line_without_allocation_is_open(db_session, make):
    line = await make.line(await make.assignment(), fte="0.8")

    roles = (await _export(db_session)).assignments[0].roles

    assert [(r.id, r.open, r.fte, r.placements) for r in roles] == [
        (f"{line.id}:open", True, "0.8", [])
    ]


async def test_fully_filled_line_is_not_open(db_session, make):
    line = await make.line(await make.assignment(), fte="0.8")
    await make.allocation(line, await make.person("a@example.org"), pct="80")

    roles = (await _export(db_session)).assignments[0].roles

    # The role is the seat the person fills, with that person's share.
    assert [(r.open, r.fte, len(r.placements)) for r in roles] == [(False, "0.8", 1)]


async def test_partly_filled_line_gives_a_filled_role_and_an_open_remainder(
    db_session, make
):
    line = await make.line(await make.assignment(), fte="1")
    await make.allocation(line, await make.person("a@example.org"), pct="60")

    roles = (await _export(db_session)).assignments[0].roles

    assert [(r.id, r.open, r.fte, len(r.placements)) for r in roles] == [
        (roles[0].placements[0].id, False, "0.6", 1),
        (f"{line.id}:open", True, "0.4", 0),
    ]


async def test_two_people_filling_one_line(db_session, make):
    line = await make.line(await make.assignment(), fte="1")
    await make.allocation(line, await make.person("a@example.org"), pct="50")
    await make.allocation(line, await make.person("b@example.org"), pct="50")

    roles = (await _export(db_session)).assignments[0].roles

    # One role per person, each with their own share.
    assert [(r.open, r.fte, len(r.placements)) for r in roles] == [
        (False, "0.5", 1),
        (False, "0.5", 1),
    ]


async def test_allocation_that_ended_leaves_the_role_open_again(db_session, make):
    line = await make.line(await make.assignment())
    await make.allocation(
        line,
        await make.person("a@example.org"),
        start=date(2026, 1, 1),
        end=date(2026, 3, 31),
    )

    roles = (await _export(db_session)).assignments[0].roles

    # The past placement stays with the role; the remainder is the whole role.
    assert [(r.open, r.fte, len(r.placements)) for r in roles] == [
        (False, "1", 1),
        (True, "1", 0),
    ]


async def test_line_that_has_not_started_is_judged_on_its_first_day(db_session, make):
    line = await make.line(
        await make.assignment(), start=date(2026, 9, 1), end=date(2026, 12, 31)
    )
    await make.allocation(
        line,
        await make.person("a@example.org"),
        start=date(2026, 9, 1),
        end=date(2026, 12, 31),
    )

    roles = (await _export(db_session)).assignments[0].roles

    assert [r.open for r in roles] == [False]


async def test_line_that_ended_is_never_open(db_session, make):
    assignment = await make.assignment()
    await make.line(assignment, start=date(2026, 1, 1), end=date(2026, 3, 31))

    roles = (await _export(db_session)).assignments[0].roles

    assert roles == []


async def test_published_vacancy_opens_a_filled_line(db_session, make):
    line = await make.line(await make.assignment())
    await make.allocation(line, await make.person("a@example.org"))
    db_session.add(
        Vacancy(
            budget_line_id=line.id,
            function_title="Senior developer",
            fte=Decimal("1"),
            declarable=True,
            status="open",
            published_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    roles = (await _export(db_session)).assignments[0].roles

    assert [(r.open, r.description) for r in roles] == [
        (False, "Developer"),
        (True, "Senior developer"),
    ]


async def test_vacancy_that_is_not_published_changes_nothing(db_session, make):
    line = await make.line(await make.assignment())
    await make.allocation(line, await make.person("a@example.org"))
    db_session.add(
        Vacancy(
            budget_line_id=line.id,
            function_title="Senior developer",
            fte=Decimal("1"),
            declarable=True,
            status="draft",
        )
    )
    await db_session.flush()

    roles = (await _export(db_session)).assignments[0].roles

    assert [r.open for r in roles] == [False]


# --- what never leaves --------------------------------------------------------


def test_export_schema_holds_only_classes_a_and_c():
    assert unclassified_fields(WiesExport) == []
    assert schema_classes(WiesExport) <= {
        DataClass.ASSIGNMENT_BASIC,
        DataClass.STAFFING,
    }


async def test_no_amount_rate_or_category_in_the_answer(
    client, db_session, make, wies_settings
):
    wies_settings()
    assignment = await make.assignment(
        quoted_amount_cents=98765400,
        notes="Vertrouwelijke notitie",
        client_contact="Con Tact",
    )
    line = await make.line(assignment, fte="0.8", category="E")
    await make.fixed_line(assignment, amount_cents=1234500)
    await make.allocation(line, await make.person("a@example.org"), pct="77.5")

    response = await client.get(URL, headers=AUTH)

    assert response.status_code == 200
    body = response.text
    for forbidden in (
        "98765400",
        "987654",
        "1234500",
        "12345",
        "77.5",
        "Vertrouwelijke",
        "Con Tact",
        "Hosting",
        "rate_category",
        "amount",
        "cents",
        "fte_pct",
        "(begroting)",
    ):
        assert forbidden not in body, forbidden

    def keys(value) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys(v)}
        return set()

    assert keys(json.loads(body)) == {
        "generated_at",
        "instance_name",
        "instance_base_uri",
        "assignments",
        "id",
        "url",
        "name",
        "status",
        "start_date",
        "end_date",
        "client_tooi_uri",
        "client_registry_id",
        "owner_email",
        "roles",
        "description",
        "role_name",
        "role_wies_id",
        "fte",
        "open",
        "placements",
        "person_email",
        "person_uri",
    }


# --- the key ------------------------------------------------------------------


async def test_export_needs_the_key(client, wies_settings):
    wies_settings()

    assert (await client.get(URL)).status_code == 403
    assert (
        await client.get(URL, headers={"Authorization": "Bearer verkeerd"})
    ).status_code == 403
    assert (
        await client.get(URL, headers={"Authorization": EXPORT_KEY})
    ).status_code == 403
    ok = await client.get(URL, headers=AUTH)
    assert ok.status_code == 200
    assert ok.headers["cache-control"] == "no-store"


async def test_export_is_off_while_no_key_is_configured(client, wies_settings):
    wies_settings(GRIP_EXPORT_KEY="")

    assert (await client.get(URL, headers=AUTH)).status_code == 403
    assert (
        await client.get(URL, headers={"Authorization": "Bearer "})
    ).status_code == 403


async def test_a_session_alone_does_not_open_the_export(
    client, create_person, wies_settings
):
    wies_settings()
    await create_person("beheerder@example.org", functions=["beheerder"])

    assert (await client.get(URL)).status_code == 403


def test_only_the_export_skips_the_session_check():
    from grip.middleware.auth_required import is_public_path

    assert is_public_path("/api/integrations/wies/export")
    assert not is_public_path("/api/integrations/wies/reconciliation")
    assert not is_public_path("/api/integrations/wies/export/extra")


async def test_client_without_tooi_uri_is_named_by_its_register_id(db_session, make):
    from grip.models.organisation import Organisation

    part = Organisation(
        name="Directie Voorbeeld", source="registry", registry_id="9004"
    )
    db_session.add(part)
    await db_session.flush()
    await make.assignment(client=part)

    item = (await _export(db_session)).assignments[0]

    assert (item.client_tooi_uri, item.client_registry_id) == (None, "9004")


async def test_role_goes_with_its_catalogue_name_and_wies_id(db_session, make):
    from sqlalchemy import select

    from grip.models.catalogue_role import CatalogueRole

    line = await make.line(await make.assignment(), role="developer")
    entry = (await db_session.execute(select(CatalogueRole))).scalars().one()
    entry.wies_public_id = "11111111-1111-1111-1111-111111111111"
    entry.name = "Developer"
    await db_session.flush()
    await db_session.refresh(line)

    (role,) = (await _export(db_session)).assignments[0].roles

    assert (role.description, role.role_name, role.role_wies_id) == (
        "Developer",
        "Developer",
        "11111111-1111-1111-1111-111111111111",
    )


async def test_line_without_role_sends_its_own_text(db_session, make):
    from grip.models.assignment import BudgetLine

    assignment = await make.assignment()
    db_session.add(
        BudgetLine(
            assignment_id=assignment.id,
            description="Extra handen",
            kind="personnel",
            fte=1,
            rate_category="D",
            start_date=assignment.start_date,
            end_date=assignment.end_date,
        )
    )
    await db_session.flush()

    (role,) = (await _export(db_session)).assignments[0].roles

    assert (role.description, role.role_name, role.role_wies_id) == (
        "Extra handen",
        None,
        None,
    )
