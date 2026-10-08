"""Searching, manual organisations and the routes."""

from __future__ import annotations

import asyncio
from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from grip.core.auth import DEV_PERSON_COOKIE
from grip.integrations.organisations.source import (
    RegistryUnavailableError,
    iter_root_organisations,
)
from grip.integrations.organisations.sync import apply_registry
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation, OrganisationSyncRun
from grip.services import organisations as service
from grip.services.assignments import upsert_organisation
from grip.services.errors import DomainValidationError

from .conftest import EXPECTED_CREATED, MINISTRY_TOOI, TODAY

URL = "/api/organisations"


@pytest.fixture
async def register(db_session, export_bytes):
    await apply_registry(
        db_session, iter_root_organisations(BytesIO(export_bytes)), today=TODAY
    )
    await db_session.flush()


async def _labels(db, query="", **kw):
    result = await service.search_organisations(db, query=query, today=TODAY, **kw)
    return [hit.organisation.display_name for hit in result.items]


async def _one(db, name) -> Organisation:
    return (
        (await db.execute(select(Organisation).where(Organisation.name == name)))
        .scalars()
        .one()
    )


# --- searching ----------------------------------------------------------------


async def test_exact_abbreviation_comes_first(db_session, register):
    labels = await _labels(db_session, "fa")

    # "FA" exactly, then the abbreviation that starts with it, then the name
    # that starts with it ("Faculteit" is already listed), then a name that
    # merely contains it ("Sofa").
    assert labels == [
        "Fictieve Autoriteit",
        "Faculteit der Voorbeelden",
        "Stichting Sofa en Zo",
    ]


async def test_name_prefix_before_word_prefix_before_contains(db_session, register):
    labels = await _labels(db_session, "voorbeeld")

    assert labels[0] == "Voorbeeldstad"
    assert labels.index("Ministerie van Voorbeeldzaken") < labels.index(
        "Faculteit der Voorbeelden"
    )
    assert "Dienst Voorbeelduitvoering" in labels


async def test_search_ignores_case_and_accents(db_session, register):
    assert await _labels(db_session, "FINANCIEN") == [
        "Ministerie van Denkbeeldige Financiën"
    ]
    assert await _labels(db_session, "financiën") == [
        "Ministerie van Denkbeeldige Financiën"
    ]


async def test_organisation_comes_before_a_part_with_the_same_rank(
    db_session, register
):
    ministry = await _one(db_session, "Voorbeeldzaken")
    db_session.add(
        Organisation(name="Voorbeeldzaken", source="registry", parent_id=ministry.id)
    )
    await db_session.flush()

    result = await service.search_organisations(
        db_session, query="voorbeeldzaken", today=TODAY
    )

    assert [hit.path_label for hit in result.items] == [
        "Ministerie van Voorbeeldzaken",
        "Ministerie van Voorbeeldzaken > Voorbeeldzaken",
    ]


async def test_every_word_must_match(db_session, register):
    assert await _labels(db_session, "directie fictieve") == ["Directie Fictieve Zaken"]
    assert await _labels(db_session, "directie bestaatniet") == []


async def test_label_is_searched_too(db_session, register):
    assert "Ministerie van Voorbeeldzaken" in await _labels(
        db_session, "ministerie van voor"
    )


async def test_like_wildcards_in_the_query_are_literal(db_session, register):
    assert await _labels(db_session, "%") == []
    assert await _labels(db_session, "_") == []


async def test_equal_names_are_told_apart_by_their_path(db_session, register):
    result = await service.search_organisations(
        db_session, query="communicatie", today=TODAY
    )

    assert sorted(hit.path_label for hit in result.items) == [
        "Ministerie van Denkbeeldige Financiën > Directie Communicatie",
        "Ministerie van Voorbeeldzaken > Directie Communicatie",
    ]


async def test_path_runs_from_the_top_down(db_session, register):
    result = await service.search_organisations(db_session, query="DFZ", today=TODAY)

    assert result.items[0].path == (
        "Ministerie van Voorbeeldzaken",
        "Directoraat-Generaal Proefbeleid",
        "Directie Fictieve Zaken",
    )


