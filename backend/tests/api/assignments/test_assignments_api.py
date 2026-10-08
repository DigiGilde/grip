"""Assignments: who sees which, and which fields."""

from .conftest import by_id


async def test_beheerder_lists_all_with_amounts(world, as_person):
    response = await as_person(world.beheerder).get("/api/assignments")
    assert response.status_code == 200
    body = response.json()
    assert {i["name"] for i in body["items"]} == {
        "Opdracht Alfa 2026",
        "Opdracht Beta 2026",
    }
    alfa = by_id(body["items"], "id", world.assignment.id)
    assert alfa["quoted_amount_cents"] == 40000000
    assert alfa["client_name"] == "Voorbeeldministerie"
    assert alfa["owner_name"] == "Eva Eigenaar"
    assert body["can_create"] is True


async def test_planner_sees_assignments_without_money(world, as_person):
    # Class B is not for a planner: the field is absent, not null.
    body = (await as_person(world.planner).get("/api/assignments")).json()
    assert len(body["items"]) == 2
    for item in body["items"]:
        assert "quoted_amount_cents" not in item
        assert "name" in item


async def test_member_sees_only_own_assignment_without_money(world, as_person):
    body = (await as_person(world.member).get("/api/assignments")).json()
    assert [i["name"] for i in body["items"]] == ["Opdracht Alfa 2026"]
    assert "quoted_amount_cents" not in body["items"][0]
    assert body["can_create"] is False


async def test_outsider_sees_nothing(world, as_person):
    client = as_person(world.outsider)
    assert (await client.get("/api/assignments")).json()["items"] == []
    # Not readable is not known to exist.
    response = await client.get(f"/api/assignments/{world.assignment.id}")
    assert response.status_code == 404
    response = await client.get(f"/api/assignments/{world.assignment.id}/budget")
    assert response.status_code == 404
    response = await client.get(f"/api/assignments/{world.assignment.id}/overview")
    assert response.status_code == 404


async def test_detail_offers_transitions_only_to_who_may_edit(world, as_person):
    owner_view = (
        await as_person(world.owner).get(f"/api/assignments/{world.assignment.id}")
    ).json()
    assert owner_view["allowed_transitions"] == ["cancelled", "quoted", "requested"]
    assert owner_view["permissions"]["edit_basic"] is True
    assert owner_view["quoted_amount_cents"] == 40000000
    assert owner_view["context_refs"] == ["https://corpus.example/id/node/1"]
    assert [r["role"] for r in owner_view["roles"]] == ["owner"]

    member_view = (
        await as_person(world.member).get(f"/api/assignments/{world.assignment.id}")
    ).json()
    assert member_view["allowed_transitions"] == []
    assert member_view["permissions"]["edit_basic"] is False
    assert "quoted_amount_cents" not in member_view


