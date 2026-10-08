"""The role catalogue: budget lines, the service, following Wies, and the routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.integrations.wies.client import WiesSkill, WiesUnavailableError, parse_skills
from grip.models.assignment import Assignment, BudgetLine, line_display_name
from grip.models.audit_log import AuditLog
from grip.models.catalogue_role import CatalogueRole, CatalogueRoleSyncRun
from grip.services import catalogue_roles as service
from grip.services.errors import DomainValidationError

URL = "/api/catalogue-roles"
SKILL_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SKILL_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
async def assignment(db_session) -> Assignment:
    assignment = Assignment(
        uri="https://grip.example/id/opdracht/rollen", name="Opdracht Alfa"
    )
    db_session.add(assignment)
    await db_session.flush()
    return assignment


def _line(assignment: Assignment, **kw) -> BudgetLine:
    values = {
        "assignment_id": assignment.id,
        "kind": "personnel",
        "fte": Decimal("1"),
        "rate_category": "D",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
    }
    values.update(kw)
    return BudgetLine(**values)


async def _roles(db) -> dict[str, CatalogueRole]:
    return {
        r.name: r for r in (await db.execute(select(CatalogueRole))).scalars().all()
    }


async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# --- the name of a line ---------------------------------------------------------


def test_display_name_is_role_plus_detail_without_saying_the_role_twice():
    assert line_display_name("Developer", "") == "Developer"
    assert line_display_name("Developer", "#2, vanaf Q2") == "Developer: #2, vanaf Q2"
    # A line from before the catalogue already names its role.
    assert line_display_name("Developer", "developer #2") == "developer #2"
    assert line_display_name(None, "Hosting") == "Hosting"


# --- a budget line and its role -------------------------------------------------


async def test_role_given_as_text_becomes_a_catalogue_entry(db_session, assignment):
    line = _line(assignment, description="#1", role="  Product   owner ")
    db_session.add(line)
    await db_session.flush()

    (entry,) = (await _roles(db_session)).values()
    assert (entry.name, entry.source, entry.needs_review) == (
        "Product owner",
        "manual",
        True,
    )
    assert (line.role, line.role_id) == ("Product owner", entry.id)
    assert line.description == "Product owner: #1"


async def test_the_same_word_in_other_capitals_is_the_same_role(db_session, assignment):
    db_session.add(_line(assignment, description="#1", role="Developer"))
    await db_session.flush()
    second = _line(assignment, description="#2", role="developer")
    third = _line(assignment, description="#3", role="DEVELOPER")
    db_session.add_all([second, third])
    await db_session.flush()

    assert list(await _roles(db_session)) == ["Developer"]
    assert (second.role, third.role) == ("Developer", "Developer")
    assert second.role_id == third.role_id


async def test_two_new_lines_with_one_new_role_in_one_flush(db_session, assignment):
    db_session.add_all(
        [
            _line(assignment, description="#1", role="Tester"),
            _line(assignment, role="tester"),
        ]
    )
    await db_session.flush()

    assert list(await _roles(db_session)) == ["Tester"]


async def test_role_given_as_reference_gets_its_name(db_session, assignment):
    entry = await service.create_role(db_session, name="Architect", actor=None)
    line = _line(assignment, role_id=entry.id)
    db_session.add(line)
    await db_session.flush()

    assert (line.role, line.description) == ("Architect", "Architect")


async def test_changing_and_clearing_the_role_of_a_line(db_session, assignment):
    line = _line(assignment, description="Extra handen", role="Developer")
    db_session.add(line)
    await db_session.flush()

    line.role = "tester"
    await db_session.flush()
    assert (line.role, (await _roles(db_session))["tester"].id) == (
        "tester",
        line.role_id,
    )

    line.role = None
    await db_session.flush()
    assert (line.role, line.role_id, line.description) == (None, None, "Extra handen")

    line.role = "   "
    await db_session.flush()
    assert (line.role, line.role_id) == (None, None)


async def test_a_line_needs_a_role_or_a_description(db_session, assignment):
    from sqlalchemy.exc import IntegrityError

    db_session.add(_line(assignment))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_description_can_be_searched_and_sorted_in_sql(db_session, assignment):
    db_session.add_all(
        [
            _line(assignment, description="#2", role="Developer"),
            _line(assignment, role="Developer"),
            _line(assignment, description="Developer nummer drie", role="developer"),
            _line(assignment, description="Losse regel"),
        ]
    )
    await db_session.flush()

    names = (
        (
            await db_session.execute(
                select(BudgetLine.description)
                .where(BudgetLine.description.ilike("developer%"))
                .order_by(func.length(BudgetLine.description))
            )
        )
        .scalars()
        .all()
    )

    # The same names the model gives, computed by the database.
    assert names == ["Developer", "Developer: #2", "Developer nummer drie"]


async def test_the_database_refuses_a_name_the_catalogue_does_not_hold(
    db_session, assignment
):
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    line = _line(assignment, role="Developer")
    db_session.add(line)
    await db_session.flush()

    # Around the model, straight to the table.
    with pytest.raises(IntegrityError):
        await db_session.execute(
            update(BudgetLine.__table__)
            .where(BudgetLine.id == line.id)
            .values(role="Iets anders")
        )


# --- the service ----------------------------------------------------------------


async def test_asking_for_an_existing_name_returns_that_role(db_session):
    first = await service.create_role(db_session, name="Developer", actor=None)
    again = await service.create_role(db_session, name=" developer ", actor=None)

    assert again.id == first.id
    assert await _count(db_session, CatalogueRole) == 1


async def test_a_role_that_is_switched_off_is_not_handed_out(db_session):
    role = await service.create_role(db_session, name="Developer", actor=None)
    await service.update_role(db_session, role.id, {"is_active": False}, actor=None)

    with pytest.raises(DomainValidationError, match="uitgeschakeld"):
        await service.create_role(db_session, name="developer", actor=None)
    assert [r.role.name for r in await service.list_roles(db_session)] == []
    listed = await service.list_roles(db_session, include_inactive=True)
    assert [r.role.name for r in listed] == ["Developer"]


async def test_rename_renames_the_role_on_every_line(db_session, assignment):
    line = _line(assignment, description="#2", role="Developer")
    db_session.add(line)
    await db_session.flush()

    await service.update_role(
        db_session, line.role_id, {"name": "Ontwikkelaar"}, actor=None
    )

    assert (line.role, line.description) == ("Ontwikkelaar", "Ontwikkelaar: #2")
    stored = (
        await db_session.execute(
            select(BudgetLine.__table__.c.role).where(BudgetLine.id == line.id)
        )
    ).scalar_one()
    assert stored == "Ontwikkelaar"


async def test_rename_to_an_existing_name_asks_for_a_merge(db_session):
    await service.create_role(db_session, name="Developer", actor=None)
    other = await service.create_role(db_session, name="Ontwikkelaar", actor=None)

    with pytest.raises(DomainValidationError, match="Voeg de twee samen"):
        await service.update_role(
            db_session, other.id, {"name": "developer"}, actor=None
        )
    # Another spelling of the own name is a rename like any other.
    renamed = await service.update_role(
        db_session, other.id, {"name": "ontwikkelaar"}, actor=None
    )
    assert renamed.name == "ontwikkelaar"


async def test_merge_moves_the_lines_and_removes_the_source(db_session, assignment):
    kept = _line(assignment, description="#1", role="Developer")
    moved = _line(assignment, description="#2", role="Ontwikkelaar")
    db_session.add_all([kept, moved])
    await db_session.flush()
    roles = await _roles(db_session)
    source_id = roles["Ontwikkelaar"].id

    target, count = await service.merge_roles(
        db_session, source_id, roles["Developer"].id, actor=None
    )

    assert count == 1
    assert list(await _roles(db_session)) == ["Developer"]
    assert (moved.role, moved.role_id) == ("Developer", target.id)
    assert target.needs_review is False
    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "catalogue_role", AuditLog.action == "delete"
                )
            )
        )
        .scalars()
        .one()
    )
    assert audit.entity_id == str(source_id)
    assert audit.new_value["budget_lines_rewritten"] == 1
    assert audit.old_value["name"] == "Ontwikkelaar"


async def test_merge_hands_the_wies_link_to_the_role_that_stays(db_session):
    from_wies = CatalogueRole(
        name="Ontwikkelaar", source="wies", wies_public_id=SKILL_A
    )
    db_session.add(from_wies)
    manual = await service.create_role(db_session, name="Developer", actor=None)
    await db_session.flush()

    target, _ = await service.merge_roles(
        db_session, from_wies.id, manual.id, actor=None
    )

    assert (target.wies_public_id, target.source) == (SKILL_A, "wies")


async def test_merge_refuses_itself_and_two_wies_roles(db_session):
    a = CatalogueRole(name="A-rol", source="wies", wies_public_id=SKILL_A)
    b = CatalogueRole(name="B-rol", source="wies", wies_public_id=SKILL_B)
    db_session.add_all([a, b])
    await db_session.flush()

    with pytest.raises(DomainValidationError):
        await service.merge_roles(db_session, a.id, a.id, actor=None)
    with pytest.raises(DomainValidationError, match="Wies"):
        await service.merge_roles(db_session, a.id, b.id, actor=None)


async def test_search_puts_a_name_that_starts_with_the_query_first(db_session):
    for name in ("Product owner", "Scrum master", "Productmanager", "Adviseur product"):
        await service.create_role(db_session, name=name, actor=None)

    found = [r.role.name for r in await service.list_roles(db_session, query="PRODUCT")]

    # How the two that start with it are ordered is up to the collation.
    assert set(found[:2]) == {"Product owner", "Productmanager"}
    assert found[2:] == ["Adviseur product"]


async def test_usage_counts_the_lines(db_session, assignment):
    db_session.add_all(
        [_line(assignment, role="Developer"), _line(assignment, role="developer")]
    )
    await service.create_role(db_session, name="Tester", actor=None)
    await db_session.flush()

    usage = {r.role.name: r.usage_count for r in await service.list_roles(db_session)}

    assert usage == {"Developer": 2, "Tester": 0}


# --- following Wies -------------------------------------------------------------


def test_parse_skills_takes_id_and_name_and_refuses_anything_else():
    skills = parse_skills(
        {
            "skills": [
                {"public_id": SKILL_A, "name": " Developer ", "extra": "genegeerd"},
                {"public_id": SKILL_A, "name": "Dubbel"},
                {"public_id": "", "name": "Zonder id"},
                {"public_id": SKILL_B, "name": ""},
            ]
        }
    )

    assert skills == [WiesSkill(public_id=SKILL_A, name="Developer")]
    with pytest.raises(WiesUnavailableError):
        parse_skills({"colleagues": []})


async def test_first_sync_fills_the_catalogue(db_session):
    counts = await service.apply_wies_skills(
        db_session,
        [WiesSkill(SKILL_A, "Developer"), WiesSkill(SKILL_B, "Product owner")],
    )

    roles = await _roles(db_session)
    assert (counts.created, counts.seen) == (2, 2)
    assert (roles["Developer"].source, roles["Developer"].wies_public_id) == (
        "wies",
        SKILL_A,
    )
    assert roles["Developer"].needs_review is False


async def test_sync_adopts_a_manual_role_with_the_same_name(db_session, assignment):
    line = _line(assignment, role="developer")
    db_session.add(line)
    await db_session.flush()

    counts = await service.apply_wies_skills(
        db_session, [WiesSkill(SKILL_A, "Developer")]
    )

    (entry,) = (await _roles(db_session)).values()
    await db_session.refresh(line)
    assert counts.adopted == 1
    # The spelling of Wies wins, on the role and on the line.
    assert (entry.name, entry.source, entry.needs_review) == (
        "Developer",
        "wies",
        False,
    )
    assert (line.role, line.role_id) == ("Developer", entry.id)


async def test_sync_follows_a_rename_in_wies(db_session, assignment):
    await service.apply_wies_skills(db_session, [WiesSkill(SKILL_A, "Developer")])
    line = _line(assignment, role="Developer")
    db_session.add(line)
    await db_session.flush()

    counts = await service.apply_wies_skills(
        db_session, [WiesSkill(SKILL_A, "Ontwikkelaar")]
    )

    await db_session.refresh(line)
    assert counts.renamed == 1
    assert line.role == "Ontwikkelaar"


async def test_second_sync_changes_nothing(db_session):
    skills = [WiesSkill(SKILL_A, "Developer"), WiesSkill(SKILL_B, "Tester")]
    await service.apply_wies_skills(db_session, skills)

    counts = await service.apply_wies_skills(db_session, skills)

    assert (counts.unchanged, counts.created, counts.renamed) == (2, 0, 0)


async def test_skill_that_disappeared_is_switched_off_when_used_and_removed_otherwise(
    db_session, assignment
):
    await service.apply_wies_skills(
        db_session, [WiesSkill(SKILL_A, "Developer"), WiesSkill(SKILL_B, "Tester")]
    )
    db_session.add(_line(assignment, role="Developer"))
    await service.create_role(db_session, name="Eigen rol", actor=None)
    await db_session.flush()
    await service.apply_wies_skills(db_session, [WiesSkill("cccc", "Analist")])

    roles = await _roles(db_session)
    assert roles["Developer"].is_active is False
    assert "Tester" not in roles
    # A role kept by hand is no business of Wies.
    assert roles["Eigen rol"].is_active is True
    assert await _count(db_session, BudgetLine) == 1


async def test_skill_that_comes_back_is_switched_on_again(db_session, assignment):
    await service.apply_wies_skills(db_session, [WiesSkill(SKILL_A, "Developer")])
    db_session.add(_line(assignment, role="Developer"))
    await db_session.flush()
    await service.apply_wies_skills(db_session, [WiesSkill(SKILL_B, "Tester")])

    counts = await service.apply_wies_skills(
        db_session, [WiesSkill(SKILL_A, "Developer"), WiesSkill(SKILL_B, "Tester")]
    )

    assert counts.reactivated == 1
    assert (await _roles(db_session))["Developer"].is_active is True


async def test_rename_onto_another_role_is_left_for_a_merge(db_session):
    await service.apply_wies_skills(db_session, [WiesSkill(SKILL_A, "Developer")])
    await service.create_role(db_session, name="Ontwikkelaar", actor=None)
    # The manual role has the new name already and is not linked: Wies would
    # adopt it for a new skill, but this skill is known under another name.
    counts = await service.apply_wies_skills(
        db_session, [WiesSkill(SKILL_A, "Ontwikkelaar")]
    )

    assert counts.conflicts == 1
    assert set(await _roles(db_session)) == {"Developer", "Ontwikkelaar"}


async def test_run_is_recorded_and_a_failed_one_changes_nothing(
    db_session, monkeypatch
):
    settings = get_settings().model_copy(
        update={"WIES_BASE_URL": "https://wies.example", "WIES_API_KEY": "sleutel"}
    )
    ok = await service.run_wies_sync(
        db_session, settings, actor=None, skills=[WiesSkill(SKILL_A, "Developer")]
    )
    assert (ok.status, ok.result["created"]) == ("completed", 1)

    async def _down(settings, **_):
        raise WiesUnavailableError("Wies is niet bereikbaar.")

    monkeypatch.setattr("grip.services.catalogue_roles.fetch_skills", _down)
    failed = await service.run_wies_sync(db_session, settings, actor=None)
    empty = await service.run_wies_sync(db_session, settings, actor=None, skills=[])

    assert (failed.status, failed.error) == ("failed", "Wies is niet bereikbaar.")
    assert empty.status == "failed"
    assert list(await _roles(db_session)) == ["Developer"]
    assert await _count(db_session, CatalogueRoleSyncRun) == 3
    assert (await service.last_sync_run(db_session)).id == empty.id


# --- the routes -----------------------------------------------------------------


async def test_everyone_reads_and_the_list_says_what_the_reader_may_do(
    client, db_session, create_person
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    nobody = await create_person("zonder-functie@example.org")
    await service.create_role(db_session, name="Developer", actor=None)
    await service.create_role(db_session, name="Tester", actor=None)

    as_beheerder = (await client.get(URL, params={"q": "dev"})).json()
    client.cookies.set(DEV_PERSON_COOKIE, str(nobody.id))
    as_nobody = await client.get(URL)

    assert [r["name"] for r in as_beheerder["items"]] == ["Developer"]
    assert (as_beheerder["can_add"], as_beheerder["can_manage"]) == (True, True)
    assert as_nobody.status_code == 200
    assert [r["name"] for r in as_nobody.json()["items"]] == ["Developer", "Tester"]
    assert (as_nobody.json()["can_add"], as_nobody.json()["can_manage"]) == (
        False,
        False,
    )


async def test_planner_adds_a_role_on_the_spot_and_it_is_marked_for_review(
    client, db_session, create_person
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])
    lezer = await create_person("lezer@example.org", functions=["lezer"])

    client.cookies.set(DEV_PERSON_COOKIE, str(lezer.id))
    assert (await client.post(URL, json={"name": "Data-analist"})).status_code == 403

    client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))
    created = await client.post(URL, json={"name": "Data-analist"})
    again = await client.post(URL, json={"name": "data-analist"})

    assert created.status_code == 201
    assert (created.json()["needs_review"], created.json()["source"]) == (
        True,
        "manual",
    )
    assert (again.status_code, again.json()["id"]) == (200, created.json()["id"])
    entry = (await _roles(db_session))["Data-analist"]
    assert entry.created_by_id == planner.id


async def test_beheerder_adds_without_review_and_manages(
    client, db_session, create_person, assignment
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    db_session.add_all(
        [_line(assignment, role="Developer"), _line(assignment, role="Ontwikkelaar")]
    )
    await db_session.flush()
    roles = await _roles(db_session)

    created = await client.post(
        URL, json={"name": "Architect", "description": "Ontwerpt"}
    )
    assert (created.status_code, created.json()["needs_review"]) == (201, False)

    renamed = await client.patch(
        f"{URL}/{created.json()['id']}", json={"name": "Solution architect"}
    )
    assert renamed.json()["name"] == "Solution architect"
    clash = await client.patch(
        f"{URL}/{created.json()['id']}", json={"name": "developer"}
    )
    assert clash.status_code in (400, 409, 422)
    off = await client.patch(f"{URL}/{created.json()['id']}", json={"is_active": False})
    assert off.json()["is_active"] is False
    assert (
        await client.patch(f"{URL}/{created.json()['id']}", json={})
    ).status_code == 422

    merged = await client.post(
        f"{URL}/{roles['Ontwikkelaar'].id}/merge",
        json={"into_id": str(roles["Developer"].id)},
    )
    assert merged.status_code == 200
    assert merged.json()["budget_lines_rewritten"] == 1
    assert merged.json()["role"]["usage_count"] == 2
    assert (await client.get(f"{URL}/{roles['Ontwikkelaar'].id}")).status_code == 404


async def test_managing_is_for_the_beheerder(client, db_session, create_person):
    await create_person("beheerder@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])
    a = await service.create_role(db_session, name="Developer", actor=None)
    b = await service.create_role(db_session, name="Tester", actor=None)
    client.cookies.set(DEV_PERSON_COOKIE, str(planner.id))

    assert (await client.patch(f"{URL}/{a.id}", json={"name": "X"})).status_code == 403
    assert (
        await client.post(f"{URL}/{a.id}/merge", json={"into_id": str(b.id)})
    ).status_code == 403
    assert (await client.get(f"{URL}/sync")).status_code == 403
    assert (await client.post(f"{URL}/sync")).status_code == 403


async def test_sync_through_the_api(
    client, db_session, create_person, monkeypatch, _test_app
):
    await create_person("beheerder@example.org", functions=["beheerder"])

    off = (await client.get(f"{URL}/sync")).json()
    assert (off["wies_configured"], off["last_run"]) == (False, None)
    assert (await client.post(f"{URL}/sync")).status_code == 409

    settings = get_settings().model_copy(
        update={"WIES_BASE_URL": "https://wies.example", "WIES_API_KEY": "sleutel"}
    )
    _test_app.dependency_overrides[get_settings] = lambda: settings

    async def _fetch(settings, **_):
        return [WiesSkill(SKILL_A, "Developer"), WiesSkill(SKILL_B, "Tester")]

    monkeypatch.setattr("grip.services.catalogue_roles.fetch_skills", _fetch)
    try:
        status = (await client.post(f"{URL}/sync")).json()
    finally:
        _test_app.dependency_overrides.pop(get_settings, None)

    assert status["wies_configured"] is True
    assert status["last_run"]["status"] == "completed"
    assert status["last_run"]["result"]["created"] == 2
    assert status["roles"] == 2
