"""Persons through the API: who sees which fields of whom.

Fields of a data class the asker may not see are absent, not null.
"""

from tests.api.reference.conftest import JUNE, by_id

ROSTER = {
    "id",
    "name",
    "email",
    "is_active",
    "manager_id",
    "manager_name",
    "uri",
    "stage",
    "starts_on",
    "can_log_in",
}
# How someone is engaged, staffed and what they may do in grip. That someone
# is hired, from whom and until when is part of it; what it costs is not.
STAFFING = {
    "functions",
    "function_grants",
    "is_sole_beheerder",
    "is_hired",
    "current_assignment_count",
    "current_fte_pct",
    "hires",
}
RATE = {"billing_scale", "rate_category", "monthly_rate_cents", "scales"}
COST = {"cost_monthly_rate_cents", "margin_monthly_cents"}
HIRE_FACTS = {"id", "supplier", "valid_from", "valid_to", "contract_reference"}
HIRE_COST = {"cost_monthly_rate_cents", "notes"}


async def _people(client, **params):
    resp = await client.get("/api/people", params=params or JUNE)
    assert resp.status_code == 200
    return resp.json()


async def test_beheerder_sees_everyone_in_full(client, world, as_person):
    as_person(world.beheerder)
    body = await _people(client)
    assert body["may_manage"] is True
    assert len(body["items"]) == 8
    hired = by_id(body["items"], world.hired)
    assert set(hired) == ROSTER | STAFFING | RATE | COST
    assert hired["billing_scale"] == 14
    assert hired["rate_category"] == "D"
    assert hired["monthly_rate_cents"] == 1800000
    assert hired["is_hired"] is True
    assert hired["cost_monthly_rate_cents"] == 1500000
    assert hired["margin_monthly_cents"] == 300000
    assert hired["hires"][0]["supplier"] == "Voorbeeld Detachering"
    report = by_id(body["items"], world.report)
    assert report["manager_name"] == "Lies Leidinggevende"
    assert report["is_hired"] is False and report["cost_monthly_rate_cents"] is None
    assert by_id(body["items"], world.planner)["functions"] == ["planner"]


async def test_planner_sees_no_amounts(client, world, as_person):
    as_person(world.planner)
    body = await _people(client)
    assert body["may_manage"] is False
    assert len(body["items"]) == 8
    for item in body["items"]:
        if item["id"] == str(world.planner.id):
            continue
        assert set(item) == ROSTER | STAFFING
    hired = by_id(body["items"], world.hired)
    assert hired["is_hired"] is True
    assert not (RATE | COST) & set(hired)
    # From whom and until when, without what it costs.
    assert set(hired["hires"][0]) == HIRE_FACTS
    assert hired["hires"][0]["supplier"] == "Voorbeeld Detachering"
    assert hired["current_assignment_count"] == 1
    assert hired["current_fte_pct"] in ("100.000", "100")


async def test_line_manager_sees_rate_of_direct_reports_only(client, world, as_person):
    as_person(world.lead)
    body = await _people(client)
    ids = {item["id"] for item in body["items"]}
    assert ids == {str(world.lead.id), str(world.report.id)}
    report = by_id(body["items"], world.report)
    assert set(report) == ROSTER | STAFFING | RATE
    assert report["billing_scale"] == 14
    assert not COST & set(report)


async def test_person_sees_own_record_only(client, world, as_person):
    as_person(world.outsider)
    body = await _people(client)
    assert [item["id"] for item in body["items"]] == [str(world.outsider.id)]
    own = body["items"][0]
    assert set(own) == ROSTER | STAFFING | RATE
    assert own["billing_scale"] == 14


async def test_owner_sees_rate_and_cost_of_people_on_own_assignment(
    client, world, as_person
):
    as_person(world.owner)
    body = await _people(client)
    hired = by_id(body["items"], world.hired)
    assert set(hired) == ROSTER | RATE | COST | {"hires"}
    assert hired["cost_monthly_rate_cents"] == 1500000
    assert hired["margin_monthly_cents"] == 300000
    # The cost of the hire, not the staffing facts around it.
    assert set(hired["hires"][0]) == HIRE_COST

    # Someone on another assignment: the name, for staffing, and nothing more.
    report = by_id(body["items"], world.report)
    assert set(report) == ROSTER
    outsider = by_id(body["items"], world.outsider)
    assert set(outsider) == ROSTER