async def test_agency_is_placed_under_its_ministry(db_session, register):
    result = await service.search_organisations(db_session, query="DVU", today=TODAY)

    assert result.items[0].path_label == (
        "Ministerie van Voorbeeldzaken > Dienst Voorbeelduitvoering"
    )
    # A municipality has no ministry above it.
    town = await service.search_organisations(
        db_session, query="voorbeeldstad", today=TODAY
    )
    assert town.items[0].path == ("Voorbeeldstad",)


async def test_filter_on_type(db_session, register):
    assert await _labels(db_session, organisation_type="Ministerie") == [
        "Ministerie van Denkbeeldige Financiën",
        "Ministerie van Voorbeeldzaken",
    ]
    # Also on a type that is not the first one of the organisation.
    assert await _labels(db_session, organisation_type="Adviescollege") == [
        "Fictieve Autoriteit"
    ]


async def test_paging(db_session, register):
    first = await service.search_organisations(
        db_session, page=1, page_size=4, today=TODAY
    )
    second = await service.search_organisations(
        db_session, page=2, page_size=4, today=TODAY
    )
    last = await service.search_organisations(
        db_session, page=3, page_size=4, today=TODAY
    )

    assert first.total == EXPECTED_CREATED
    assert (len(first.items), len(second.items), len(last.items)) == (4, 4, 3)
    ids = [h.organisation.id for h in (*first.items, *second.items, *last.items)]
    assert len(set(ids)) == EXPECTED_CREATED


async def test_without_a_query_used_and_manual_come_first(db_session, register):
    town = await _one(db_session, "Voorbeeldstad")
    db_session.add(
        Assignment(
            uri="https://grip.example/id/opdracht/1",
            name="Alfa",
            client_organisation_id=town.id,
        )
    )
    await service.create_manual_organisation(
        db_session, name="Voorbeeld BV", actor=None, today=TODAY
    )
    await db_session.flush()

    labels = await _labels(db_session)

    assert labels[:4] == [
        "Voorbeeldstad",
        "Voorbeeld BV",
        "Ministerie van Denkbeeldige Financiën",
        "Ministerie van Voorbeeldzaken",
    ]


async def test_ended_organisations_are_hidden_unless_asked(db_session, register):
    town = await _one(db_session, "Voorbeeldstad")
    town.end_date = date(2026, 1, 1)
    await db_session.flush()

    assert await _labels(db_session, "voorbeeldstad") == []
    assert await _labels(db_session, "voorbeeldstad", include_ended=True) == [
        "Voorbeeldstad"
    ]


async def test_type_counts(db_session, register):
    counts = dict(await service.type_counts(db_session, today=TODAY))

    assert counts["Ministerie"] == 2
    assert counts["Organisatieonderdeel"] == 4
    assert counts["Adviescollege"] == 1


# --- manual organisations -----------------------------------------------------


async def test_party_outside_the_register(db_session, register):
    company = await service.create_manual_organisation(
        db_session, name="  Voorbeeld   BV ", actor=None, today=TODAY
    )

    assert (company.name, company.source) == ("Voorbeeld BV", "manual")
    assert (company.tooi_uri, company.unit_key, company.parent_id) == (None, None, None)


async def test_unit_below_a_registered_organisation(db_session, register):
    dg = await _one(db_session, "Directoraat-Generaal Proefbeleid")

    unit = await service.create_manual_organisation(
        db_session, name="Voorbeeld Gilde", parent_id=dg.id, actor=None, today=TODAY
    )

    # The DG has no TOOI URI of its own; the ministry above it has.
    assert (unit.tooi_uri, unit.unit_key, unit.parent_id) == (
        MINISTRY_TOOI,
        "voorbeeld-gilde",
        dg.id,
    )
    (hit,) = await service.with_paths(db_session, [unit])
    assert hit.path_label == (
        "Ministerie van Voorbeeldzaken > "
        "Directoraat-Generaal Proefbeleid > Voorbeeld Gilde"
    )


async def test_same_name_in_the_same_place_is_not_added_twice(db_session, register):
    ministry = await _one(db_session, "Voorbeeldzaken")
    first = await service.create_manual_organisation(
        db_session,
        name="Voorbeeldgilde",
        parent_id=ministry.id,
        actor=None,
        today=TODAY,
    )

    again = await service.create_manual_organisation(
        db_session,
        name="voorbeeldgilde",
        parent_id=ministry.id,
        actor=None,
        today=TODAY,
    )
    # An organisation the register already holds is returned as well.
    existing = await service.create_manual_organisation(
        db_session, name="voorbeeldstad", actor=None, today=TODAY
    )

    assert again.id == first.id
    assert (existing.source, existing.name) == ("registry", "Voorbeeldstad")


