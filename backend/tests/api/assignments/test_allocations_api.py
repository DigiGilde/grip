"""Inzet: who sees whose time, whose amount, and the R14 signal."""

from datetime import date
from decimal import Decimal

from grip.calc import Month
from grip.services import month_close
from tests.lifecycle import accept

from .conftest import by_id

MEMBER_AMOUNT = 10800000
COLLEAGUE_AMOUNT = 5400000


async def test_planner_sees_time_and_signal_but_no_category_or_amount(world, as_person):
    body = (await as_person(world.planner).get("/api/allocations?year=2026")).json()
    assert body["can_add"] is True
    colleague = by_id(body["items"], "id", world.colleague_allocation.id)
    assert colleague["person_name"] == "Cas Collega"
    assert Decimal(colleague["fte_pct"]) == Decimal("30.00")
    assert colleague["category_mismatch"] is True
    assert colleague["can_edit"] is True
    for hidden in (
        "amount_cents",
        "line_category",
        "person_category",
        "mismatch_direction",
        "pricing_error",
    ):
        assert hidden not in colleague


async def test_owner_sees_amounts_and_categories(world, as_person):
    body = (await as_person(world.owner).get("/api/allocations?year=2026")).json()
    colleague = by_id(body["items"], "id", world.colleague_allocation.id)
    assert colleague["amount_cents"] == COLLEAGUE_AMOUNT
    assert colleague["line_category"] == "D"
    assert colleague["person_category"] == "C"
    assert colleague["mismatch_direction"] == "underrun"
    member = by_id(body["items"], "id", world.member_allocation.id)
    assert member["amount_cents"] == MEMBER_AMOUNT
    assert member["category_mismatch"] is False


async def test_member_sees_own_inzet_and_only_names_of_the_team(world, as_person):
    body = (await as_person(world.member).get("/api/allocations?year=2026")).json()
    assert body["can_add"] is False
    own = by_id(body["items"], "id", world.member_allocation.id)
    assert own["amount_cents"] == MEMBER_AMOUNT
    assert Decimal(own["fte_pct"]) == Decimal("50.00")
    assert own["can_edit"] is False
    other = by_id(body["items"], "id", world.colleague_allocation.id)
    assert other["person_name"] == "Cas Collega"
    for hidden in ("fte_pct", "start_date", "amount_cents", "category_mismatch"):
        assert hidden not in other


async def test_lezer_and_outsider_see_no_inzet(world, as_person):
    for person in (world.lezer, world.outsider):
        body = (await as_person(person).get("/api/allocations")).json()
        assert body["items"] == []


async def test_filters(world, as_person):
    client = as_person(world.planner)
    by_person = (
        await client.get(f"/api/allocations?person_id={world.member.id}")
    ).json()
    assert [i["person_name"] for i in by_person["items"]] == ["Lot Lid"]
    by_line = (
        await client.get(f"/api/allocations?budget_line_id={world.line.id}")
    ).json()
    assert len(by_line["items"]) == 2
    by_assignment = (
        await client.get(f"/api/allocations?assignment_id={world.other_assignment.id}")
    ).json()
    assert by_assignment["items"] == []


async def test_add_change_and_remove(world, as_person):
    client = as_person(world.planner)
    added = await client.post(
        "/api/allocations",
        json={
            "budget_line_id": str(world.line.id),
            "person_id": str(world.outsider.id),
            "start_date": "2026-03-01",
            "end_date": "2026-06-30",
            "fte_pct": "20",
        },
    )
    assert added.status_code == 201
    row = added.json()
    assert row["person_name"] == "Bo Buiten"
    assert "amount_cents" not in row

    changed = await client.patch(
        f"/api/allocations/{row['id']}", json={"fte_pct": "40"}
    )
    assert changed.status_code == 200
    assert Decimal(changed.json()["fte_pct"]) == Decimal("40.00")

    assert (await client.delete(f"/api/allocations/{row['id']}")).status_code == 204