async def test_owner_loses_cost_outside_the_period_staffed(client, world, as_person):
    as_person(world.owner)
    body = await _people(client, period_start="2027-03-01", period_end="2027-03-31")
    hired = by_id(body["items"], world.hired)
    assert not COST & set(hired)


async def test_person_one_may_not_see_answers_not_found(client, world, as_person):
    as_person(world.outsider)
    assert (await client.get(f"/api/people/{world.hired.id}")).status_code == 404
    assert (
        await client.get("/api/people/00000000-0000-0000-0000-000000000000")
    ).status_code == 404
    own = await client.get(f"/api/people/{world.outsider.id}")
    assert own.status_code == 200 and own.json()["name"] == "Otto Overig"


async def test_inactive_persons_are_left_out_by_default(
    client, world, as_person, create_person
):
    await create_person("weg@example.org", name="Wim Weg", is_active=False)
    as_person(world.beheerder)
    assert len((await _people(client))["items"]) == 8
    body = await _people(client, include_inactive=True, **JUNE)
    assert len(body["items"]) == 9


async def test_invalid_period_is_refused(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.get(
        "/api/people", params={"period_start": "2026-07-01", "period_end": "2026-06-01"}
    )
    assert resp.status_code == 422


async def test_only_beheerder_manages_persons(client, world, as_person):
    target = world.report.id
    for person in (world.planner, world.lead, world.owner, world.report):
        as_person(person)
        assert (
            await client.post(
                "/api/people", json={"name": "Nieuw", "email": "nieuw@example.org"}
            )
        ).status_code == 403
        assert (
            await client.patch(f"/api/people/{target}", json={"name": "Anders"})
        ).status_code == 403
        assert (
            await client.post(
                f"/api/people/{target}/scales",
                json={"valid_from": "2026-07-01", "billing_scale": 15},
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/people/{target}/hires",
                json={
                    "supplier": "X",
                    "cost_monthly_rate_cents": 1,
                    "valid_from": "2026-01-01",
                },
            )
        ).status_code == 403
        assert (
            await client.put(f"/api/people/{target}/functions/beheerder")
        ).status_code == 403
        assert (
            await client.delete(f"/api/people/{world.planner.id}/functions/planner")
        ).status_code == 403


async def test_beheerder_creates_and_changes_a_person(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.post(
        "/api/people",
        json={
            "name": "Nora Nieuw",
            "email": "nora@example.org",
            "manager_id": str(world.lead.id),
        },
    )
    assert resp.status_code == 201
    person = resp.json()
    assert person["manager_name"] == "Lies Leidinggevende"
    assert person["functions"] == [] and person["billing_scale"] is None

    duplicate = await client.post(
        "/api/people", json={"name": "Dubbel", "email": "NORA@example.org"}
    )
    assert duplicate.status_code == 422

    resp = await client.patch(
        f"/api/people/{person['id']}", json={"manager_id": None, "name": "Nora N."}
    )
    assert resp.status_code == 200
    assert resp.json()["manager_id"] is None and resp.json()["name"] == "Nora N."

    resp = await client.patch(f"/api/people/{person['id']}", json={"is_active": False})
    assert resp.status_code == 200 and resp.json()["is_active"] is False


async def test_reporting_line_cannot_loop(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.patch(
        f"/api/people/{world.lead.id}", json={"manager_id": str(world.report.id)}
    )
    assert resp.status_code == 422


async def test_scale_history(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.post(
        f"/api/people/{world.report.id}/scales",
        json={"valid_from": "2026-07-01", "billing_scale": 12},
    )
    assert resp.status_code == 201
    scales = resp.json()["scales"]
    assert [(s["valid_from"], s["valid_to"], s["billing_scale"]) for s in scales] == [
        ("2026-01-01", "2026-06-30", 14),
        ("2026-07-01", None, 12),
    ]
    body = await _people(client, period_start="2026-08-01", period_end="2026-08-31")
    report = by_id(body["items"], world.report)
    assert report["billing_scale"] == 12 and report["rate_category"] == "C"

    overlap = await client.post(
        f"/api/people/{world.report.id}/scales",
        json={"valid_from": "2026-03-01", "billing_scale": 10},
    )
    assert overlap.status_code == 422


async def test_hire_add_and_remove(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.post(
        f"/api/people/{world.report.id}/hires",
        json={
            "supplier": "Voorbeeld Bureau",
            "cost_monthly_rate_cents": 1600000,
            "valid_from": "2026-01-01",
        },
    )
    assert resp.status_code == 201
    hire_id = resp.json()["hires"][0]["id"]

    wrong_person = await client.delete(
        f"/api/people/{world.outsider.id}/hires/{hire_id}"
    )
    assert wrong_person.status_code == 404
    assert (
        await client.delete(f"/api/people/{world.report.id}/hires/{hire_id}")
    ).status_code == 204
    body = await _people(client)
    assert by_id(body["items"], world.report)["hires"] == []


async def test_functions_are_granted_and_revoked(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.put(f"/api/people/{world.report.id}/functions/planner")
    assert resp.status_code == 200 and resp.json()["functions"] == ["planner"]
    # Granting twice changes nothing.
    resp = await client.put(f"/api/people/{world.report.id}/functions/planner")
    assert resp.json()["functions"] == ["planner"]

    as_person(world.report)
    assert set(by_id((await _people(client))["items"], world.hired)) == (
        ROSTER | STAFFING
    )

    as_person(world.beheerder)
    resp = await client.delete(f"/api/people/{world.report.id}/functions/planner")
    assert resp.status_code == 200 and resp.json()["functions"] == []
    assert (
        await client.put(f"/api/people/{world.report.id}/functions/koning")
    ).status_code == 422


async def test_last_beheerder_cannot_be_removed(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.delete(f"/api/people/{world.beheerder.id}/functions/beheerder")
    assert resp.status_code == 422
    assert "laatste beheerder" in resp.json()["detail"]
    resp = await client.patch(
        f"/api/people/{world.beheerder.id}", json={"is_active": False}
    )
    assert resp.status_code == 422

    await client.put(f"/api/people/{world.lead.id}/functions/beheerder")
    resp = await client.delete(f"/api/people/{world.beheerder.id}/functions/beheerder")
    assert resp.status_code == 200


async def test_beheerder_unbinds_a_login(client, world, as_person, db_session):
    world.report.oidc_subject = "sub-oud"
    await db_session.flush()
    url = f"/api/people/{world.report.id}/login"

    # Whether someone is bound, and unbinding, is for the beheerder only.
    for person in (world.planner, world.lead, world.report, world.outsider):
        as_person(person)
        assert (await client.get(url)).status_code == 403, person.name
        assert (await client.delete(url)).status_code == 403, person.name
    assert world.report.oidc_subject == "sub-oud"

    as_person(world.beheerder)
    state = (await client.get(url)).json()
    # The fact only: the subject itself is never shown.
    assert state == {"bound": True}
    response = await client.delete(url)
    assert response.status_code == 200, response.text
    assert response.json() == {"bound": False}
    assert world.report.oidc_subject is None
    assert (await client.get(url)).json() == {"bound": False}

    # Nothing left to unbind.
    again = await client.delete(url)
    assert again.status_code == 422
    assert "nog niet ingelogd" in again.json()["detail"]


async def test_grants_say_since_when_and_by_whom(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.put(f"/api/people/{world.report.id}/functions/tekenbevoegde")
    grants = resp.json()["function_grants"]
    assert len(grants) == 1
    assert grants[0]["function"] == "tekenbevoegde"
    assert grants[0]["granted_by_name"] == "Bea Beheerder"
    assert grants[0]["since"]

    # A grant made when the instance was set up has no person behind it.
    body = await _people(client)
    own = by_id(body["items"], world.beheerder)
    assert own["function_grants"][0]["granted_by_name"] is None


async def test_sole_beheerder_is_marked(client, world, as_person):
    as_person(world.beheerder)
    body = await _people(client)
    assert by_id(body["items"], world.beheerder)["is_sole_beheerder"] is True
    assert by_id(body["items"], world.planner)["is_sole_beheerder"] is False

    await client.put(f"/api/people/{world.lead.id}/functions/beheerder")
    body = await _people(client)
    assert by_id(body["items"], world.beheerder)["is_sole_beheerder"] is False
    assert by_id(body["items"], world.lead)["is_sole_beheerder"] is False


async def test_unknown_right_is_named_as_a_right(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.put(f"/api/people/{world.report.id}/functions/koning")
    assert resp.status_code == 422
    assert "recht in grip" in resp.json()["detail"]