async def test_create_update_and_transition(world, as_person):
    client = as_person(world.planner)
    created = await client.post(
        "/api/assignments",
        json={"name": " Opdracht Gamma 2026 ", "kind": "internal"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Opdracht Gamma 2026"
    assert body["status"] == "draft"
    # The creator became the owner.
    assert body["roles"][0]["name"] == "Pim Planner"
    assert "accepted" in body["allowed_transitions"]

    updated = await client.patch(
        f"/api/assignments/{body['id']}",
        json={"context_refs": ["https://corpus.example/id/node/7"]},
    )
    assert updated.status_code == 200
    assert updated.json()["context_refs"] == ["https://corpus.example/id/node/7"]

    moved = await client.post(
        f"/api/assignments/{body['id']}/transition", json={"target": "accepted"}
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "accepted"


async def test_member_cannot_change_or_create(world, as_person):
    client = as_person(world.member)
    url = f"/api/assignments/{world.assignment.id}"
    assert (await client.patch(url, json={"name": "Anders"})).status_code == 403
    assert (
        await client.post(f"{url}/transition", json={"target": "quoted"})
    ).status_code == 403
    assert (
        await client.post("/api/assignments", json={"name": "X"})
    ).status_code == 403
    assert (
        await client.put(f"{url}/roles/{world.member.id}", json={"role": "manager"})
    ).status_code == 403


async def test_roles(world, as_person):
    client = as_person(world.owner)
    url = f"/api/assignments/{world.assignment.id}/roles"
    added = await client.put(f"{url}/{world.colleague.id}", json={"role": "manager"})
    assert added.status_code == 200
    assert {(r["name"], r["role"]) for r in added.json()["roles"]} == {
        ("Eva Eigenaar", "owner"),
        ("Cas Collega", "manager"),
    }
    removed = await client.delete(f"{url}/{world.colleague.id}")
    assert removed.status_code == 200
    assert len(removed.json()["roles"]) == 1


async def test_person_options_need_someone_who_staffs(world, as_person):
    ok = await as_person(world.owner).get("/api/person-options")
    assert ok.status_code == 200
    assert "Lot Lid" in {p["name"] for p in ok.json()["items"]}
    assert (await as_person(world.member).get("/api/person-options")).status_code == 403
    assert (await as_person(world.lezer).get("/api/person-options")).status_code == 403


async def test_permissions_tell_the_screen_which_parts_to_offer(world, as_person):
    url = f"/api/assignments/{world.assignment.id}"

    async def permissions(person):
        return (await as_person(person).get(url)).json()["permissions"]

    owner = await permissions(world.owner)
    assert all(owner.values())

    planner = await permissions(world.planner)
    assert (
        planner["read_staffing"] and planner["read_roster"] and planner["edit_staffing"]
    )
    assert not planner["read_financial"] and not planner["edit_basic"]

    # A team member sees who is on the team, not how much time or money.
    member = await permissions(world.member)
    assert member["read_roster"]
    assert not member["read_staffing"] and not member["read_financial"]

    lezer = await permissions(world.lezer)
    assert lezer["read_financial"]
    assert not lezer["read_roster"] and not lezer["read_staffing"]


async def test_a_new_assignment_is_potential_and_needs_only_a_name(world, as_person):
    client = as_person(world.planner)
    created = await client.post("/api/assignments", json={"name": "Opdracht Zeta"})
    assert created.status_code == 201
    body = created.json()
    assert body["phase"] == "potential"
    assert body["status"] == "draft"
    assert body["status_since"] is not None
    assert "traffic_form" not in body
    # A field of an older client is ignored, not refused.
    again = await client.post(
        "/api/assignments", json={"name": "Opdracht Eta", "traffic_form": "document"}
    )
    assert again.status_code == 201


async def test_list_says_phase_and_what_a_potential_assignment_may_be_worth(
    world, as_person
):
    body = (await as_person(world.beheerder).get("/api/assignments")).json()
    alfa = by_id(body["items"], "id", world.assignment.id)
    assert alfa["phase"] == "potential"
    # No quote yet, so the budget stands in: 172,800 plus 15,000.
    assert alfa["pipeline_amount_cents"] == 18780000
    assert alfa["pipeline_amount_source"] == "budget"
    # Money is class B: a planner gets the phase, not the amount.
    planner = (await as_person(world.planner).get("/api/assignments")).json()
    alfa = by_id(planner["items"], "id", world.assignment.id)
    assert alfa["phase"] == "potential"
    assert "pipeline_amount_cents" not in alfa
    assert "pipeline_amount_source" not in alfa


async def test_detail_says_how_the_reader_relates_to_the_assignment(world, as_person):
    url = f"/api/assignments/{world.assignment.id}"
    assert (await as_person(world.owner).get(url)).json()["viewer_relations"] == [
        "owner"
    ]
    assert (await as_person(world.member).get(url)).json()["viewer_relations"] == [
        "member"
    ]
    assert (await as_person(world.beheerder).get(url)).json()["viewer_relations"] == [
        "function:beheerder"
    ]
