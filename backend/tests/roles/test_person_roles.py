"""The roles of a person: reading, setting by hand, and following Wies."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from grip.access import schema_classes, unclassified_fields
from grip.access.types import DataClass
from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.integrations.wies.client import WiesColleague, WiesSkill, parse_colleagues
from grip.models.catalogue_role import CatalogueRole, PersonCatalogueRole
from grip.schema.person_roles import PersonRolesOut
from grip.services import catalogue_roles, person_roles
from grip.services.errors import DomainValidationError, NotFoundError

DEV = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PO = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
async def roles(db_session) -> dict[str, CatalogueRole]:
    await catalogue_roles.apply_wies_skills(
        db_session, [WiesSkill(DEV, "Developer"), WiesSkill(PO, "Product owner")]
    )
    await catalogue_roles.create_role(db_session, name="Coach", actor=None)
    found = (await db_session.execute(select(CatalogueRole))).scalars().all()
    return {r.name: r for r in found}


def _colleague(email, *skill_ids, skills=(), active=True) -> WiesColleague:
    return WiesColleague(
        public_id="c-1",
        name="Co Llega",
        email=email,
        active=active,
        skills=tuple(skills),
        skill_ids=tuple(skill_ids),
    )


async def _proposals(db, *colleagues):
    return [
        (p.action, p.person_name, p.role_name)
        for p in await person_roles.current_role_proposals(db, colleagues)
    ]


async def _confirm_all(db, *colleagues):
    proposals = await person_roles.current_role_proposals(db, colleagues)
    return await person_roles.apply_role_proposals(
        db, [p.key for p in proposals], proposals, actor=None
    )


# --- reading and setting by hand -------------------------------------------------


async def test_person_without_roles_has_none(db_session, create_person):
    person = await create_person("co@example.org")

    assert await person_roles.roles_of_person(db_session, person.id) == []
    assert await person_roles.roles_of_persons(db_session, [person.id]) == {}
    assert await person_roles.roles_of_persons(db_session, []) == {}


async def test_roles_set_by_hand_are_read_back_by_name(
    db_session, create_person, roles
):
    person = await create_person("co@example.org")

    links = await person_roles.set_person_roles(
        db_session,
        person.id,
        [roles["Product owner"].id, roles["Coach"].id],
        actor=None,
    )

    assert [(link.role.name, link.source) for link in links] == [
        ("Coach", "manual"),
        ("Product owner", "manual"),
    ]
    names = [r.name for r in await person_roles.roles_of_person(db_session, person.id)]
    assert names == ["Coach", "Product owner"]


async def test_a_role_that_is_switched_off_is_not_offered(
    db_session, create_person, roles
):
    person = await create_person("co@example.org")
    await person_roles.set_person_roles(
        db_session, person.id, [roles["Coach"].id], actor=None
    )
    await catalogue_roles.update_role(
        db_session, roles["Coach"].id, {"is_active": False}, actor=None
    )

    assert await person_roles.roles_of_person(db_session, person.id) == []
    kept = await person_roles.roles_of_person(
        db_session, person.id, include_inactive=True
    )
    assert [r.name for r in kept] == ["Coach"]


async def test_setting_replaces_the_set_and_keeps_the_source_of_what_stays(
    db_session, create_person, roles
):
    person = await create_person("co@example.org")
    await _confirm_all(db_session, _colleague("co@example.org", DEV))

    links = await person_roles.set_person_roles(
        db_session, person.id, [roles["Developer"].id, roles["Coach"].id], actor=None
    )
    assert {link.role.name: link.source for link in links} == {
        "Developer": "wies",
        "Coach": "manual",
    }
    cleared = await person_roles.set_person_roles(db_session, person.id, [], actor=None)
    assert cleared == []


async def test_unknown_person_or_role_is_refused(db_session, create_person, roles):
    person = await create_person("co@example.org")

    with pytest.raises(NotFoundError):
        await person_roles.set_person_roles(db_session, uuid4(), [], actor=None)
    with pytest.raises(DomainValidationError):
        await person_roles.set_person_roles(
            db_session, person.id, [uuid4()], actor=None
        )


# --- following Wies ---------------------------------------------------------------


def test_colleague_answer_carries_skill_ids_when_wies_sends_them():
    (with_ids,) = parse_colleagues(
        {
            "colleagues": [
                {
                    "name": "Co Llega",
                    "email": "co@example.org",
                    "skills": ["Developer"],
                    "skill_ids": [DEV],
                    "active": True,
                }
            ]
        }
    )
    (without,) = parse_colleagues(
        {
            "colleagues": [
                {"name": "Co Llega", "email": "co@example.org", "skills": ["Developer"]}
            ]
        }
    )

    assert with_ids.skill_ids == (DEV,)
    assert (without.skills, without.skill_ids) == (("Developer",), ())


async def test_skill_in_wies_is_proposed_as_role_and_nothing_changes_until_confirmed(
    db_session, create_person, roles
):
    person = await create_person("co@example.org", name="Co Llega")

    assert await _proposals(db_session, _colleague("co@example.org", DEV, PO)) == [
        ("add_role", "Co Llega", "Developer"),
        ("add_role", "Co Llega", "Product owner"),
    ]
    assert await person_roles.roles_of_person(db_session, person.id) == []


async def test_confirmed_roles_come_from_wies(db_session, create_person, roles):
    person = await create_person("co@example.org")

    outcome = await _confirm_all(db_session, _colleague("co@example.org", DEV))

    assert [applied for _, applied in outcome] == [True]
    links = await person_roles.person_role_links(db_session, person.id)
    assert [(link.role.name, link.source) for link in links] == [("Developer", "wies")]
    # In step: nothing left to propose.
    assert await _proposals(db_session, _colleague("co@example.org", DEV)) == []


async def test_skill_is_matched_on_its_name_when_wies_sends_no_ids(
    db_session, create_person, roles
):
    await create_person("co@example.org", name="Co Llega")

    proposals = await _proposals(
        db_session, _colleague("co@example.org", skills=["product  OWNER", "Onbekend"])
    )

    assert proposals == [("add_role", "Co Llega", "Product owner")]


async def test_role_dropped_in_wies_is_proposed_and_a_manual_role_is_left_alone(
    db_session, create_person, roles
):
    person = await create_person("co@example.org", name="Co Llega")
    await _confirm_all(db_session, _colleague("co@example.org", DEV, PO))
    await person_roles.set_person_roles(
        db_session,
        person.id,
        [roles["Developer"].id, roles["Product owner"].id, roles["Coach"].id],
        actor=None,
    )

    # Wies now knows only the developer skill; the coach role was set by hand.
    after = _colleague("co@example.org", DEV)
    assert await _proposals(db_session, after) == [
        ("drop_role", "Co Llega", "Product owner")
    ]
    await _confirm_all(db_session, after)

    names = [r.name for r in await person_roles.roles_of_person(db_session, person.id)]
    assert names == ["Coach", "Developer"]


async def test_role_the_person_already_has_by_hand_is_not_proposed_again(
    db_session, create_person, roles
):
    person = await create_person("co@example.org")
    await person_roles.set_person_roles(
        db_session, person.id, [roles["Developer"].id], actor=None
    )

    assert await _proposals(db_session, _colleague("co@example.org", DEV)) == []
    # And Wies dropping the skill does not take the hand-set role away.
    assert await _proposals(db_session, _colleague("co@example.org")) == []


async def test_only_active_persons_wies_knows_get_proposals(
    db_session, create_person, roles
):
    await create_person("weg@example.org", name="Weg", is_active=False)
    await create_person("onbekend@example.org", name="Onbekend")

    assert await _proposals(db_session, _colleague("weg@example.org", DEV)) == []


async def test_stale_confirmation_is_not_applied(db_session, create_person, roles):
    person = await create_person("co@example.org")
    proposals = await person_roles.current_role_proposals(
        db_session, [_colleague("co@example.org", DEV)]
    )

    outcome = await person_roles.apply_role_proposals(
        db_session,
        [("add_role", person.id, roles["Product owner"].id)],
        proposals,
        actor=None,
    )

    assert [applied for _, applied in outcome] == [False]
    assert await person_roles.roles_of_person(db_session, person.id) == []


# --- the catalogue and the people who hold a role -----------------------------------


async def test_merge_gives_people_the_role_that_stays_once(
    db_session, create_person, roles
):
    both = await create_person("beide@example.org")
    one = await create_person("een@example.org")
    await person_roles.set_person_roles(
        db_session, both.id, [roles["Coach"].id, roles["Developer"].id], actor=None
    )
    await person_roles.set_person_roles(
        db_session, one.id, [roles["Coach"].id], actor=None
    )

    await catalogue_roles.merge_roles(
        db_session, roles["Coach"].id, roles["Developer"].id, actor=None
    )

    for person in (both, one):
        names = [
            r.name for r in await person_roles.roles_of_person(db_session, person.id)
        ]
        assert names == ["Developer"]


async def test_skill_gone_from_wies_but_held_by_a_person_is_kept(
    db_session, create_person, roles
):
    person = await create_person("co@example.org", name="Co Llega")
    await _confirm_all(db_session, _colleague("co@example.org", DEV))

    counts = await catalogue_roles.apply_wies_skills(
        db_session, [WiesSkill(PO, "Product owner")]
    )

    assert (counts.deactivated, counts.deleted) == (1, 0)
    links = await person_roles.person_role_links(db_session, person.id)
    assert [(link.role.name, link.role.is_active) for link in links] == [
        ("Developer", False)
    ]
    # Taking it from the person is proposed, not done underneath them.
    assert await _proposals(db_session, _colleague("co@example.org")) == [
        ("drop_role", "Co Llega", "Developer")
    ]


# --- the routes -----------------------------------------------------------------


def test_a_persons_roles_are_staffing():
    assert unclassified_fields(PersonRolesOut) == []
    assert schema_classes(PersonRolesOut) == {DataClass.STAFFING}


async def test_beheerder_sets_roles_and_others_read_what_they_may(
    client, db_session, create_person, roles
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    person = await create_person("co@example.org")
    other = await create_person("ander@example.org")
    url = f"/api/people/{person.id}/roles"

    saved = await client.put(
        url, json={"role_ids": [str(roles["Developer"].id), str(roles["Coach"].id)]}
    )
    assert saved.status_code == 200
    assert [(i["name"], i["source"]) for i in saved.json()["items"]] == [
        ("Coach", "manual"),
        ("Developer", "manual"),
    ]
    assert (await client.get(f"/api/people/{uuid4()}/roles")).status_code == 404

    # The person reads the own roles; someone unrelated does not, and nobody
    # but the beheerder changes them.
    client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
    own = await client.get(url)
    assert [i["name"] for i in own.json()["items"]] == ["Coach", "Developer"]
    assert (await client.put(url, json={"role_ids": []})).status_code == 403
    client.cookies.set(DEV_PERSON_COOKIE, str(other.id))
    assert (await client.get(url)).status_code in (403, 404)


async def test_role_proposals_through_the_api(
    client, db_session, create_person, roles, monkeypatch, _test_app
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])
    person = await create_person("co@example.org", name="Co Llega")
    url = "/api/integrations/wies/role-proposals"

    off = (await client.get(url)).json()
    assert (off["configured"], off["proposals"]) == (False, [])
    assert (await client.post(url, json={"changes": []})).status_code == 409

    settings = get_settings().model_copy(
        update={"WIES_BASE_URL": "https://wies.example", "WIES_API_KEY": "sleutel"}
    )
    _test_app.dependency_overrides[get_settings] = lambda: settings

    async def _fetch(settings, **_):
        return [_colleague("co@example.org", DEV)]

    monkeypatch.setattr("grip.api.routes.person_roles.fetch_colleagues", _fetch)
    try:
        listed = (await client.get(url)).json()
        assert [
            (p["action"], p["person_name"], p["role_name"]) for p in listed["proposals"]
        ] == [("add_role", "Co Llega", "Developer")]
        change = {
            k: listed["proposals"][0][k] for k in ("action", "person_id", "role_id")
        }
        stale = {**change, "role_id": str(roles["Coach"].id)}
        done = (await client.post(url, json={"changes": [change, stale]})).json()
        assert [c["applied"] for c in done["applied"]] == [True, False]

        client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))
        assert (await client.get(url)).status_code == 403
        assert (await client.post(url, json={"changes": []})).status_code == 403
    finally:
        _test_app.dependency_overrides.pop(get_settings, None)

    names = [r.name for r in await person_roles.roles_of_person(db_session, person.id)]
    assert names == ["Developer"]
    links = (await db_session.execute(select(PersonCatalogueRole))).scalars().all()
    assert [link.source for link in links] == ["wies"]
