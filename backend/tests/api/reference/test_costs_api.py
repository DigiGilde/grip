"""Cost items, invoice lines and coverage through the API (data class B)."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from grip.services import costs


async def _hosting(db: AsyncSession, world, *, alfa_pct="30", beta_pct=None):
    """A hosting contract with a forecast of 15,000, covered by Alfa."""
    item = await costs.create_cost_item(
        db, description="Hostingcontract", budgeted_cents=1600000, actor=world.beheerder
    )
    await costs.add_invoice_line(
        db,
        item.id,
        kind="actual",
        amount_cents=1000000,
        reference="HOST-26-01",
        period=__import__("datetime").date(2026, 3, 1),
        actor=world.beheerder,
    )
    await costs.add_invoice_line(
        db,
        item.id,
        kind="estimate",
        amount_cents=500000,
        period=__import__("datetime").date(2026, 9, 1),
        actor=world.beheerder,
    )
    if alfa_pct:
        await costs.set_coverage(
            db, item.id, world.alfa_line.id, Decimal(alfa_pct), actor=world.beheerder
        )
    if beta_pct:
        await costs.set_coverage(
            db, item.id, world.beta_line.id, Decimal(beta_pct), actor=world.beheerder
        )
    return item


async def test_worked_example_thirty_percent_of_fifteen_thousand(
    client, world, as_person, db_session
):
    item = await _hosting(db_session, world)
    as_person(world.owner)
    resp = await client.get(f"/api/costs/{item.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["budgeted_cents"] == 1600000
    assert body["forecast_cents"] == 1500000
    assert body["actual_cents"] == 1000000 and body["estimate_cents"] == 500000
    assert body["covered_cents"] == 450000
    assert body["uncovered_cents"] == 1050000
    assert Decimal(body["pct_total"]) == Decimal(30)
    assert len(body["invoice_lines"]) == 2
    coverage = body["coverages"][0]
    assert coverage["assignment_name"] == "Opdracht Alfa"
    assert coverage["amount_cents"] == 450000
    assert coverage["may_edit"] is True
    assert body["may_edit"] is True


async def test_year_filter_counts_only_that_year(client, world, as_person, db_session):
    item = await _hosting(db_session, world)
    as_person(world.beheerder)
    body = (await client.get(f"/api/costs/{item.id}", params={"year": 2027})).json()
    assert body["forecast_cents"] == 0 and body["invoice_lines"] == []
    body = (await client.get("/api/costs", params={"year": 2026})).json()
    assert body["items"][0]["forecast_cents"] == 1500000


async def test_who_sees_cost_items(client, world, as_person, db_session):
    item = await _hosting(db_session, world)
    for person in (world.beheerder, world.lezer, world.owner):
        as_person(person)
        body = (await client.get("/api/costs")).json()
        assert [i["id"] for i in body["items"]] == [str(item.id)]
    # Class B is not for the planner, a line manager, someone staffed on the
    # assignment or anyone else.
    for person in (world.planner, world.lead, world.hired, world.outsider):
        as_person(person)
        body = (await client.get("/api/costs")).json()
        assert body["items"] == [] and body["may_create"] is False
        assert (await client.get(f"/api/costs/{item.id}")).status_code == 404
        assert (
            await client.patch(f"/api/costs/{item.id}", json={"description": "x"})
        ).status_code == 404
        assert (
            await client.post("/api/costs", json={"description": "x"})
        ).status_code == 403
        assert (await client.get("/api/costs/coverage-options")).json()["items"] == []


async def test_reader_cannot_change(client, world, as_person, db_session):
    item = await _hosting(db_session, world)
    as_person(world.lezer)
    assert (
        await client.patch(f"/api/costs/{item.id}", json={"description": "x"})
    ).status_code == 403
    assert (
        await client.post(
            f"/api/costs/{item.id}/invoice-lines",
            json={"kind": "actual", "amount_cents": 100},
        )
    ).status_code == 403
    assert (
        await client.put(
            f"/api/costs/{item.id}/coverage/{world.alfa_line.id}", json={"pct": "10"}
        )
    ).status_code == 403


async def test_share_of_an_assignment_one_may_not_see_stays_anonymous(
    client, world, as_person, db_session
):
    item = await _hosting(db_session, world, beta_pct="50")
    as_person(world.owner)
    body = (await client.get(f"/api/costs/{item.id}")).json()
    assert [c["assignment_name"] for c in body["coverages"]] == ["Opdracht Alfa"]
    assert Decimal(body["hidden_coverage_pct"]) == Decimal(50)
    assert Decimal(body["pct_total"]) == Decimal(80)
    assert "Opdracht Beta" not in str(body)

    as_person(world.beheerder)
    body = (await client.get(f"/api/costs/{item.id}")).json()
    assert len(body["coverages"]) == 2
    assert Decimal(body["hidden_coverage_pct"]) == Decimal(0)


async def test_owner_manages_a_cost_item_end_to_end(client, world, as_person):
    as_person(world.owner)
    assert (await client.get("/api/costs")).json()["may_create"] is True
    resp = await client.post(
        "/api/costs", json={"description": "Licenties", "budgeted_cents": 800000}
    )
    assert resp.status_code == 201
    item = resp.json()
    assert item["may_edit"] is True and item["coverages"] == []

    resp = await client.post(
        f"/api/costs/{item['id']}/invoice-lines",
        json={
            "kind": "actual",
            "amount_cents": 200000,
            "reference": "LIC-26-01",
            "period": "2026-02-01",
        },
    )
    assert resp.status_code == 201
    line_id = resp.json()["invoice_lines"][0]["id"]

    options = (await client.get("/api/costs/coverage-options")).json()["items"]
    assert [o["assignment_name"] for o in options] == ["Opdracht Alfa"]

    resp = await client.put(
        f"/api/costs/{item['id']}/coverage/{world.alfa_line.id}", json={"pct": "60"}
    )
    assert resp.status_code == 200
    assert resp.json()["covered_cents"] == 120000
    assert resp.json()["uncovered_cents"] == 80000

    resp = await client.patch(
        f"/api/costs/{item['id']}", json={"description": "Licenties 2026"}
    )
    assert resp.status_code == 200 and resp.json()["description"] == "Licenties 2026"

    resp = await client.delete(f"/api/costs/{item['id']}/invoice-lines/{line_id}")
    assert resp.status_code == 200 and resp.json()["invoice_lines"] == []

    resp = await client.delete(f"/api/costs/{item['id']}/coverage/{world.alfa_line.id}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/costs/{item['id']}")).json()["coverages"] == []


async def test_more_than_hundred_percent_is_refused(
    client, world, as_person, db_session
):
    item = await _hosting(db_session, world, alfa_pct=None, beta_pct="80")
    # The owner of Alfa may add cost items, and this one has coverage only
    # from Beta, so the owner does not see it.
    as_person(world.owner)
    assert (
        await client.put(
            f"/api/costs/{item.id}/coverage/{world.alfa_line.id}", json={"pct": "30"}
        )
    ).status_code == 404

    as_person(world.beheerder)  # owner of Beta
    resp = await client.put(
        f"/api/costs/{item.id}/coverage/{world.beta_line.id}", json={"pct": "100"}
    )
    assert resp.status_code == 200
    # Beta is at 100 percent now; Alfa cannot add to it, whoever asks.
    await costs.set_coverage(
        db_session, item.id, world.beta_line.id, Decimal(80), actor=world.beheerder
    )
    resp = await client.put(
        f"/api/costs/{item.id}/coverage/{world.beta_line.id}", json={"pct": "100.5"}
    )
    assert resp.status_code == 422


async def test_service_message_when_shares_exceed_hundred(
    client, world, as_person, db_session
):
    item = await _hosting(db_session, world, alfa_pct="30", beta_pct="50")
    as_person(world.owner)
    resp = await client.put(
        f"/api/costs/{item.id}/coverage/{world.alfa_line.id}", json={"pct": "60"}
    )
    assert resp.status_code == 422
    assert "meer dan 100 kan niet" in resp.json()["detail"]


async def test_coverage_needs_edit_rights_on_the_assignment_of_the_line(
    client, world, as_person, db_session
):
    item = await _hosting(db_session, world)
    as_person(world.owner)
    resp = await client.put(
        f"/api/costs/{item.id}/coverage/{world.beta_line.id}", json={"pct": "10"}
    )
    assert resp.status_code == 403
    resp = await client.delete(f"/api/costs/{item.id}/coverage/{world.beta_line.id}")
    assert resp.status_code == 403


async def test_unknown_ids_are_not_found(client, world, as_person, db_session):
    item = await _hosting(db_session, world)
    as_person(world.owner)
    zero = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/costs/{zero}")).status_code == 404
    assert (
        await client.delete(f"/api/costs/{item.id}/invoice-lines/{zero}")
    ).status_code == 404
    assert (
        await client.put(f"/api/costs/{item.id}/coverage/{zero}", json={"pct": "10"})
    ).status_code == 404


async def test_beheerder_adds_and_changes_cost_items(client, world, as_person):
    as_person(world.beheerder)
    assert (await client.get("/api/costs")).json()["may_create"] is True
    resp = await client.post(
        "/api/costs", json={"description": "Licenties", "budgeted_cents": 100000}
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    resp = await client.patch(
        f"/api/costs/{item['id']}", json={"description": "Licenties 2026"}
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Licenties 2026"


async def test_an_uncovered_cost_item_is_managed_by_its_creator(
    client, world, as_person
):
    """Nothing covers it yet, so no assignment gives anyone rights on it."""
    as_person(world.owner)
    resp = await client.post("/api/costs", json={"description": "Hosting"})
    assert resp.status_code == 201, resp.text
    own = resp.json()["id"]
    assert (await client.get(f"/api/costs/{own}")).status_code == 200
    assert (
        await client.patch(f"/api/costs/{own}", json={"description": "Hosting 2026"})
    ).status_code == 200

    as_person(world.beheerder)
    resp = await client.post("/api/costs", json={"description": "Van de beheerder"})
    other = resp.json()["id"]
    # The beheerder sees and changes every item, also the owner's.
    assert (
        await client.patch(f"/api/costs/{own}", json={"budgeted_cents": 5})
    ).status_code == 200

    # The owner manages an assignment, but did not create this one.
    as_person(world.owner)
    assert (await client.get(f"/api/costs/{other}")).status_code == 404
    assert (
        await client.patch(f"/api/costs/{other}", json={"description": "x"})
    ).status_code == 404
    listed = [i["id"] for i in (await client.get("/api/costs")).json()["items"]]
    assert own in listed and other not in listed

    # A reader sees both and changes neither.
    as_person(world.lezer)
    assert (await client.get(f"/api/costs/{other}")).status_code == 200
    assert (
        await client.patch(f"/api/costs/{own}", json={"description": "x"})
    ).status_code == 403


async def test_the_creator_hands_over_once_a_budget_covers_the_item(
    client, world, as_person, db_session
):
    as_person(world.owner)
    own = (await client.post("/api/costs", json={"description": "Hosting"})).json()[
        "id"
    ]
    # Only Beta covers it now; the owner of Alfa created it but no longer
    # manages it.
    await costs.set_coverage(
        db_session, own, world.beta_line.id, Decimal(40), actor=world.beheerder
    )
    assert (await client.get(f"/api/costs/{own}")).status_code == 404
