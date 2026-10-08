"""A person who is hired exists in grip before Wies knows them.

Planned and counted from the hire, proposed to Wies, linked to the address
when it arrives, and removed on both sides when the hire falls through.
All names, addresses and data are fictional.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from grip.calc import Month
from grip.core.auth import resolve_person_for_login
from grip.integrations.wies.client import (
    WiesColleague,
    WiesProposalAnswer,
    parse_colleagues,
    parse_proposal_answers,
)
from grip.integrations.wies.reconcile import propose
from grip.models.assignment import Allocation
from grip.models.audit_log import AuditLog
from grip.models.person import Person
from grip.models.person_standing import ColleagueProposal, PersonStanding
from grip.services import standing
from grip.services.errors import DomainValidationError
from grip.services.reports import steering

from .conftest import EXPORT_KEY

AUTH = {"Authorization": f"Bearer {EXPORT_KEY}"}
EXPORT_URL = "/api/integrations/wies/export"
PROPOSED_URL = "/api/integrations/wies/proposed-colleagues"
RECONCILIATION_URL = "/api/integrations/wies/reconciliation"
START = date(2026, 9, 1)


async def _hire(db_session, name="Nova Nieuw", **kw) -> Person:
    return await standing.create_prospective_colleague(
        db_session, name=name, start_date=START, actor=None, **kw
    )


def _colleague(email, name="Nova Nieuw", *, uri=None, public_id="wies-1", active=True):
    return WiesColleague(
        public_id=public_id,
        name=name,
        email=email,
        active=active,
        suborganization="Digi Gilde",
        grip_person_uri=uri,
    )


# --- the person exists, without an address -------------------------------------


async def test_hire_creates_a_person_without_address_with_uri_and_standing(db_session):
    person = await _hire(
        db_session,
        suborganization="Digi Gilde",
        source="recruitment",
        source_ref="V-2026-014",
    )

    assert person.email is None
    assert person.uri.endswith(f"/id/persoon/{person.id}")
    assert person.identity_source == "grip"
    row = await db_session.get(PersonStanding, person.id)
    assert (row.stage, row.start_date, row.source, row.source_ref) == (
        "prospective",
        START,
        "recruitment",
        "V-2026-014",
    )
    proposal = await db_session.get(ColleagueProposal, person.id)
    assert (proposal.state, proposal.suborganization) == ("open", "Digi Gilde")


async def test_two_persons_without_address_can_exist(db_session):
    first = await _hire(db_session, "Een Persoon")
    second = await _hire(db_session, "Twee Persoon")

    assert first.id != second.id
    assert first.uri != second.uri


async def test_every_person_gets_a_uri_whoever_creates_the_row(db_session):
    person = Person(name="Direct Aangemaakt", email="direct@example.org")
    db_session.add(person)
    await db_session.flush()

    assert person.uri.endswith(f"/id/persoon/{person.id}")


async def test_prospective_colleague_cannot_log_in_until_the_address_arrives(
    db_session,
):
    person = await _hire(db_session)

    refused = await resolve_person_for_login(
        db_session, sub="sub-nova", email="", email_verified=True
    )
    assert refused is None

    await standing.attach_identity_from_wies(
        db_session,
        person.id,
        email="Nova.Nieuw@Example.org",
        name="Nova Nieuw",
        wies_public_id="wies-1",
        actor=None,
    )
    logged_in = await resolve_person_for_login(
        db_session, sub="sub-nova", email="nova.nieuw@example.org", email_verified=True
    )

    assert logged_in is not None and logged_in.id == person.id
    assert person.identity_source == "wies"
    assert (await db_session.get(PersonStanding, person.id)).stage == "colleague"
    assert (await db_session.get(ColleagueProposal, person.id)).state == "confirmed"


async def test_address_of_another_person_is_not_attached(db_session, create_person):
    await create_person("bezet@example.org")
    person = await _hire(db_session)

    with pytest.raises(DomainValidationError):
        await standing.attach_identity_from_wies(
            db_session,
            person.id,
            email="bezet@example.org",
            name=None,
            wies_public_id=None,
            actor=None,
        )


async def test_planned_and_counted_in_occupancy_before_any_address(db_session, make):
    person = await _hire(db_session)
    assignment = await make.assignment()
    line = await make.line(assignment)
    await make.allocation(line, person, pct="80", start=START, end=date(2026, 12, 31))

    rows = await steering.occupancy(db_session, [Month(2026, 9), Month(2026, 10)])

    mine = [row for row in rows if row.person_id == person.id]
    assert len(mine) == 1
    assert mine[0].person_name == "Nova Nieuw"
    assert all(cell.available for cell in mine[0].cells)


async def test_people_api_marks_a_prospective_colleague(client, create_person):
    await create_person("beheerder@example.org", functions=["beheerder"])

    created = await client.post(
        "/api/people",
        json={
            "name": "Nova Nieuw",
            "start_date": "2026-09-01",
            "suborganization": "Digi Gilde",
        },
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] is None
    assert (body["stage"], body["starts_on"], body["can_log_in"]) == (
        "prospective",
        "2026-09-01",
        False,
    )
    assert body["uri"].endswith(body["id"])

    without_date = await client.post("/api/people", json={"name": "Zonder Datum"})
    assert without_date.status_code == 422


# --- what goes to Wies -----------------------------------------------------------


async def test_export_carries_the_uri_and_no_address_for_a_prospective_colleague(
    client, db_session, make, wies_settings
):
    wies_settings()
    person = await _hire(db_session)
    known = await make.person("bekend@example.org", "Bekend Persoon")
    assignment = await make.assignment()
    line = await make.line(assignment, fte="2")
    await make.allocation(line, person, start=START, end=date(2026, 12, 31))
    await make.allocation(line, known)

    response = await client.get(EXPORT_URL, headers=AUTH)

    assert response.status_code == 200
    placements = {
        p["person_uri"]: p
        for role in response.json()["assignments"][0]["roles"]
        for p in role["placements"]
    }
    assert placements[person.uri]["person_email"] is None
    assert placements[known.uri]["person_email"] == "bekend@example.org"


async def test_proposed_colleagues_need_the_key_and_carry_four_facts(
    client, db_session, wies_settings
):
    wies_settings()
    person = await _hire(db_session, suborganization="Digi Gilde")

    assert (await client.get(PROPOSED_URL)).status_code in (401, 403)
    response = await client.get(PROPOSED_URL, headers=AUTH)

    assert response.status_code == 200
    assert response.json()["proposals"] == [
        {
            "person_uri": person.uri,
            "name": "Nova Nieuw",
            "suborganization": "Digi Gilde",
            "start_date": "2026-09-01",
            "state": "open",
        }
    ]


async def test_withdrawn_hire_removes_planning_and_tells_wies_by_key_only(
    client, db_session, make, wies_settings
):
    wies_settings()
    person = await _hire(db_session, suborganization="Digi Gilde")
    assignment = await make.assignment()
    line = await make.line(assignment)
    await make.allocation(line, person, start=START, end=date(2026, 12, 31))
    uri = person.uri

    await standing.withdraw_hire(
        db_session, person.id, actor=None, reason="Kandidaat zag ervan af."
    )

    assert person.is_active is False
    left = (
        (
            await db_session.execute(
                select(Allocation).where(Allocation.person_id == person.id)
            )
        )
        .scalars()
        .all()
    )
    assert left == []
    proposals = (await client.get(PROPOSED_URL, headers=AUTH)).json()["proposals"]
    assert proposals == [
        {
            "person_uri": uri,
            "name": "",
            "suborganization": None,
            "start_date": None,
            "state": "withdrawn",
        }
    ]
    export = (await client.get(EXPORT_URL, headers=AUTH)).json()
    assert uri not in str(export)


async def test_withdrawn_hire_is_removed_after_the_retention_period(db_session):
    person = await _hire(db_session)
    person_id = person.id
    today = date(2026, 8, 1)
    await standing.withdraw_hire(
        db_session, person_id, actor=None, reason="Ging niet door.", today=today
    )

    assert await standing.purge_withdrawn(db_session, today=today) == 0
    assert (
        await standing.purge_withdrawn(db_session, today=today + timedelta(days=27))
        == 0
    )
    removed = await standing.purge_withdrawn(
        db_session, today=today + timedelta(days=28)
    )

    assert removed == 1
    gone = (
        await db_session.execute(select(Person).where(Person.id == person_id))
    ).scalar_one_or_none()
    assert gone is None or gone.name == "Vervallen aanstelling"
    names = [
        str(row.new_value)
        for row in (await db_session.execute(select(AuditLog))).scalars()
        if row.entity == "person" and row.action == "delete"
    ]
    assert names and all("Nova" not in value for value in names)


async def test_only_a_hire_that_has_not_started_can_be_withdrawn(
    db_session, create_person
):
    colleague = await create_person("allang@example.org")

    with pytest.raises(DomainValidationError):
        await standing.withdraw_hire(
            db_session, colleague.id, actor=None, reason="Vergissing."
        )


# --- the address comes back: no second person, in any order --------------------


def test_grip_proposed_first_then_wies_holds_the_uri():
    """Wies confirmed the proposal, so its colleague carries the URI."""
    person = Person(
        name="Nova Nieuw", email=None, uri="https://grip.example/id/persoon/1"
    )

    proposals = propose(
        [_colleague("nova.nieuw@example.org", uri=person.uri)], [person]
    )

    assert [(p.action, p.email, p.match) for p in proposals] == [
        ("link", "nova.nieuw@example.org", "uri")
    ]


def test_wies_staff_created_the_colleague_first_without_uri():
    """Staff made the colleague by hand; the equal name is offered as a link."""
    person = Person(
        name="Nova Nieuw", email=None, uri="https://grip.example/id/persoon/1"
    )

    proposals = propose([_colleague("nova.nieuw@example.org")], [person])

    assert [(p.action, p.match) for p in proposals] == [("link", "name"), ("add", None)]


def test_no_link_is_suggested_on_a_name_two_prospective_colleagues_share():
    persons = [
        Person(name="Nova Nieuw", email=None, uri="https://grip.example/id/persoon/1"),
        Person(name="Nova Nieuw", email=None, uri="https://grip.example/id/persoon/2"),
    ]

    proposals = propose([_colleague("nova.nieuw@example.org")], persons)

    assert [p.action for p in proposals] == ["add"]


def test_person_without_address_is_never_proposed_for_deactivation():
    person = Person(
        name="Nova Nieuw", email=None, uri="https://grip.example/id/persoon/1"
    )

    assert propose([], [person]) == []


def test_colleague_without_address_is_read_when_it_carries_the_uri():
    parsed = parse_colleagues(
        {
            "colleagues": [
                {"name": "Nova Nieuw", "email": "", "grip_person_uri": "u-1"},
                {"name": "Zonder Sleutel", "email": ""},
            ],
            "proposals": [
                {"grip_person_uri": "u-1", "state": "confirmed", "public_id": "w-1"},
                {"grip_person_uri": "", "state": "declined"},
            ],
        }
    )

    assert [(c.name, c.grip_person_uri) for c in parsed] == [("Nova Nieuw", "u-1")]
    assert parse_proposal_answers(
        {"proposals": [{"grip_person_uri": "u-1", "state": "confirmed"}]}
    ) == [WiesProposalAnswer(person_uri="u-1", state="confirmed", public_id=None)]


@pytest.fixture
def wies_answers(monkeypatch):
    def _set(colleagues, answers=()):
        async def _fetch(settings, **_):
            return list(colleagues), list(answers)

        monkeypatch.setattr(
            "grip.api.routes.integrations_wies.fetch_wies_state", _fetch
        )

    return _set


async def test_link_by_uri_attaches_the_address_and_creates_nobody(
    client, db_session, create_person, wies_settings, wies_answers
):
    wies_settings()
    await create_person(
        "beheerder@example.org", name="Be Heerder", functions=["beheerder"]
    )
    person = await _hire(db_session)
    before = len((await db_session.execute(select(Person.id))).all())
    wies_answers(
        [
            _colleague("beheerder@example.org", "Be Heerder", public_id="wies-0"),
            _colleague("nova.nieuw@example.org", uri=person.uri),
        ],
        [
            WiesProposalAnswer(
                person_uri=person.uri, state="confirmed", public_id="wies-1"
            )
        ],
    )

    proposal = await client.get(RECONCILIATION_URL)
    assert [(p["action"], p["match"]) for p in proposal.json()["proposals"]] == [
        ("link", "uri")
    ]
    assert proposal.json()["outgoing"][0]["state"] == "confirmed"

    applied = await client.post(
        RECONCILIATION_URL,
        json={"changes": [{"action": "link", "email": "nova.nieuw@example.org"}]},
    )

    assert applied.json()["applied"][0]["applied"] is True
    await db_session.refresh(person)
    assert person.email == "nova.nieuw@example.org"
    assert person.wies_public_id == "wies-1"
    assert len((await db_session.execute(select(Person.id))).all()) == before


async def test_link_and_add_of_the_same_address_at_once_gives_one_person(
    client, db_session, create_person, wies_settings, wies_answers
):
    """Both sides knew the person separately; the beheerder ticks both boxes."""
    wies_settings()
    await create_person(
        "beheerder@example.org", name="Be Heerder", functions=["beheerder"]
    )
    person = await _hire(db_session)
    before = len((await db_session.execute(select(Person.id))).all())
    wies_answers(
        [
            _colleague("beheerder@example.org", "Be Heerder", public_id="wies-0"),
            _colleague("nova.nieuw@example.org"),
        ]
    )

    applied = await client.post(
        RECONCILIATION_URL,
        json={
            "changes": [
                {"action": "link", "email": "nova.nieuw@example.org"},
                {"action": "add", "email": "nova.nieuw@example.org"},
            ]
        },
    )

    results = {(a["action"], a["applied"]) for a in applied.json()["applied"]}
    assert results == {("link", True), ("add", False)}
    assert len((await db_session.execute(select(Person.id))).all()) == before
    await db_session.refresh(person)
    assert person.email == "nova.nieuw@example.org"


async def test_declined_in_wies_is_shown_and_reopens_when_proposed_again(
    client, db_session, create_person, wies_settings, wies_answers
):
    wies_settings()
    beheerder = await create_person(
        "beheerder@example.org", name="Be Heerder", functions=["beheerder"]
    )
    person = await _hire(db_session)
    wies_answers(
        [_colleague("beheerder@example.org", "Be Heerder", public_id="wies-0")],
        [WiesProposalAnswer(person_uri=person.uri, state="declined")],
    )

    body = (await client.get(RECONCILIATION_URL)).json()

    assert [(o["name"], o["state"]) for o in body["outgoing"]] == [
        ("Nova Nieuw", "declined")
    ]
    await standing.propose_to_wies_as_colleague(
        db_session, person.id, actor=beheerder, suborganization="Rijks ICT Gilde"
    )
    proposal = await db_session.get(ColleagueProposal, person.id)
    assert (proposal.state, proposal.suborganization) == ("open", "Rijks ICT Gilde")
