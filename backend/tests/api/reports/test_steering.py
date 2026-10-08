"""The steering overview: each block follows what the reader may see."""

from .conftest import (
    ALFA_FORECAST_2026,
    ALFA_FORECAST_2027,
    ALFA_REALISED_2026,
    BETA_PIPELINE_2026,
)

BLOCKS = {"turnover", "occupancy", "pipeline", "costs", "billability", "open_roles"}
MONEY_BLOCKS = {"turnover", "pipeline", "costs"}


async def _steering(client, year: int = 2026):
    response = await client.get("/api/reports/steering", params={"year": year})
    assert response.status_code == 200
    return response


def _names(block) -> set[str]:
    return {person["person_name"] for person in block["persons"]}


async def test_the_beheerder_sees_every_block(as_person, world):
    body = (await _steering(as_person(world.beheerder))).json()
    assert BLOCKS <= set(body)
    for block in BLOCKS:
        assert body[block]["scope"] == "all"

    turnover = body["turnover"]
    assert turnover["realised_cents"] == ALFA_REALISED_2026
    assert turnover["forecast_cents"] == ALFA_FORECAST_2026
    assert turnover["pipeline_cents"] == BETA_PIPELINE_2026
    july = next(m for m in turnover["months"] if m["month"] == "2026-07")
    assert july["realised_cents"] == ALFA_REALISED_2026
    assert july["forecast_cents"] == 0
    assert len(turnover["months"]) == 12

    costs = body["costs"]
    assert costs["forecast_cents"] == 1500000
    assert costs["covered_cents"] == 450000
    assert costs["uncovered_cents"] == 1050000

    accepted = next(
        s for s in body["pipeline"]["statuses"] if s["status"] == "accepted"
    )
    assert accepted["count"] == 1
    assert accepted["total_cents"] == world.quote.total_cents


async def test_turnover_agrees_with_the_stand_van_zaken(as_person, world):
    client = as_person(world.beheerder)
    for year in (2026, 2027):
        turnover = (await _steering(client, year)).json()["turnover"]
        overview = (await client.get("/api/overview", params={"year": year})).json()
        totals = overview["totals"]
        assert turnover["realised_cents"] == totals["realised_cents"]
        assert (
            turnover["forecast_cents"] + turnover["pipeline_cents"]
            == totals["forecast_cents"]
        )
    assert turnover["forecast_cents"] == ALFA_FORECAST_2027


async def test_occupancy_per_person_and_month(as_person, world):
    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    by_name = {person["person_name"]: person for person in occupancy["persons"]}
    assert set(by_name) == set(world.staff_names)
    # Available all year through the billing scale, on inzet from July; the
    # closed month counts with the established 80 percent.
    member = by_name[world.member.name]["months"]
    assert member[:6] == ["0"] * 6
    assert member[6] == "80"
    assert member[7:] == ["100"] * 5
    assert by_name[world.colleague.name]["months"][6:] == ["50"] * 6
    assert by_name[world.other_person.name]["months"] == ["100"] * 12

    july = next(m for m in occupancy["months"] if m["month"] == "2026-07")
    assert july["available_fte"] == "3"
    assert july["allocated_fte"] == "2.3"
    assert (july["under"], july["full"], july["over"]) == (2, 1, 0)


async def test_a_lezer_sees_money_totals_and_no_persons(as_person, world):
    response = await _steering(as_person(world.lezer))
    body = response.json()
    assert set(body) == {"year"} | MONEY_BLOCKS
    assert body["turnover"]["scope"] == "all"
    assert body["turnover"]["pipeline_cents"] == BETA_PIPELINE_2026
    for name in world.staff_names:
        assert name not in response.text


async def test_a_planner_sees_occupancy_without_amounts(as_person, world):
    response = await _steering(as_person(world.planner))
    body = response.json()
    assert set(body) == {"year", "occupancy", "open_roles"}
    assert body["occupancy"]["scope"] == "all"
    assert "cents" not in response.text


async def test_a_line_manager_sees_only_direct_reports(as_person, world):
    body = (await _steering(as_person(world.leader))).json()
    assert set(body) == {"year", "occupancy", "billability"}
    reports = {world.member.name, world.colleague.name}

    occupancy = body["occupancy"]
    assert occupancy["scope"] == "own"
    assert _names(occupancy) == reports
    # The totals are over the two reports only: nothing in them says that a
    # third person is available and fully allocated.
    assert {month["available_fte"] for month in occupancy["months"]} == {"2"}
    july = next(m for m in occupancy["months"] if m["month"] == "2026-07")
    assert july["allocated_fte"] == "1.3"

    billability = body["billability"]
    assert billability["scope"] == "own"
    assert _names(billability) == reports
    listed = sum(
        (person["realised_cents"] or 0) + (person["forecast_cents"] or 0)
        for person in billability["persons"]
    )
    assert billability["realised_cents"] + billability["forecast_cents"] == listed
    member = next(
        p for p in billability["persons"] if p["person_name"] == world.member.name
    )
    assert member["target_pct"] == "90"
    assert member["realised_cents"] == 1440000


