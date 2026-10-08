"""The budget and the stand van zaken: amounts only for who may see class B."""

from decimal import Decimal

from .conftest import by_id

# 0.8 FTE in category D for twelve months at 18,000: the worked example.
PM_BUDGETED = 17280000
HOSTING = 1500000
# Member: 50 percent of D (18,000) for twelve months. Colleague: 30 percent
# of C (15,000) for twelve months.
MEMBER_AMOUNT = 10800000
COLLEAGUE_AMOUNT = 5400000


async def test_owner_sees_the_budget_with_computed_amounts(world, as_person):
    response = await as_person(world.owner).get(
        f"/api/assignments/{world.assignment.id}/budget"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["can_edit"] is True
    pm = by_id(body["lines"], "id", world.line.id)
    assert pm["budgeted_cents"] == PM_BUDGETED
    assert pm["budgeted_by_year"] == {"2026": PM_BUDGETED}
    assert pm["rate_category"] == "D"
    assert body["subtotals_by_year"] == {"2026": PM_BUDGETED + HOSTING}
    assert body["total_budgeted_cents"] == PM_BUDGETED + HOSTING
    assert body["quoted_amount_cents"] == 40000000


async def test_planner_gets_the_demand_but_no_money_and_no_category(world, as_person):
    body = (
        await as_person(world.planner).get(
            f"/api/assignments/{world.assignment.id}/budget"
        )
    ).json()
    pm = by_id(body["lines"], "id", world.line.id)
    assert pm["role"] == "Productmanager"
    assert Decimal(pm["fte"]) == Decimal("0.800")
    for hidden in (
        "rate_category",
        "budgeted_cents",
        "amount_cents",
        "budgeted_by_year",
    ):
        assert hidden not in pm
    for hidden in ("total_budgeted_cents", "subtotals_by_year", "quoted_amount_cents"):
        assert hidden not in body
    assert body["can_edit"] is False


async def test_member_gets_line_names_only(world, as_person):
    body = (
        await as_person(world.member).get(
            f"/api/assignments/{world.assignment.id}/budget"
        )
    ).json()
    pm = by_id(body["lines"], "id", world.line.id)
    assert pm["description"] == "Productmanager"
    for hidden in ("rate_category", "budgeted_cents", "fte", "role", "start_date"):
        assert hidden not in pm


async def test_lezer_sees_money_but_not_the_staffing_demand(world, as_person):
    body = (
        await as_person(world.lezer).get(
            f"/api/assignments/{world.assignment.id}/budget"
        )
    ).json()
    pm = by_id(body["lines"], "id", world.line.id)
    assert pm["budgeted_cents"] == PM_BUDGETED
    assert "fte" not in pm


async def test_budget_line_lifecycle(world, as_person):
    client = as_person(world.owner)
    base = f"/api/assignments/{world.assignment.id}"
    added = await client.post(
        f"{base}/budget-lines",
        json={
            "description": "Developer",
            "kind": "personnel",
            "role": "Developer",
            "fte": "1",
            "rate_category": "C",
            "start_date": "2026-07-01",
            "end_date": "2026-12-31",
        },
    )
    assert added.status_code == 201
    developer = next(
        line for line in added.json()["lines"] if line["description"] == "Developer"
    )
    assert developer["budgeted_cents"] == 6 * 1500000

    changed = await client.patch(
        f"/api/budget-lines/{developer['id']}", json={"fte": "0.5"}
    )
    assert changed.status_code == 200
    assert by_id(changed.json()["lines"], "id", developer["id"])["budgeted_cents"] == (
        3 * 1500000
    )

    deleted = await client.delete(f"/api/budget-lines/{developer['id']}")
    assert deleted.status_code == 200
    assert len(deleted.json()["lines"]) == 2

    # A line with inzet on it cannot go.
    refused = await client.delete(f"/api/budget-lines/{world.line.id}")
    assert refused.status_code == 422


async def test_planner_and_member_cannot_edit_the_budget(world, as_person):
    payload = {"description": "X", "kind": "fixed", "amount_cents": 1, "year": 2026}
    for person in (world.planner, world.member, world.lezer):
        client = as_person(person)
        response = await client.post(
            f"/api/assignments/{world.assignment.id}/budget-lines", json=payload
        )
        assert response.status_code == 403
        response = await client.patch(
            f"/api/budget-lines/{world.fixed_line.id}", json={"amount_cents": 2}
        )
        assert response.status_code == 403


async def test_closed_year_override_is_for_the_beheerder(world, as_person):
    response = await as_person(world.owner).post(
        f"/api/assignments/{world.assignment.id}/budget-lines",
        json={
            "description": "X",
            "kind": "fixed",
            "amount_cents": 1,
            "year": 2026,
            "allow_closed_year": True,
        },
    )
    assert response.status_code == 403


async def test_overview_list(world, as_person):
    body = (await as_person(world.beheerder).get("/api/overview?year=2026")).json()
    assert body["year"] == 2026
    alfa = by_id(body["rows"], "assignment_id", world.assignment.id)
    used = MEMBER_AMOUNT + COLLEAGUE_AMOUNT
    assert alfa["totals"] == {
        "budgeted_cents": PM_BUDGETED + HOSTING,
        "realised_cents": 0,
        "forecast_cents": used,
        "coverage_cents": 0,
        "used_cents": used,
        "available_cents": PM_BUDGETED + HOSTING - used,
        "overrun": False,
    }
    assert body["totals"]["budgeted_cents"] == PM_BUDGETED + HOSTING

    # Another year: nothing budgeted and nothing used.
    other_year = (
        await as_person(world.beheerder).get("/api/overview?year=2027")
    ).json()
    alfa = by_id(other_year["rows"], "assignment_id", world.assignment.id)
    assert alfa["pricing_error"] is not None or alfa["totals"]["budgeted_cents"] == 0

    whole = (await as_person(world.beheerder).get("/api/overview?year=all")).json()
    assert whole["year"] is None


async def test_overview_list_without_class_b_has_no_amounts(world, as_person):
    for person in (world.planner, world.member):
        body = (await as_person(person).get("/api/overview?year=2026")).json()
        assert "totals" not in body
        assert body["rows"], person.name
        for row in body["rows"]:
            assert "pricing_error" not in row
            assert "totals" not in row


async def test_overview_rejects_a_bad_year(world, as_person):
    response = await as_person(world.beheerder).get("/api/overview?year=later")
    assert response.status_code == 422


async def test_assignment_overview_per_reader(world, as_person):
    url = f"/api/assignments/{world.assignment.id}/overview?year=2026"

    owner = (await as_person(world.owner).get(url)).json()
    pm = by_id(owner["lines"], "budget_line_id", world.line.id)
    assert pm["totals"]["budgeted_cents"] == PM_BUDGETED
    assert pm["totals"]["forecast_cents"] == MEMBER_AMOUNT + COLLEAGUE_AMOUNT
    team = {m["person_name"]: m for m in pm["team"]}
    assert team["Lot Lid"]["amount_cents"] == MEMBER_AMOUNT
    assert team["Lot Lid"]["category_mismatch"] is False
    assert team["Cas Collega"]["amount_cents"] == COLLEAGUE_AMOUNT
    assert team["Cas Collega"]["category_mismatch"] is True

    # The planner sees who, how much time and the signal, but no amounts.
    planner = (await as_person(world.planner).get(url)).json()
    pm = by_id(planner["lines"], "budget_line_id", world.line.id)
    assert "totals" not in pm
    assert "rate_category" not in pm
    team = {m["person_name"]: m for m in pm["team"]}
    assert team["Cas Collega"]["category_mismatch"] is True
    assert Decimal(team["Cas Collega"]["fte_pct"]) == Decimal("30.00")
    assert "amount_cents" not in team["Cas Collega"]
    assert "totals" not in planner

    # A member sees the team by name, the own time and amount, nothing of others.
    member = (await as_person(world.member).get(url)).json()
    pm = by_id(member["lines"], "budget_line_id", world.line.id)
    assert "totals" not in pm
    team = {m["person_name"]: m for m in pm["team"]}
    assert set(team) == {"Lot Lid", "Cas Collega"}
    assert team["Lot Lid"]["amount_cents"] == MEMBER_AMOUNT
    assert Decimal(team["Lot Lid"]["fte_pct"]) == Decimal("50.00")
    for hidden in ("amount_cents", "fte_pct", "start_date", "category_mismatch"):
        assert hidden not in team["Cas Collega"]

    # The lezer sees the money and no people.
    lezer = (await as_person(world.lezer).get(url)).json()
    pm = by_id(lezer["lines"], "budget_line_id", world.line.id)
    assert pm["totals"]["budgeted_cents"] == PM_BUDGETED
    assert pm["team"] == []


async def test_costs_on_a_line_are_class_b(world, as_person, db_session):
    from grip.services import costs

    item = await costs.create_cost_item(
        db_session,
        description="Hostingcontract",
        budgeted_cents=1500000,
        actor=world.owner,
    )
    await costs.set_coverage(
        db_session, item.id, world.fixed_line.id, Decimal("30"), actor=world.owner
    )
    url = f"/api/assignments/{world.assignment.id}/overview?year=all"

    owner = (await as_person(world.owner).get(url)).json()
    hosting = by_id(owner["lines"], "budget_line_id", world.fixed_line.id)
    assert [c["description"] for c in hosting["costs"]] == ["Hostingcontract"]

    for person in (world.member, world.planner):
        body = (await as_person(person).get(url)).json()
        hosting = by_id(body["lines"], "budget_line_id", world.fixed_line.id)
        assert hosting["costs"] == [], person.name