async def test_unit_keys_stay_unique_within_an_organisation(db_session, register):
    ministry = await _one(db_session, "Voorbeeldzaken")
    dg = await _one(db_session, "Directoraat-Generaal Proefbeleid")

    first = await service.create_manual_organisation(
        db_session, name="Team A", parent_id=ministry.id, actor=None, today=TODAY
    )
    second = await service.create_manual_organisation(
        db_session, name="Team A", parent_id=dg.id, actor=None, today=TODAY
    )

    assert (first.unit_key, second.unit_key) == ("team-a", "team-a-2")


async def test_manual_organisation_needs_a_name_and_an_existing_parent(
    db_session, register
):
    with pytest.raises(DomainValidationError):
        await service.create_manual_organisation(db_session, name="   ", actor=None)
    with pytest.raises(DomainValidationError):
        await service.create_manual_organisation(
            db_session, name="Team", parent_id=uuid4(), actor=None
        )


async def test_register_rows_are_not_edited_by_hand(db_session, register):
    town = await _one(db_session, "Voorbeeldstad")

    with pytest.raises(DomainValidationError, match="register"):
        await service.update_organisation(
            db_session, town.id, {"name": "Anders"}, actor=None
        )
    changed = await service.update_organisation(
        db_session,
        town.id,
        {"instance_uri": "https://grip.voorbeeldstad.example"},
        actor=None,
    )

    assert (changed.name, changed.instance_uri) == (
        "Voorbeeldstad",
        "https://grip.voorbeeldstad.example",
    )


async def test_manual_rows_can_be_renamed_and_ended(db_session):
    company = await service.create_manual_organisation(
        db_session, name="Voorbeeld BV", actor=None
    )

    changed = await service.update_organisation(
        db_session,
        company.id,
        {"name": "Voorbeeld NV", "end_date": date(2026, 12, 31)},
        actor=None,
    )

    assert (changed.name, changed.end_date) == ("Voorbeeld NV", date(2026, 12, 31))


async def test_upsert_keeps_working_for_its_callers(db_session, register):
    # A counterparty that is in the register is found, not doubled.
    found = await upsert_organisation(
        db_session, name="Maakt niet uit", tooi_uri=MINISTRY_TOOI
    )
    # One that is not becomes a manual row.
    new = await upsert_organisation(db_session, name="Voorbeeld BV")

    assert (found.source, found.name) == ("registry", "Voorbeeldzaken")
    assert new.source == "manual"


# --- the routes ---------------------------------------------------------------


