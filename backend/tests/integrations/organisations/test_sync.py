"""Bringing the organisation table in line with the register."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import func, select

from grip.integrations.organisations.source import iter_root_organisations
from grip.integrations.organisations.sync import SyncRefusedError, apply_registry
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation, OrganisationSyncRun
from grip.services import organisations as service
from grip.services.assignments import upsert_organisation

from .conftest import AGENCY_TOOI, EXPECTED_CREATED, MINISTRY_TOOI, TODAY, without


async def _sync(db, content: bytes, today: date = TODAY):
    counts = await apply_registry(
        db, iter_root_organisations(BytesIO(content)), today=today
    )
    await db.flush()
    return counts


async def _by_name(db) -> dict[str, list[Organisation]]:
    result: dict[str, list[Organisation]] = {}
    for organisation in (await db.execute(select(Organisation))).scalars().all():
        result.setdefault(organisation.name, []).append(organisation)
    return result


async def test_first_run_takes_over_the_register(db_session, export_bytes):
    counts = await _sync(db_session, export_bytes)

    assert counts.created == EXPECTED_CREATED
    assert counts.skipped_ended == 2
    assert counts.excluded == 2
    orgs = await _by_name(db_session)
    assert "Opgeheven Bureau" not in orgs
    assert "Algemene Inlichtingen- en Veiligheidsdienst" not in orgs
    assert "Onderdeel dat niet mee mag" not in orgs
    (ministry,) = orgs["Voorbeeldzaken"]
    assert (
        ministry.source,
        ministry.label,
        ministry.main_type,
        ministry.registry_id,
    ) == (
        "registry",
        "Ministerie van Voorbeeldzaken",
        "Ministerie",
        "9001",
    )
    assert ministry.tooi_uri == MINISTRY_TOOI
    assert ministry.unit_key is None
    assert ministry.abbreviations == ["VZ", "MinVZ"]
    assert (
        ministry.source_url == "https://organisaties.overheid.nl/9001/Voorbeeldzaken/"
    )


async def test_hierarchy_follows_the_nesting(db_session, export_bytes):
    await _sync(db_session, export_bytes)
    orgs = await _by_name(db_session)

    (ministry,) = orgs["Voorbeeldzaken"]
    (dg,) = orgs["Directoraat-Generaal Proefbeleid"]
    (directie,) = orgs["Directie Fictieve Zaken"]
    assert dg.parent_id == ministry.id
    assert directie.parent_id == dg.id
    # The same name under two ministries is two organisations.
    assert len(orgs["Directie Communicatie"]) == 2
    assert {o.parent_id for o in orgs["Directie Communicatie"]} == {
        ministry.id,
        orgs["Ministerie van Denkbeeldige Financiën"][0].id,
    }


async def test_second_run_changes_nothing(db_session, export_bytes):
    await _sync(db_session, export_bytes)

    counts = await _sync(db_session, export_bytes)

    assert (counts.created, counts.updated, counts.closed, counts.deleted) == (
        0,
        0,
        0,
        0,
    )
    assert counts.unchanged == EXPECTED_CREATED
    total = (
        await db_session.execute(select(func.count()).select_from(Organisation))
    ).scalar_one()
    assert total == EXPECTED_CREATED


async def test_changes_in_the_register_arrive(db_session, export_bytes):
    await _sync(db_session, export_bytes)
    renamed = export_bytes.replace(
        b"<p:naam>Voorbeeldstad</p:naam>",
        b"<p:naam>Nieuw Voorbeeldstad</p:naam>",
    )

    counts = await _sync(db_session, renamed)

    assert counts.updated == 1
    orgs = await _by_name(db_session)
    assert "Voorbeeldstad" not in orgs
    assert orgs["Nieuw Voorbeeldstad"][0].registry_id == "9030"


async def test_what_grip_owns_survives_a_run(db_session, export_bytes):
    await _sync(db_session, export_bytes)
    (agency,) = (await _by_name(db_session))["Dienst Voorbeelduitvoering"]
    agency.instance_uri = "https://grip.voorbeelduitvoering.example"
    await db_session.flush()

    await _sync(db_session, export_bytes)

    await db_session.refresh(agency)
    assert agency.instance_uri == "https://grip.voorbeelduitvoering.example"


async def test_manual_row_with_a_registered_identifier_is_taken_over(
    db_session, export_bytes
):
    manual = await upsert_organisation(
        db_session,
        name="Voorbeelduitvoering (zelf ingevoerd)",
        tooi_uri=AGENCY_TOOI,
        instance_uri="https://grip.voorbeelduitvoering.example",
    )
    assert manual.source == "manual"

    counts = await _sync(db_session, export_bytes)

    await db_session.refresh(manual)
    assert counts.adopted == 1
    assert counts.created == EXPECTED_CREATED - 1
    assert (manual.source, manual.name) == ("registry", "Dienst Voorbeelduitvoering")
    assert manual.instance_uri == "https://grip.voorbeelduitvoering.example"


async def test_unit_below_a_registered_organisation_is_not_mistaken_for_it(
    db_session, export_bytes
):
    unit = await upsert_organisation(
        db_session,
        name="Voorbeeldgilde",
        tooi_uri=MINISTRY_TOOI,
        unit_key="voorbeeldgilde",
    )

    counts = await _sync(db_session, export_bytes)

    await db_session.refresh(unit)
    assert counts.adopted == 0
    assert (unit.source, unit.name) == ("manual", "Voorbeeldgilde")


async def test_disappeared_and_referenced_is_closed_not_deleted(
    db_session, export_bytes
):
    await _sync(db_session, export_bytes)
    (town,) = (await _by_name(db_session))["Voorbeeldstad"]
    db_session.add(
        Assignment(
            uri="https://grip.example/id/opdracht/1",
            name="Opdracht Alfa",
            client_organisation_id=town.id,
        )
    )
    await db_session.flush()

    counts = await _sync(db_session, without(export_bytes, "9030"))

    await db_session.refresh(town)
    assert (counts.closed, counts.deleted) == (1, 0)
    assert town.end_date == TODAY


async def test_disappeared_and_unreferenced_is_removed(db_session, export_bytes):
    await _sync(db_session, export_bytes)

    counts = await _sync(db_session, without(export_bytes, "9030"))

    assert (counts.closed, counts.deleted) == (1, 1)
    assert "Voorbeeldstad" not in await _by_name(db_session)


async def test_whole_tree_that_disappeared_is_removed_leaves_first(
    db_session, export_bytes
):
    await _sync(db_session, export_bytes)

    counts = await _sync(db_session, without(export_bytes, "9001"))

    assert (counts.closed, counts.deleted) == (4, 4)
    assert "Directie Fictieve Zaken" not in await _by_name(db_session)


async def test_manual_unit_keeps_its_closed_parent(db_session, export_bytes):
    await _sync(db_session, export_bytes)
    (town,) = (await _by_name(db_session))["Voorbeeldstad"]
    unit = await service.create_manual_organisation(
        db_session, name="Team Voorbeeld", parent_id=town.id, actor=None, today=TODAY
    )

    counts = await _sync(db_session, without(export_bytes, "9030"))

    await db_session.refresh(town)
    await db_session.refresh(unit)
    assert counts.deleted == 0
    assert town.end_date == TODAY
    assert unit.end_date is None


async def test_manual_organisations_are_never_touched(db_session, export_bytes):
    company = await service.create_manual_organisation(
        db_session, name="Voorbeeld BV", actor=None, today=TODAY
    )

    await _sync(db_session, export_bytes)
    await _sync(db_session, without(export_bytes, "9001"))

    await db_session.refresh(company)
    assert (company.source, company.end_date) == ("manual", None)


async def test_organisation_that_ended_in_the_register_gets_its_end_date(
    db_session, export_bytes
):
    await _sync(db_session, export_bytes)
    (town,) = (await _by_name(db_session))["Voorbeeldstad"]
    db_session.add(
        Assignment(
            uri="https://grip.example/id/opdracht/2",
            name="Opdracht Beta",
            client_organisation_id=town.id,
        )
    )
    await db_session.flush()
    ended = export_bytes.replace(
        b"<p:naam>Voorbeeldstad</p:naam>",
        b"<p:naam>Voorbeeldstad</p:naam><p:eindDatum>2026-06-30</p:eindDatum>",
    )

    await _sync(db_session, ended)

    await db_session.refresh(town)
    assert town.end_date == date(2026, 6, 30)


async def test_empty_export_is_refused(db_session, export_bytes):
    await _sync(db_session, export_bytes)
    empty = (
        b'<p:overheidsorganisaties xmlns:p="https://organisaties.overheid.nl/static/schema/oo/'
        b'export/9.9.9"><p:organisaties></p:organisaties></p:overheidsorganisaties>'
    )

    with pytest.raises(SyncRefusedError):
        await _sync(db_session, empty)


async def test_export_that_shrank_too_much_is_refused(
    db_session, export_bytes, monkeypatch
):
    monkeypatch.setattr("grip.integrations.organisations.sync._SHRINK_GUARD_MINIMUM", 5)
    await _sync(db_session, export_bytes)
    small = export_bytes
    for registry_id in ("9001", "9010", "9020", "9025", "9026", "9027"):
        small = without(small, registry_id)

    with pytest.raises(SyncRefusedError, match="te weinig"):
        await _sync(db_session, small)


# --- the run as the beheerder starts it -----------------------------------------


async def test_run_is_recorded_with_its_counts(db_session, export_bytes):
    run = await service.run_registry_sync(
        db_session, actor=None, content=export_bytes, today=TODAY
    )

    assert run.status == "completed"
    assert run.result["created"] == EXPECTED_CREATED
    assert (await service.last_sync_run(db_session)).id == run.id


async def test_failed_run_changes_nothing_and_is_recorded(db_session, export_bytes):
    await service.run_registry_sync(
        db_session, actor=None, content=export_bytes, today=TODAY
    )
    # Readable at the start, broken halfway: the first organisations parse.
    broken = export_bytes[: len(export_bytes) // 2]

    run = await service.run_registry_sync(
        db_session, actor=None, content=broken, today=TODAY
    )

    assert run.status == "failed"
    assert "leesbare XML" in run.error
    assert run.result == {}
    total = (
        await db_session.execute(select(func.count()).select_from(Organisation))
    ).scalar_one()
    assert total == EXPECTED_CREATED
    runs = (
        await db_session.execute(select(func.count()).select_from(OrganisationSyncRun))
    ).scalar_one()
    assert runs == 2


async def test_first_run_that_fails_halfway_leaves_the_table_empty(
    db_session, export_bytes
):
    run = await service.run_registry_sync(
        db_session,
        actor=None,
        content=export_bytes[: len(export_bytes) // 2],
        today=TODAY,
    )

    assert run.status == "failed"
    total = (
        await db_session.execute(select(func.count()).select_from(Organisation))
    ).scalar_one()
    assert total == 0
