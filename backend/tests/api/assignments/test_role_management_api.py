"""Who owns and manages an assignment: its own act, apart from the content.

The beheerder may name and remove the owner and managers of any assignment,
because an owner can have left. That gives the beheerder no right to change
the assignment itself; only a role on it does, and taking that role is in
the audit log as what it is.
"""

from sqlalchemy import select

from grip.models.audit_log import AuditLog


def _url(world) -> str:
    return f"/api/assignments/{world.assignment.id}"


async def _role_audit(db, person_id) -> list[AuditLog]:
    rows = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity == "assignment_role")
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return [
        row
        for row in rows.scalars()
        if str(person_id)
        in (
            (row.new_value or {}).get("person_id"),
            (row.old_value or {}).get("person_id"),
        )
    ]


async def test_permissions_offer_the_beheerder_roles_and_nothing_else(world, as_person):
    body = (await as_person(world.beheerder).get(_url(world))).json()
    assert body["permissions"]["manage_roles"] is True
    assert body["permissions"]["edit_basic"] is False
    assert body["permissions"]["edit_financial"] is False
    assert body["allowed_transitions"] == []

    owner_view = (await as_person(world.owner).get(_url(world))).json()
    assert owner_view["permissions"]["manage_roles"] is True
    for person in (world.planner, world.lezer, world.member):
        view = (await as_person(person).get(_url(world))).json()
        assert view["permissions"]["manage_roles"] is False, person.name


async def test_beheerder_assigns_on_an_assignment_of_someone_else(
    world, as_person, db_session
):
    client = as_person(world.beheerder)
    response = await client.put(
        f"{_url(world)}/roles/{world.colleague.id}", json={"role": "owner"}
    )
    assert response.status_code == 200
    assert {(r["name"], r["role"]) for r in response.json()["roles"]} == {
        ("Cas Collega", "owner"),
        ("Eva Eigenaar", "manager"),
    }
    # Still no rights on the content afterwards.
    assert response.json()["permissions"]["edit_basic"] is False

    (row,) = await _role_audit(db_session, world.colleague.id)
    assert row.actor_id == world.beheerder.id
    assert row.new_value["role"] == "owner"
    assert row.new_value["basis"] == "function:beheerder"
    assert "self_assignment" not in row.new_value

    removed = await client.delete(f"{_url(world)}/roles/{world.owner.id}")
    assert removed.status_code == 200
    assert [r["name"] for r in removed.json()["roles"]] == ["Cas Collega"]
    (row,) = await _role_audit(db_session, world.owner.id)
    assert row.new_value == {"basis": "function:beheerder"}


async def test_beheerder_cannot_edit_content_without_a_role(world, as_person):
    client = as_person(world.beheerder)
    assert (
        await client.patch(_url(world), json={"notes": "Aangepast"})
    ).status_code == 403
    assert (
        await client.patch(f"/api/budget-lines/{world.line.id}", json={"fte": "0.5"})
    ).status_code == 403
    assert (
        await client.post(f"{_url(world)}/transition", json={"target": "quoted"})
    ).status_code == 403


async def test_self_assignment_by_the_beheerder_is_audited_as_such(
    world, as_person, db_session
):
    client = as_person(world.beheerder)
    response = await client.put(
        f"{_url(world)}/roles/{world.beheerder.id}", json={"role": "manager"}
    )
    assert response.status_code == 200
    body = response.json()
    # Now a manager through the relation, with a manager's rights.
    assert body["viewer_relations"] == ["manager"]
    assert body["permissions"]["edit_basic"] is True
    assert body["permissions"]["edit_financial"] is True

    (row,) = await _role_audit(db_session, world.beheerder.id)
    assert row.actor_id == world.beheerder.id
    assert row.new_value["basis"] == "function:beheerder"
    assert row.new_value["self_assignment"] is True

    assert (
        await client.patch(_url(world), json={"notes": "Aangepast"})
    ).status_code == 200

    # From here the beheerder acts as manager: nothing special to mark.
    await client.put(
        f"{_url(world)}/roles/{world.colleague.id}", json={"role": "manager"}
    )
    (row,) = await _role_audit(db_session, world.colleague.id)
    assert "basis" not in row.new_value


async def test_owner_changes_are_not_marked(world, as_person, db_session):
    await as_person(world.owner).put(
        f"{_url(world)}/roles/{world.colleague.id}", json={"role": "manager"}
    )
    (row,) = await _role_audit(db_session, world.colleague.id)
    assert "basis" not in row.new_value
    assert "self_assignment" not in row.new_value


async def test_planner_and_lezer_cannot_manage_roles(world, as_person):
    for person in (world.planner, world.lezer, world.member):
        client = as_person(person)
        put = await client.put(
            f"{_url(world)}/roles/{world.colleague.id}", json={"role": "manager"}
        )
        assert put.status_code == 403, person.name
        delete = await client.delete(f"{_url(world)}/roles/{world.owner.id}")
        assert delete.status_code == 403, person.name
    outsider = await as_person(world.outsider).put(
        f"{_url(world)}/roles/{world.colleague.id}", json={"role": "manager"}
    )
    assert outsider.status_code == 404


async def test_removing_the_last_owner_is_refused(world, as_person):
    for person in (world.owner, world.beheerder):
        client = as_person(person)
        removed = await client.delete(f"{_url(world)}/roles/{world.owner.id}")
        assert removed.status_code == 422, person.name
        assert "eigenaar" in removed.text
        # Nor by turning the owner into a manager.
        demoted = await client.put(
            f"{_url(world)}/roles/{world.owner.id}", json={"role": "manager"}
        )
        assert demoted.status_code == 422, person.name
    body = (await as_person(world.owner).get(_url(world))).json()
    assert [(r["name"], r["role"]) for r in body["roles"]] == [
        ("Eva Eigenaar", "owner")
    ]