async def test_totals_differ_by_what_the_reader_sees(as_person, world):
    """An aggregate is taken over the visible rows, never over more."""
    everything = (await _steering(as_person(world.beheerder))).json()
    partial = (await _steering(as_person(world.leader))).json()
    all_july = next(
        m for m in everything["occupancy"]["months"] if m["month"] == "2026-07"
    )
    own_july = next(
        m for m in partial["occupancy"]["months"] if m["month"] == "2026-07"
    )
    assert all_july["available_fte"] == "3"
    assert own_july["available_fte"] == "2"
    assert (
        everything["billability"]["forecast_cents"]
        > partial["billability"]["forecast_cents"]
    )


async def test_an_owner_adds_up_only_the_own_assignments(as_person, world):
    body = (await _steering(as_person(world.owner))).json()
    assert body["turnover"]["scope"] == "own"
    assert body["turnover"]["realised_cents"] == ALFA_REALISED_2026
    assert body["turnover"]["forecast_cents"] == ALFA_FORECAST_2026
    # Opdracht Beta is someone else's: its pipeline is not in this total.
    assert body["turnover"]["pipeline_cents"] == 0
    assert body["pipeline"]["scope"] == "own"
    assert body["costs"]["scope"] == "own"
    assert body["costs"]["covered_cents"] == 450000
    # No KPI of anyone and no occupancy of the team through the assignment.
    assert "billability" not in body
    assert "occupancy" not in body


async def test_a_person_sees_the_own_occupancy_and_kpi(as_person, world):
    body = (await _steering(as_person(world.member))).json()
    assert set(body) == {"year", "occupancy", "billability"}
    assert _names(body["occupancy"]) == {world.member.name}
    assert _names(body["billability"]) == {world.member.name}


async def test_someone_without_anything_gets_no_block(as_person, world):
    response = await _steering(as_person(world.outsider))
    assert response.json() == {"year": 2026}


async def test_open_roles_follow_staffing_access(as_person, world, db_session):
    from datetime import date
    from decimal import Decimal

    from grip.services import assignments

    await assignments.add_budget_line(
        db_session,
        world.alfa.id,
        description="Ontwerper",
        kind="personnel",
        role="Ontwerper",
        fte=Decimal("0.6"),
        rate_category="C",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        actor=world.owner,
    )
    planner = (await _steering(as_person(world.planner))).json()["open_roles"]
    assert planner["scope"] == "all"
    roles = {(r["assignment_name"], r["description"]) for r in planner["roles"]}
    assert ("Opdracht Alfa", "Ontwerper") in roles

    owner = (await _steering(as_person(world.owner))).json()["open_roles"]
    assert owner["scope"] == "own"
    assert {r["assignment_name"] for r in owner["roles"]} == {"Opdracht Alfa"}

    lezer = (await _steering(as_person(world.lezer))).json()
    assert "open_roles" not in lezer


async def test_an_unpriced_assignment_is_named_and_left_out(
    as_person, world, db_session
):
    from datetime import date
    from decimal import Decimal

    from grip.services import assignments

    # Inzet in a year without a rate card cannot be priced.
    line = await assignments.add_budget_line(
        db_session,
        world.beta.id,
        description="Uitloop",
        kind="personnel",
        role="Adviseur",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2028, 1, 1),
        end_date=date(2028, 3, 31),
        actor=world.beheerder,
    )
    await assignments.add_allocation(
        db_session,
        line.id,
        world.other_person.id,
        start_date=date(2028, 1, 1),
        end_date=date(2028, 3, 31),
        fte_pct=Decimal("100"),
        actor=world.beheerder,
    )
    turnover = (await _steering(as_person(world.beheerder))).json()["turnover"]
    assert turnover["unpriced_assignments"] == ["Opdracht Beta"]
    assert turnover["pipeline_cents"] == 0
    assert turnover["realised_cents"] == ALFA_REALISED_2026


async def test_the_year_is_validated(as_person, world):
    response = await as_person(world.beheerder).get(
        "/api/reports/steering", params={"year": 1999}
    )
    assert response.status_code == 422