async def test_only_planner_and_manager_edit(world, as_person):
    payload = {
        "budget_line_id": str(world.line.id),
        "person_id": str(world.outsider.id),
        "start_date": "2026-03-01",
        "end_date": "2026-06-30",
        "fte_pct": "20",
    }
    assert (
        await as_person(world.owner).post("/api/allocations", json=payload)
    ).status_code == 201
    for person in (world.member, world.lezer, world.outsider):
        client = as_person(person)
        assert (await client.post("/api/allocations", json=payload)).status_code == 403
    # A member may see the own inzet but not change it.
    response = await as_person(world.member).patch(
        f"/api/allocations/{world.member_allocation.id}", json={"fte_pct": "60"}
    )
    assert response.status_code == 403
    # Someone who cannot see it is told it does not exist.
    response = await as_person(world.outsider).patch(
        f"/api/allocations/{world.member_allocation.id}", json={"fte_pct": "60"}
    )
    assert response.status_code == 404


async def test_closed_month_refuses_a_shifted_period(world, as_person, db_session):
    await accept(db_session, world.assignment.id)
    await month_close.close_month(
        db_session, world.assignment.id, Month.of(date(2026, 1, 1)), actor=world.owner
    )
    response = await as_person(world.planner).patch(
        f"/api/allocations/{world.member_allocation.id}",
        json={"start_date": "2026-02-01"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "MonthClosedError"
    assert body["title"] == "Maand is afgesloten"
    assert "afgesloten" in body["detail"]


async def test_options(world, as_person):
    planner = (await as_person(world.planner).get("/api/allocations/options")).json()
    assert {p["name"] for p in planner["people"]} >= {"Lot Lid", "Cas Collega"}
    # Someone who only holds a right is a person, but not one to plan.
    assert "Lex Lezer" not in {p["name"] for p in planner["people"]}
    assert world.lezer.name == "Lex Lezer"
    assert [ln["description"] for ln in planner["lines"]] == ["Productmanager"]
    assert Decimal(planner["lines"][0]["fte"]) == Decimal("0.800")

    owner = (await as_person(world.owner).get("/api/allocations/options")).json()
    assert [ln["assignment_name"] for ln in owner["lines"]] == ["Opdracht Alfa 2026"]

    assert (
        await as_person(world.member).get("/api/allocations/options")
    ).status_code == 403


async def test_inzet_on_a_potential_assignment_is_tentative(
    world, as_person, db_session
):
    from grip.services import assignments

    client = as_person(world.planner)
    body = (await client.get("/api/allocations?year=2026")).json()
    assert all(item["tentative"] for item in body["items"])

    # After the client agrees it is firm.
    for target in ("quoted", "accepted"):
        await assignments.transition(
            db_session,
            world.assignment.id,
            target,
            actor=world.owner,
            enforce_readiness=False,
        )
    body = (await client.get("/api/allocations?year=2026")).json()
    assert not any(item["tentative"] for item in body["items"])


async def test_the_load_of_a_person_is_told_before_an_inzet_is_saved(world, as_person):
    """Above 100 percent is allowed, but said first: the months and what the
    person ends up at. Asking saves nothing."""
    client = as_person(world.planner)
    existing = world.member_allocation
    wanted = {
        "budget_line_id": str(world.line.id),
        "person_id": str(world.member.id),
        "start_date": "2026-03-01",
        "end_date": "2026-04-30",
        "fte_pct": "100",
    }
    before = (await client.get("/api/allocations")).json()["items"]
    answer = await client.post("/api/allocations/load-preview", json=wanted)
    assert answer.status_code == 200
    body = answer.json()
    assert body["person_name"] == "Lot Lid"
    assert [m["month"] for m in body["over_months"]] == ["2026-03-01", "2026-04-01"]
    first = body["over_months"][0]
    assert Decimal(first["current_pct"]) == Decimal(existing.fte_pct)
    assert Decimal(first["new_pct"]) == Decimal(existing.fte_pct) + 100
    assert (await client.get("/api/allocations")).json()["items"] == before

    # Within 100 percent there is nothing to say.
    room = 100 - Decimal(existing.fte_pct)
    quiet = await client.post(
        "/api/allocations/load-preview", json={**wanted, "fte_pct": str(room)}
    )
    assert quiet.json()["over_months"] == []

    # Changing an inzet: its own share makes room for the new percentage.
    changed = await client.post(
        "/api/allocations/load-preview",
        json={"allocation_id": str(existing.id), "fte_pct": "100"},
    )
    assert changed.json()["over_months"] == []

    # Who may not plan this person here learns nothing about their load.
    refused = await as_person(world.outsider).post(
        "/api/allocations/load-preview", json=wanted
    )
    assert refused.status_code in (403, 404)
