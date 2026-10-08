"""The Functiegebouw Rijk: the reference file, reading, beheer, and vacancies."""

from __future__ import annotations

import io
import json
from datetime import date, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from grip.access import unclassified_fields
from grip.models.function_framework import FunctionGroup
from grip.schema import function_framework as schemas
from grip.services import function_framework as framework
from grip.services import rates

BASE = "/api/function-framework"
VACANCIES = "/api/vacancies"

# A small file in the format of the reference file, with fictional entries.
FIXTURE = {
    "name": "Functiegebouw Rijk",
    "source_url": "https://bron.example/functiegebouw",
    "read_on": "2026-10-08",
    "families": [
        {
            "key": "testfamilie",
            "name": "Testfamilie",
            "source_url": "https://bron.example/functiegebouw/testfamilie",
            "groups": [
                {
                    "source_id": "test-groep-1",
                    "name": "Testmedewerker",
                    "scales": [8, 9, 10],
                    "source_url": "https://bron.example/functiegebouw/testmedewerker",
                },
                {
                    "source_id": "test-groep-2",
                    "name": "Testadviseur",
                    "scales": [12],
                },
            ],
        }
    ],
}


async def _groups(client) -> dict[str, dict]:
    body = (await client.get(BASE)).json()
    return {
        group["name"]: group
        for family in body["families"]
        for group in family["groups"]
    }


# --- the reference file ------------------------------------------------------


def test_reference_file_is_complete_and_sound() -> None:
    data = framework.read_reference()
    assert data["source_url"].startswith("https://www.functiegebouwrijksoverheid.nl/")
    assert date.fromisoformat(data["read_on"])
    info = framework.reference_info(data)
    assert (info.families, info.groups) == (8, 64)
    ids = [group["source_id"] for f in data["families"] for group in f["groups"]]
    assert len(ids) == len(set(ids))
    for family in data["families"]:
        assert family["name"] and family["key"]
        for group in family["groups"]:
            assert group["name"].strip()
            assert group["scales"] == sorted(set(group["scales"]))
            assert all(1 <= scale <= 19 for scale in group["scales"])


@pytest.mark.parametrize(
    "schema",
    [
        schemas.FunctionFrameworkOut,
        schemas.FunctionFamilyOut,
        schemas.FunctionGroupOut,
        schemas.FunctionFrameworkSourceOut,
        schemas.ReloadOut,
    ],
    ids=lambda s: s.__name__,
)
def test_no_unclassified_fields(schema) -> None:
    assert unclassified_fields(schema) == []


def test_scales_in_words() -> None:
    assert framework.describe_scales([12]) == "schaal 12"
    assert framework.describe_scales([13, 11, 12]) == "schaal 11 t/m 13"
    assert framework.describe_scales([4, 6]) == "schaal 4, 6"


# --- reading and beheer ------------------------------------------------------


async def test_everyone_reads_the_list_loaded_by_the_migration(
    client, act_as, colleague
) -> None:
    act_as(colleague)
    response = await client.get(BASE)
    assert response.status_code == 200
    body = response.json()
    assert body["can_manage"] is False
    assert body["source"]["read_on"] == "2026-10-08"
    assert body["source"]["reference_groups"] == 64
    assert len(body["families"]) == 8
    groups = await _groups(client)
    assert len(groups) == 64
    adviser = groups["(Senior) Adviseur"]
    assert adviser["scales"] == [11, 12, 13]
    assert adviser["scales_text"] == "schaal 11 t/m 13"
    assert adviser["source"] == "reference" and adviser["edited"] is False


async def test_only_the_beheerder_changes_the_list(
    client, act_as, colleague, planner, lezer, manager
) -> None:
    act_as(colleague)
    group_id = (await _groups(client))["Projectleider"]["id"]
    family_id = (await client.get(BASE)).json()["families"][0]["id"]
    for person in (colleague, planner, lezer, manager):
        act_as(person)
        assert (await client.post(f"{BASE}/reload")).status_code == 403
        response = await client.post(f"{BASE}/families", json={"name": "Eigen familie"})
        assert response.status_code == 403
        response = await client.patch(
            f"{BASE}/families/{family_id}", json={"name": "X"}
        )
        assert response.status_code == 403
        response = await client.post(
            f"{BASE}/groups", json={"family_id": family_id, "name": "X", "scales": [9]}
        )
        assert response.status_code == 403
        response = await client.patch(f"{BASE}/groups/{group_id}", json={"name": "X"})
        assert response.status_code == 403