async def test_every_person_may_search_and_read(
    client, db_session, create_person, register
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    nobody = await create_person("zonder-functie@example.org")
    client.cookies.set(DEV_PERSON_COOKIE, str(nobody.id))

    response = await client.get(URL, params={"q": "dvu"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    hit = body["items"][0]
    assert hit["label"] == "Dienst Voorbeelduitvoering"
    assert hit["abbreviation"] == "DVU"
    assert hit["source"] == "registry"
    assert (
        hit["path_label"]
        == "Ministerie van Voorbeeldzaken > Dienst Voorbeelduitvoering"
    )
    assert (await client.get(f"{URL}/{hit['id']}")).json()["id"] == hit["id"]
    assert (await client.get(f"{URL}/{uuid4()}")).status_code == 404
    types = (await client.get(f"{URL}/types")).json()
    assert {"name": "Ministerie", "count": 2} in types


async def test_paging_and_type_filter_through_the_api(client, create_person, register):
    await create_person("beheerder@example.org", functions=["beheerder"])

    page = (await client.get(URL, params={"page_size": 3, "page": 2})).json()
    ministries = (await client.get(URL, params={"type": "Ministerie"})).json()

    assert (page["page"], page["page_size"], len(page["items"])) == (2, 3, 3)
    assert ministries["total"] == 2
    assert (await client.get(URL, params={"page_size": 1000})).status_code == 422


async def test_adding_by_hand_needs_the_right_to_start_an_assignment(
    client, db_session, create_person, register
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    lezer = await create_person("lezer@example.org", functions=["lezer"])
    planner = await create_person("planner@example.org", functions=["planner"])

    client.cookies.set(DEV_PERSON_COOKIE, str(lezer.id))
    assert (await client.post(URL, json={"name": "Voorbeeld BV"})).status_code == 403

    client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))
    ministry = await _one(db_session, "Voorbeeldzaken")
    created = await client.post(
        URL, json={"name": "Voorbeeldgilde", "parent_id": str(ministry.id)}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source"] == "manual"
    assert body["path_label"] == "Ministerie van Voorbeeldzaken > Voorbeeldgilde"
    assert body["tooi_uri"] == MINISTRY_TOOI


async def test_beheerder_may_add_by_hand(client, create_person):
    await create_person("beheerder@example.org", functions=["beheerder"])

    assert (await client.post(URL, json={"name": "Voorbeeld BV"})).status_code == 201


async def test_sync_is_for_the_beheerder(
    client, create_person, monkeypatch, export_bytes
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])

    async def _fetch(url, **_):
        return export_bytes

    monkeypatch.setattr("grip.services.organisations.fetch_registry", _fetch)

    client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))
    assert (
        await client.post(f"{URL}/sync", params={"wait": "true"})
    ).status_code == 403
    assert (await client.get(f"{URL}/sync")).status_code == 403

    client.cookies.delete(DEV_PERSON_COOKIE)
    before = (await client.get(f"{URL}/sync")).json()
    assert (before["last_run"], before["running"]) == (None, False)
    answer = await client.post(f"{URL}/sync", params={"wait": "true"})
    assert answer.status_code == 200
    run = answer.json()["last_run"]
    assert run["status"] == "completed"
    assert run["result"]["created"] == EXPECTED_CREATED
    assert answer.json()["registry_organisations"] == EXPECTED_CREATED


async def test_run_from_the_screen_continues_in_the_background(
    client, create_person, monkeypatch
):
    beheerder = await create_person("beheerder@example.org", functions=["beheerder"])
    started: list = []
    release = asyncio.Event()

    async def _slow(actor_id):
        started.append(actor_id)
        await release.wait()

    monkeypatch.setattr("grip.api.routes.organisations._run_in_background", _slow)

    first = await client.post(f"{URL}/sync")
    await asyncio.sleep(0)
    # A second press while one runs starts nothing.
    second = await client.post(f"{URL}/sync")

    assert (first.status_code, second.status_code) == (202, 202)
    assert first.json()["running"] is True
    assert first.json()["running_since"] is not None
    assert started == [beheerder.id]

    release.set()
    await asyncio.sleep(0.01)
    assert (await client.get(f"{URL}/sync")).json()["running"] is False


async def test_unreachable_register_gives_a_clear_message_and_changes_nothing(
    client, db_session, create_person, monkeypatch
):
    await create_person("beheerder@example.org", functions=["beheerder"])

    async def _down(url, **_):
        raise RegistryUnavailableError(
            "organisaties.overheid.nl is niet bereikbaar. Er is niets gewijzigd."
        )

    monkeypatch.setattr("grip.services.organisations.fetch_registry", _down)

    run = (await client.post(f"{URL}/sync", params={"wait": "true"})).json()["last_run"]

    assert run["status"] == "failed"
    assert run["error"] == (
        "organisaties.overheid.nl is niet bereikbaar. Er is niets gewijzigd."
    )
    total = select(func.count()).select_from(Organisation)
    assert (await db_session.execute(total)).scalar_one() == 0
    runs = select(func.count()).select_from(OrganisationSyncRun)
    assert (await db_session.execute(runs)).scalar_one() == 1


async def test_only_the_beheerder_changes_an_organisation(
    client, db_session, create_person, register
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])
    town = await _one(db_session, "Voorbeeldstad")

    refused = await client.patch(f"{URL}/{town.id}", json={"name": "Anders"})
    assert refused.status_code in (400, 409, 422)
    ok = await client.patch(
        f"{URL}/{town.id}", json={"instance_uri": "https://grip.voorbeeldstad.example"}
    )
    assert ok.json()["instance_uri"] == "https://grip.voorbeeldstad.example"

    client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))
    assert (
        await client.patch(f"{URL}/{town.id}", json={"instance_uri": None})
    ).status_code == 403
