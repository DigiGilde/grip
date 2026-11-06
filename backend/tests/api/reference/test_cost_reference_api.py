"""A cost item another organisation keeps, through the API (ADR 0052, 0053).

Here such an item is a reference. What it stands for is read at the
executor; these tests stand in for that read. Executor, state, the lines
read there and the incomplete totals are class B, like the rest of the cost
item: whoever may not read it sees none of them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.organisation import Organisation
from grip.services import (
    assignments,
    cost_references,
    costs,
    requested_cost_items,
)
from grip.services.cost_references import FetchedItem, FetchedLine

GILDE = "https://grip.opdrachtnemer.example"
PROGRAMMA = "https://grip.programma.example"


async def _organisation(db: AsyncSession, name: str, instance_uri: str) -> Organisation:
    organisation = Organisation(name=name, instance_uri=instance_uri)
    db.add(organisation)
    await db.flush()
    return organisation


class Executor:
    """The supplier as this instance sees it: connected, and what it has."""

    def __init__(self, organisation: Organisation) -> None:
        self.organisation = organisation
        # By cost item id here; missing means "does not have it".
        self.items: dict[UUID, FetchedItem] = {}
        self.reachable = True

    async def lookup(self, _db: AsyncSession) -> set[UUID]:
        return {self.organisation.id}

    async def read(
        self, _db: AsyncSession, executor_id: UUID, ids: list[UUID]
    ) -> dict[UUID, FetchedItem | None] | None:
        assert executor_id == self.organisation.id
        if not self.reachable:
            return None
        return {i: self.items.get(i) for i in ids}


@pytest.fixture
async def gilde(db_session: AsyncSession):
    executor = Executor(await _organisation(db_session, "Voorbeeldgilde", GILDE))
    cost_references.register_executor_lookup(executor.lookup)
    cost_references.register_reader(executor.read)
    yield executor
    cost_references.clear()


async def _made(
    db: AsyncSession, world, gilde: Executor, line_id: UUID | None = None
) -> UUID:
    """A reference on Alfa that the supplier made and booked an invoice on."""
    item = await costs.create_cost_item(
        db,
        description="Zaal en catering",
        budgeted_cents=450000,
        executor_organisation_id=gilde.organisation.id,
        actor=world.beheerder,
    )
    await costs.set_coverage(
        db,
        item.id,
        line_id or world.alfa_line.id,
        Decimal("100"),
        actor=world.beheerder,
    )
    await cost_references.answered(db, item.id, 1, "applied")
    gilde.items[item.id] = FetchedItem(
        description="Zaal en catering",
        budgeted_cents=450000,
        lines=(
            FetchedLine(
                kind="actual",
                amount_cents=285000,
                reference="ZAAL-2026-031",
                period=date(2026, 3, 1),
            ),
        ),
    )
    return item.id


async def test_ask_an_executor(client, world, as_person, gilde):
    as_person(world.beheerder)
    options = (await client.get("/api/costs/executor-options")).json()["items"]
    assert options == [
        {"organisation_id": str(gilde.organisation.id), "name": "Voorbeeldgilde"}
    ]
    resp = await client.post(
        "/api/costs",
        json={
            "description": "Hotelovernachtingen",
            "budgeted_cents": 60000,
            "executor_organisation_id": str(gilde.organisation.id),
            "period": "2026-09-01",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["executor_name"] == "Voorbeeldgilde"
    assert body["reference_state"] == "waiting"
    # What was asked shows; nothing counts until the supplier has it.
    assert (body["description"], body["budgeted_cents"]) == (
        "Hotelovernachtingen",
        60000,
    )
    assert body["forecast_cents"] is None and body["actual_cents"] is None
    assert body["invoice_lines"] == [] and body["executor_lines"] == []

    # A change before the supplier has it replaces what was asked.
    item_id = body["id"]
    body = (
        await client.patch(f"/api/costs/{item_id}", json={"description": "Hotel"})
    ).json()
    assert (body["description"], body["reference_state"]) == ("Hotel", "waiting")
    # A reference keeps its executor.
    resp = await client.patch(
        f"/api/costs/{item_id}", json={"executor_organisation_id": None}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == cost_references.EXECUTOR_FIXED


async def test_an_organisation_without_a_connection_is_refused(
    client, world, as_person, db_session, gilde
):
    stranger = await _organisation(
        db_session, "Ander voorbeeld", "https://grip.ander.example"
    )
    as_person(world.beheerder)
    resp = await client.post(
        "/api/costs",
        json={"description": "Zaal", "executor_organisation_id": str(stranger.id)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == cost_references.NOT_CONNECTED


async def test_what_the_supplier_has_is_read_there(
    client, world, as_person, db_session, gilde
):
    item_id = await _made(db_session, world, gilde)
    as_person(world.beheerder)
    body = (await client.get(f"/api/costs/{item_id}")).json()
    assert body["reference_state"] == "found" and body["change_state"] is None
    assert body["description"] == "Zaal en catering"
    assert (body["budgeted_cents"], body["actual_cents"]) == (450000, 285000)
    assert body["invoice_lines"] == []
    assert body["executor_lines"] == [
        {
            "reference": "ZAAL-2026-031",
            "description": None,
            "kind": "actual",
            "amount_cents": 285000,
            "period": "2026-03-01",
        }
    ]
    resp = await client.post(
        f"/api/costs/{item_id}/invoice-lines",
        json={"kind": "estimate", "amount_cents": 1},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == cost_references.LINES_AT_EXECUTOR

    # A change is asked of the supplier; until it applies it, its values stay.
    resp = await client.patch(f"/api/costs/{item_id}", json={"budgeted_cents": 500000})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["change_state"], body["budgeted_cents"]) == ("waiting", 450000)

    # The figures of the line count what was read there.
    lines = (await client.get(f"/api/assignments/{world.alfa.id}/financial")).json()
    (line,) = lines["lines"]
    (cost,) = line["costs"]
    assert (cost["executor_name"], cost["reference_state"]) == (
        "Voorbeeldgilde",
        "found",
    )
    assert cost["total_cents"] == 285000
    assert line["incomplete_by"] == [] and lines["incomplete_by"] == []


async def test_what_cannot_be_read_makes_the_totals_incomplete(
    client, world, as_person, db_session, gilde
):
    item_id = await _made(db_session, world, gilde)
    gilde.reachable = False
    as_person(world.beheerder)
    body = (await client.get(f"/api/costs/{item_id}")).json()
    assert body["reference_state"] == "unreachable"
    for field in ("budgeted_cents", "forecast_cents", "actual_cents", "covered_cents"):
        assert body[field] is None, field
    assert body["coverages"][0]["amount_cents"] is None

    finance = (await client.get(f"/api/assignments/{world.alfa.id}/financial")).json()
    assert finance["incomplete_by"] == ["Voorbeeldgilde"]
    (line,) = finance["lines"]
    assert line["incomplete_by"] == ["Voorbeeldgilde"]
    assert line["costs"][0]["total_cents"] == 0

    overview = (await client.get(f"/api/assignments/{world.alfa.id}/overview")).json()
    assert overview["totals"]["incomplete_by"] == ["Voorbeeldgilde"]
    (line,) = overview["lines"]
    assert line["totals"]["incomplete_by"] == ["Voorbeeldgilde"]
    assert line["costs"][0]["amount_cents"] is None
    assert line["costs"][0]["reference_state"] == "unreachable"


async def test_a_refused_reference_can_go(client, world, as_person, db_session, gilde):
    item = await costs.create_cost_item(
        db_session,
        description="Zaal",
        budgeted_cents=1000,
        executor_organisation_id=gilde.organisation.id,
        actor=world.beheerder,
    )
    await cost_references.answered(db_session, item.id, 1, "refused")
    own = await costs.create_cost_item(
        db_session, description="Eigen", actor=world.beheerder
    )
    as_person(world.beheerder)
    body = (await client.get(f"/api/costs/{item.id}")).json()
    assert (body["reference_state"], body["description"]) == ("refused", "Zaal")
    assert (await client.delete(f"/api/costs/{own.id}")).status_code == 422
    assert (await client.delete(f"/api/costs/{item.id}")).status_code == 204
    assert (await client.get(f"/api/costs/{item.id}")).status_code == 404


async def test_the_supplier_sees_who_asked(client, world, as_person, db_session):
    programma = await _organisation(db_session, "Voorbeeldprogramma", PROGRAMMA)
    item, outcome = await requested_cost_items.receive_request(
        db_session,
        requester_organisation_id=programma.id,
        reference_uri=f"{PROGRAMMA}/id/kostenpost/5d6e7f80-0000-4000-8000-0000000000a1",
        sequence=1,
        description="Zaal en catering",
        budgeted_cents=450000,
        period=date(2026, 3, 1),
    )
    assert outcome == "created"
    as_person(world.beheerder)
    body = (await client.get(f"/api/costs/{item.id}")).json()
    assert body["requested_by_name"] == "Voorbeeldprogramma"
    assert body["reference_state"] is None and body["executor_name"] is None
    # The asked amount is the supplier's first expected invoice.
    assert [(line["kind"], line["amount_cents"]) for line in body["invoice_lines"]] == [
        ("estimate", 450000)
    ]
    # An item another organisation asked for is not passed on.
    resp = await client.patch(
        f"/api/costs/{item.id}",
        json={"executor_organisation_id": str(programma.id)},
    )
    assert resp.status_code == 422


async def test_references_do_not_leak(client, world, as_person, db_session, gilde):
    item_id = await _made(db_session, world, gilde)
    programma = await _organisation(db_session, "Voorbeeldprogramma", PROGRAMMA)
    requested, _ = await requested_cost_items.receive_request(
        db_session,
        requester_organisation_id=programma.id,
        reference_uri=f"{PROGRAMMA}/id/kostenpost/5d6e7f80-0000-4000-8000-0000000000a2",
        sequence=1,
        description="Hotel",
        budgeted_cents=60000,
    )
    secrets = ("Voorbeeldgilde", "Voorbeeldprogramma", "ZAAL-2026-031", "found")
    for reachable in (True, False):
        gilde.reachable = reachable
        for person in (world.planner, world.lead, world.hired, world.outsider):
            as_person(person)
            options = await client.get("/api/costs/executor-options")
            assert options.status_code == 403
            assert (await client.get(f"/api/costs/{item_id}")).status_code == 404
            assert (await client.get(f"/api/costs/{requested.id}")).status_code == 404
            text = (await client.get("/api/costs")).text
            for secret in (*secrets, "unreachable", "executor_lines"):
                assert secret not in text, secret
            for path in ("financial", "overview"):
                resp = await client.get(f"/api/assignments/{world.alfa.id}/{path}")
                for secret in (*secrets, "incomplete_by", "reference_state"):
                    assert secret not in resp.text, secret
    as_person(world.lezer)
    body = (await client.get(f"/api/costs/{item_id}")).json()
    assert (body["executor_name"], body["reference_state"]) == (
        "Voorbeeldgilde",
        "unreachable",
    )
    body = (await client.get(f"/api/costs/{requested.id}")).json()
    assert body["requested_by_name"] == "Voorbeeldprogramma"
    # A reader may see a reference, not choose an executor for one.
    assert (await client.get("/api/costs/executor-options")).status_code == 403


async def test_free_room_is_not_claimed_on_a_line_that_cannot_be_counted(
    client, world, as_person, db_session, gilde
):
    line = await assignments.add_budget_line(
        db_session,
        world.alfa.id,
        description="Bijeenkomsten en reizen",
        kind="fixed",
        amount_cents=6000000,
        year=2026,
        actor=world.beheerder,
    )
    await _made(db_session, world, gilde, line.id)
    as_person(world.beheerder)

    def kinds(body):
        return [signal["kind"] for signal in body["signals"]]

    url = f"/api/assignments/{world.alfa.id}/financial"
    readable = (await client.get(url)).json()
    assert "free_room" in kinds(readable)

    gilde.reachable = False
    unreadable = (await client.get(url)).json()
    assert unreadable["incomplete_by"] == ["Voorbeeldgilde"]
    assert "free_room" not in kinds(unreadable)


async def test_the_steering_costs_say_what_they_miss(
    client, world, as_person, db_session, gilde
):
    world.alfa.status = "accepted"
    await db_session.flush()
    item_id = await _made(db_session, world, gilde)
    as_person(world.beheerder)

    async def steering():
        response = await client.get("/api/reports/steering", params={"year": 2026})
        assert response.status_code == 200
        return response.json()

    body = await steering()
    assert body["costs"]["incomplete_by"] == []
    assert body["turnover"]["incomplete_by"] == []

    gilde.reachable = False
    body = await steering()
    assert body["costs"]["incomplete_by"] == ["Voorbeeldgilde"]
    (item,) = [i for i in body["costs"]["items"] if i["cost_item_id"] == str(item_id)]
    assert item["incomplete_by"] == ["Voorbeeldgilde"]
    assert body["turnover"]["incomplete_by"] == ["Voorbeeldgilde"]
