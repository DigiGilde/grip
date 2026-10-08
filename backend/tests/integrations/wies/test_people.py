"""Reading colleagues from Wies and reconciling them with grip's persons."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.integrations.wies import client as wies_client
from grip.integrations.wies.client import (
    WiesColleague,
    WiesNotConfiguredError,
    WiesUnavailableError,
    fetch_colleagues,
    parse_colleagues,
)
from grip.integrations.wies.reconcile import parse_scope, propose
from grip.models.audit_log import AuditLog
from grip.models.person import Person

URL = "/api/integrations/wies/reconciliation"


def _colleague(
    email, name="Co Llega", *, active=True, merk="Digi Gilde", skills=("Developer",)
):
    return WiesColleague(
        public_id="00000000-0000-0000-0000-000000000001",
        name=name,
        email=email,
        active=active,
        suborganization=merk,
        skills=tuple(skills),
    )


def _person(email, name="Co Llega", *, active=True):
    return Person(name=name, email=email, is_active=active)


def _actions(proposals):
    return [(p.action, p.email) for p in proposals]


# --- the client ---------------------------------------------------------------


def _configured(**overrides):
    values = {"WIES_BASE_URL": "https://wies.example/", "WIES_API_KEY": "sleutel"}
    values.update(overrides)
    return get_settings().model_copy(update=values)


async def test_fetch_sends_the_key_and_parses_the_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(
            200,
            json={
                "colleagues": [
                    {
                        "public_id": "p-1",
                        "name": "Co Llega",
                        "email": "Collega@Example.org",
                        "skills": ["Developer"],
                        "labels": [{"category": "Expertise", "name": "ICT"}],
                        "suborganization": "Digi Gilde",
                        "active": True,
                    }
                ]
            },
        )

    colleagues = await fetch_colleagues(
        _configured(), transport=httpx.MockTransport(handler)
    )

    assert seen == {
        "url": "https://wies.example/koppelvlak/grip/collegas/",
        "authorization": "Bearer sleutel",
    }
    assert colleagues == [
        WiesColleague(
            public_id="p-1",
            name="Co Llega",
            email="collega@example.org",
            active=True,
            suborganization="Digi Gilde",
            skills=("Developer",),
            labels=(("Expertise", "ICT"),),
        )
    ]


async def test_fetch_is_off_while_not_configured():
    with pytest.raises(WiesNotConfiguredError):
        await fetch_colleagues(_configured(WIES_API_KEY=""))


async def test_refusal_and_outage_are_reported_as_unavailable():
    refused = httpx.MockTransport(
        lambda request: httpx.Response(403, json={"error": "forbidden"})
    )
    with pytest.raises(WiesUnavailableError):
        await fetch_colleagues(_configured(), transport=refused)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("geen verbinding")

    with pytest.raises(WiesUnavailableError):
        await fetch_colleagues(_configured(), transport=httpx.MockTransport(down))


def test_parse_skips_entries_without_address_and_doubles():
    parsed = parse_colleagues(
        {
            "colleagues": [
                {"name": "Zonder adres", "email": ""},
                {"name": "Een", "email": "een@example.org", "active": True},
                {"name": "Dubbel", "email": "EEN@example.org", "active": True},
                "geen object",
            ]
        }
    )

    assert [c.name for c in parsed] == ["Een"]
    with pytest.raises(WiesUnavailableError):
        parse_colleagues({"iets": "anders"})


# --- what is proposed ---------------------------------------------------------


def test_new_colleague_is_proposed_for_addition():
    proposals = propose([_colleague("nieuw@example.org", "Nieuw Persoon")], [])

    assert _actions(proposals) == [("add", "nieuw@example.org")]
    assert proposals[0].suborganization == "Digi Gilde"


def test_colleague_without_account_in_wies_is_not_added():
    assert propose([_colleague("weg@example.org", active=False)], []) == []


def test_matching_ignores_case():
    assert (
        propose(
            [_colleague("Collega@Example.org".lower())],
            [_person("COLLEGA@example.org")],
        )
        == []
    )


def test_person_without_account_in_wies_is_proposed_for_deactivation():
    proposals = propose(
        [_colleague("co@example.org", active=False)], [_person("co@example.org")]
    )

    assert _actions(proposals) == [("deactivate", "co@example.org")]
    assert "geen actief account" in proposals[0].reason


def test_person_unknown_in_wies_is_proposed_with_that_reason():
    proposals = propose([], [_person("alleen-grip@example.org")])

    assert _actions(proposals) == [("deactivate", "alleen-grip@example.org")]
    assert proposals[0].reason == "Niet bekend in Wies."


def test_inactive_person_with_account_is_proposed_for_reactivation():
    proposals = propose(
        [_colleague("co@example.org")], [_person("co@example.org", active=False)]
    )

    assert _actions(proposals) == [("reactivate", "co@example.org")]


def test_other_name_in_wies_is_proposed_as_rename():
    proposals = propose(
        [_colleague("co@example.org", "Nieuwe Naam")], [_person("co@example.org")]
    )

    assert _actions(proposals) == [("rename", "co@example.org")]
    assert (proposals[0].name, proposals[0].current_name) == ("Nieuwe Naam", "Co Llega")


def test_merk_filter_limits_additions_but_never_causes_deactivation():
    scope = parse_scope("Digi Gilde, Rijks ICT Gilde")
    colleagues = [
        _colleague("eigen@example.org", "Eigen Merk"),
        _colleague("ander@example.org", "Ander Merk", merk="Rijksconsultants"),
        _colleague("bekend@example.org", "Bekend Persoon", merk="Rijksconsultants"),
    ]

    proposals = propose(
        colleagues,
        [_person("bekend@example.org", "Bekend Persoon")],
        suborganizations=scope,
    )

    assert _actions(proposals) == [("add", "eigen@example.org")]


def test_local_stand_in_is_left_alone():
    assert propose([], [_person("ontwikkelaar@grip.invalid")]) == []


# --- through the API ----------------------------------------------------------


@pytest.fixture
def wies_answers(monkeypatch):
    """Let the routes see these colleagues instead of calling Wies."""

    def _set(colleagues, answers=()):
        async def _fetch(settings, **_):
            return list(colleagues), list(answers)

        monkeypatch.setattr(
            "grip.api.routes.integrations_wies.fetch_wies_state", _fetch
        )

    return _set


async def test_proposal_changes_nothing(
    client, db_session, create_person, wies_settings, wies_answers
):
    wies_settings()
    await create_person(
        "beheerder@example.org", name="Be Heerder", functions=["beheerder"]
    )
    wies_answers(
        [
            _colleague("beheerder@example.org", "Be Heerder"),
            _colleague("nieuw@example.org"),
        ]
    )

    response = await client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["wies_colleagues"] == 2
    assert [(p["action"], p["email"]) for p in body["proposals"]] == [
        ("add", "nieuw@example.org")
    ]
    emails = (await db_session.execute(select(Person.email))).scalars().all()
    assert "nieuw@example.org" not in emails


async def test_only_confirmed_changes_are_applied(
    client, db_session, create_person, wies_settings, wies_answers
):
    wies_settings()
    beheerder = await create_person(
        "beheerder@example.org", name="Be Heerder", functions=["beheerder"]
    )
    vertrokken = await create_person("vertrokken@example.org", name="Ver Trokken")
    wies_answers(
        [
            _colleague("beheerder@example.org", "Be Heerder"),
            _colleague("nieuw@example.org", "Nieuw Persoon"),
            _colleague("ook-nieuw@example.org", "Ook Nieuw"),
            _colleague("vertrokken@example.org", "Ver Trokken", active=False),
        ]
    )

    response = await client.post(
        URL,
        json={
            "changes": [
                {"action": "add", "email": "Nieuw@Example.org"},
                {"action": "deactivate", "email": "vertrokken@example.org"},
                # Not backed by Wies: refused, also for a beheerder.
                {"action": "add", "email": "verzonnen@example.org"},
            ]
        },
    )

    assert response.status_code == 200
    applied = {
        (c["action"], c["email"]): c["applied"] for c in response.json()["applied"]
    }
    assert applied == {
        ("add", "nieuw@example.org"): True,
        ("deactivate", "vertrokken@example.org"): True,
        ("add", "verzonnen@example.org"): False,
    }
    persons = {
        p.email: p for p in (await db_session.execute(select(Person))).scalars().all()
    }
    assert persons["nieuw@example.org"].name == "Nieuw Persoon"
    assert persons["nieuw@example.org"].is_active
    assert "ook-nieuw@example.org" not in persons  # proposed, not confirmed
    assert "verzonnen@example.org" not in persons
    await db_session.refresh(vertrokken)
    assert vertrokken.is_active is False

    audit = (
        (await db_session.execute(select(AuditLog).where(AuditLog.entity == "person")))
        .scalars()
        .all()
    )
    assert {(a.action, a.actor_id) for a in audit} == {
        ("create", beheerder.id),
        ("update", beheerder.id),
    }


async def test_beheerder_cannot_deactivate_themself(
    client, db_session, create_person, wies_settings, wies_answers
):
    wies_settings()
    beheerder = await create_person("beheerder@example.org", functions=["beheerder"])
    wies_answers([])

    response = await client.post(
        URL,
        json={"changes": [{"action": "deactivate", "email": "beheerder@example.org"}]},
    )

    assert response.json()["applied"][0]["applied"] is False
    await db_session.refresh(beheerder)
    assert beheerder.is_active


async def test_reconciliation_is_for_the_beheerder(
    client, create_person, wies_settings, wies_answers
):
    wies_settings()
    await create_person("beheerder@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])
    wies_answers([_colleague("nieuw@example.org")])
    client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))

    assert (await client.get(URL)).status_code == 403
    assert (
        await client.post(
            URL, json={"changes": [{"action": "add", "email": "nieuw@example.org"}]}
        )
    ).status_code == 403


async def test_off_while_wies_is_not_configured(client, create_person, wies_settings):
    wies_settings(WIES_BASE_URL="", WIES_API_KEY="")
    await create_person("beheerder@example.org", functions=["beheerder"])

    proposal = await client.get(URL)
    assert proposal.status_code == 200
    assert proposal.json()["configured"] is False
    assert proposal.json()["proposals"] == []
    assert (await client.post(URL, json={"changes": []})).status_code == 409


async def test_wies_outage_is_a_gateway_error(
    client, create_person, wies_settings, monkeypatch
):
    wies_settings()
    await create_person("beheerder@example.org", functions=["beheerder"])

    async def _down(settings, **_):
        raise wies_client.WiesUnavailableError("Wies is niet bereikbaar.")

    monkeypatch.setattr("grip.api.routes.integrations_wies.fetch_wies_state", _down)

    response = await client.get(URL)

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")