async def test_beheerder_corrects_adds_and_ends(client, act_as, beheerder) -> None:
    act_as(beheerder)
    body = (await client.get(BASE)).json()
    assert body["can_manage"] is True
    family_id = body["families"][0]["id"]
    group = (await _groups(client))["Projectleider"]

    response = await client.patch(
        f"{BASE}/groups/{group['id']}",
        json={"name": "Projectleider A", "scales": [10, 9]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["scales"] == [9, 10]
    assert response.json()["edited"] is True

    response = await client.post(
        f"{BASE}/groups",
        json={"family_id": family_id, "name": "Eigen groep", "scales": [7, 8]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["source"] == "manual"
    for scales in ([], [0], [20]):
        response = await client.post(
            f"{BASE}/groups",
            json={"family_id": family_id, "name": "X", "scales": scales},
        )
        assert response.status_code == 422

    # An ended group is no longer offered, but stays for beheer.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = await client.patch(
        f"{BASE}/groups/{group['id']}", json={"valid_to": yesterday}
    )
    assert response.status_code == 200
    assert "Projectleider A" not in await _groups(client)
    everything = (await client.get(f"{BASE}?include_ended=true")).json()
    names = {g["name"] for f in everything["families"] for g in f["groups"]}
    assert {"Projectleider A", "Eigen groep"} <= names

    # A reload restores nothing that a beheerder changed, and removes nothing.
    response = await client.post(f"{BASE}/reload")
    assert response.status_code == 200
    assert response.json() == {
        "families_created": 0,
        "families_updated": 0,
        "groups_created": 0,
        "groups_updated": 0,
        "groups_kept": 1,
    }
    response = await client.post(f"{BASE}/families", json={"name": "Eigen familie"})
    assert response.status_code == 201
    assert (
        await client.post(f"{BASE}/families", json={"name": "Eigen familie"})
    ).status_code == 422


async def test_reload_upserts_from_a_file_in_the_source_format(
    db_session, beheerder
) -> None:
    first = await framework.reload_reference(db_session, actor=beheerder, data=FIXTURE)
    assert (first.families_created, first.groups_created) == (1, 2)
    changed = json.loads(json.dumps(FIXTURE))
    changed["families"][0]["groups"][0]["name"] = "Testmedewerker nieuw"
    changed["families"][0]["groups"][0]["scales"] = [8, 9]
    second = await framework.reload_reference(db_session, actor=beheerder, data=changed)
    assert (second.groups_created, second.groups_updated, second.groups_kept) == (
        0,
        1,
        0,
    )
    group = (
        await db_session.execute(
            select(FunctionGroup).where(FunctionGroup.source_id == "test-groep-1")
        )
    ).scalar_one()
    assert (group.name, list(group.scales)) == ("Testmedewerker nieuw", [8, 9])
    again = await framework.reload_reference(db_session, actor=beheerder, data=changed)
    assert (again.groups_created, again.groups_updated, again.groups_kept) == (0, 0, 0)


# --- a vacancy and its function group ----------------------------------------


@pytest.fixture
async def rate_card(db_session, beheerder):
    """2027: category C is scale 12 and 13, as in the domain examples."""
    await rates.create_rate_card(db_session, 2027, actor=beheerder)
    for scale, category in {
        10: "B",
        11: "B",
        12: "C",
        13: "C",
        14: "D",
        15: "D",
    }.items():
        await rates.set_scale_band(db_session, 2027, scale, category, actor=beheerder)


async def _vacancy(client, budget_line) -> dict:
    response = await client.post(
        VACANCIES, json={"budget_line_id": str(budget_line.id)}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_creating_asks_for_nothing_but_the_role(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _vacancy(client, budget_line)
    assert vacancy["function_title"] == "Backend-ontwikkelaar"
    assert vacancy["vacancy_type"] == "regulier"
    assert vacancy["fgr_function_name"] is None and vacancy["scale"] is None
    assert vacancy["function_group_id"] is None
    assert vacancy["addressee_has_account"] is False


async def test_group_prints_its_name_and_guards_the_scale(
    client, act_as, manager, beheerder, budget_line
) -> None:
    act_as(manager)
    vacancy = await _vacancy(client, budget_line)
    url = f"{VACANCIES}/{vacancy['id']}"
    groups = await _groups(client)

    # One scale: filled in.
    single = groups["Geestelijk Verzorger"]
    changed = (await client.patch(url, json={"function_group_id": single["id"]})).json()
    assert changed["fgr_function_name"] == "Geestelijk Verzorger"
    assert changed["scale"] == 12
    assert changed["function_family_name"] == "Uitvoering"
    assert changed["function_group_scales"] == [12]

    # Several scales: one of them is fine, another is refused.
    adviser = groups["(Senior) Adviseur"]
    response = await client.patch(
        url, json={"function_group_id": adviser["id"], "scale": 12}
    )
    assert response.status_code == 200, response.text
    response = await client.patch(url, json={"scale": 14})
    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "ScaleOutsideGroupError"
    assert (
        "Schaal 14 hoort niet bij de functiegroep (Senior) Adviseur"
        in problem["detail"]
    )
    assert "schaal 11 t/m 13" in problem["detail"]
    assert (await client.get(url)).json()["scale"] == 12

    # Unless it is marked as deviating, with the reason.
    response = await client.patch(
        url,
        json={"scale": 14, "scale_deviation_reason": "Arbeidsmarkttoelage omgezet."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["scale_deviation_reason"] == "Arbeidsmarkttoelage omgezet."
    # Back inside the group, the reason is dropped.
    back = (await client.patch(url, json={"scale": 13})).json()
    assert back["scale_deviation_reason"] is None

    # A later renaming does not change what was printed on this vacancy.
    act_as(beheerder)
    response = await client.patch(
        f"{BASE}/groups/{adviser['id']}", json={"name": "Adviseur (hernoemd)"}
    )
    assert response.status_code == 200
    seen = (await client.get(url)).json()
    assert seen["fgr_function_name"] == "(Senior) Adviseur"
    assert seen["function_group_id"] == adviser["id"]

    # A free-text name drops the link to a group, and with it the guard.
    free = (
        await client.patch(url, json={"fgr_function_name": "Eigen naam", "scale": 16})
    ).json()
    assert free["function_group_id"] is None
    assert free["fgr_function_name"] == "Eigen naam" and free["scale"] == 16

    # An ended group cannot be chosen.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await client.patch(f"{BASE}/groups/{single['id']}", json={"valid_to": yesterday})
    response = await client.patch(url, json={"function_group_id": single["id"]})
    assert response.status_code == 422
    assert "niet meer geldig" in response.json()["detail"]


async def test_budget_line_category_suggests_groups_and_warns(
    client, act_as, manager, budget_line, rate_card
) -> None:
    """The line is budgeted in category C: scale 12 and 13 in 2027."""
    act_as(manager)
    vacancy = await _vacancy(client, budget_line)
    url = f"{VACANCIES}/{vacancy['id']}"
    groups = await _groups(client)
    by_id = {group["id"]: group for group in groups.values()}

    suggested = [by_id[i] for i in vacancy["suggested_function_group_ids"]]
    assert suggested
    assert all(set(group["scales"]) & {12, 13} for group in suggested)
    names = {group["name"] for group in suggested}
    assert "(Senior) Adviseur" in names and "Projectleider" not in names
    assert vacancy["scale_fits_budget_line"] is None

    adviser = groups["(Senior) Adviseur"]
    fits = (
        await client.patch(url, json={"function_group_id": adviser["id"], "scale": 12})
    ).json()
    assert fits["scale_fits_budget_line"] is True
    # Scale 11 is a scale of the group, but below the line's category.
    low = (await client.patch(url, json={"scale": 11})).json()
    assert low["scale_fits_budget_line"] is False


async def test_without_a_rate_card_nothing_is_suggested(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _vacancy(client, budget_line)
    assert vacancy["suggested_function_group_ids"] == []
    assert vacancy["scale_fits_budget_line"] is None


async def test_addressee_with_and_without_an_account(
    client, act_as, manager, adviser, lezer, budget_line
) -> None:
    act_as(manager)
    vacancy = await _vacancy(client, budget_line)
    url = f"{VACANCIES}/{vacancy['id']}"
    picked = (await client.patch(url, json={"addressee_id": str(adviser.id)})).json()
    assert picked["addressee_name"] == "Fictieve Adviseur"
    assert picked["addressee_has_account"] is True
    typed = (
        await client.patch(url, json={"addressee_name": "Fictief Directielid"})
    ).json()
    assert typed["addressee_name"] == "Fictief Directielid"
    assert typed["addressee_has_account"] is False
    response = await client.patch(
        url, json={"addressee_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert response.status_code == 404
    # A lezer sees the group and the scale, not who it is addressed to.
    act_as(lezer)
    seen = (await client.get(url)).json()
    assert "addressee_name" not in seen and "addressee_has_account" not in seen
    assert "function_group_id" in seen


async def test_form_prints_the_stored_name_and_scale(
    client, act_as, manager, beheerder, budget_line, blank_form, test_mapping
) -> None:
    act_as(beheerder)
    response = await client.post(
        "/api/form-templates",
        data={"name": "Aanvraagformulier", "mapping": json.dumps(test_mapping)},
        files={"file": ("formulier.pdf", blank_form, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    act_as(manager)
    vacancy = await _vacancy(client, budget_line)
    url = f"{VACANCIES}/{vacancy['id']}"
    adviser = (await _groups(client))["(Senior) Adviseur"]

    # What is still to be prepared shows in the open fields.
    status = (await client.get(f"{url}/request-form/status")).json()
    open_sources = {field["source"] for field in status["open_fields"]}
    assert {
        "fgr_function_name",
        "scale",
        "addressee_name",
        "contract_type",
    } <= open_sources

    await client.patch(
        url,
        json={
            "function_group_id": adviser["id"],
            "scale": 12,
            "contract_type": "temporary_project",
            "addressee_name": "Fictief Directielid",
        },
    )
    act_as(beheerder)
    await client.patch(f"{BASE}/groups/{adviser['id']}", json={"name": "Hernoemd"})
    act_as(manager)
    status = (await client.get(f"{url}/request-form/status")).json()
    open_sources = {field["source"] for field in status["open_fields"]}
    assert (
        not {"fgr_function_name", "scale", "addressee_name", "contract_type"}
        & open_sources
    )
    response = await client.get(f"{url}/request-form")
    fields = PdfReader(io.BytesIO(response.content)).get_fields()
    assert fields["fgr"]["/V"] == "(Senior) Adviseur"
    assert fields["schaal"]["/V"] == "12"
    assert fields["aan"]["/V"] == "Fictief Directielid"
