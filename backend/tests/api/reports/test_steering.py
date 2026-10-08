"""The steering overview: each block follows what the reader may see."""

from .conftest import (
    ALFA_BUDGET_2026,
    ALFA_COVERAGE_2026,
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
    assert turnover["expected_cents"] == ALFA_REALISED_2026 + ALFA_FORECAST_2026
    # The same year in the words of the assignment pages, over what is
    # agreed: Opdracht Beta is not, so its budget is not in it.
    figures = turnover["figures"]
    assert figures["budgeted_cents"] == ALFA_BUDGET_2026
    assert figures["realised_cents"] == ALFA_REALISED_2026
    assert figures["planned_cents"] == ALFA_FORECAST_2026
    assert figures["costs_cents"] == ALFA_COVERAGE_2026
    assert figures["expected_total_cents"] == (
        ALFA_REALISED_2026 + ALFA_FORECAST_2026 + ALFA_COVERAGE_2026
    )
    assert figures["variance_cents"] == ALFA_BUDGET_2026 - (
        ALFA_REALISED_2026 + ALFA_FORECAST_2026 + ALFA_COVERAGE_2026
    )
    assert figures["overrun"] is True
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
        figures = [row["figures"] for row in overview["rows"] if row.get("figures")]
        assert turnover["realised_cents"] == sum(f["realised_cents"] for f in figures)
        assert turnover["forecast_cents"] + turnover["pipeline_cents"] == sum(
            f["planned_cents"] for f in figures
        )
    assert turnover["forecast_cents"] == ALFA_FORECAST_2027


def _cells(person) -> dict[str, dict]:
    return {cell["month"]: cell for cell in person["cells"]}


async def test_occupancy_per_person_and_month(as_person, world):
    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    by_name = {person["person_name"]: person for person in occupancy["persons"]}
    assert set(by_name) == set(world.staff_names)

    # Available all year through the billing scale, on inzet from July; the
    # closed month counts with the established 80 percent.
    member = _cells(by_name[world.member.name])
    assert [member[f"2026-{m:02d}"]["pct"] for m in range(1, 7)] == ["0"] * 6
    assert member["2026-03"]["available"] is True
    assert member["2026-03"]["parts"] == []
    assert member["2026-07"]["pct"] == "80"
    assert member["2026-07"]["established"] is True
    assert member["2026-08"]["pct"] == "100"
    assert member["2026-08"]["established"] is False
    part = member["2026-08"]["parts"][0]
    assert part["assignment_name"] == "Opdracht Alfa"
    assert part["assignment_id"] == str(world.alfa.id)
    assert (part["pct"], part["tentative"], part["established"]) == (
        "100",
        False,
        False,
    )

    # Inzet on an assignment that is not agreed yet is tentative.
    other = _cells(by_name[world.other_person.name])
    assert other["2026-05"]["pct"] == "100"
    assert other["2026-05"]["tentative_pct"] == "100"
    assert other["2026-05"]["parts"][0]["tentative"] is True
    assert member["2026-08"]["tentative_pct"] == "0"

    july = next(m for m in occupancy["months"] if m["month"] == "2026-07")
    assert july["available_fte"] == "3"
    assert july["allocated_fte"] == "2.3"
    assert july["tentative_fte"] == "1"
    assert july["free_fte"] == "0.7"
    assert (july["under"], july["full"], july["over"]) == (2, 1, 0)


async def test_the_figures_on_top_cover_the_rows_of_the_block(as_person, world):
    from datetime import date

    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    summary = occupancy["summary"]
    assert summary["person_count"] == 3
    # (0*6 + 80 + 100*5) + 50*6 + 100*12 over 36 available person-months.
    assert summary["average_pct"] == "57.8"
    assert summary["over_count"] == 0
    assert summary["over_months"] == []
    today = date.today()
    assert summary["current_month"] == f"{today.year:04d}-{today.month:02d}"
    assert len(summary["window"]) == 4
    assert summary["window"][0]["month"] == summary["current_month"]

    own = (await _steering(as_person(world.leader))).json()["occupancy"]["summary"]
    assert own["person_count"] == 2
    # (580 + 300) over 24 person-months: the third person is not in it.
    assert own["average_pct"] == "36.7"


async def test_the_window_says_what_is_free_and_who_is_idle(db_session, world):
    from grip.calc import Month
    from grip.services.reports import steering

    year_rows = await steering.occupancy(db_session, steering.months_of(2026))
    window = steering.next_months(Month(2026, 10), 4)
    window_rows = await steering.occupancy(db_session, window)
    summary = steering.occupancy_summary(year_rows, window_rows, window)
    october, november, december, january = summary.window
    assert str(october.month) == "2026-10"
    assert (str(october.allocated_fte), str(october.tentative_fte)) == ("2.50", "1.00")
    assert str(october.free_fte) == "0.50"
    # In January the tentative inzet has ended: one more person is free.
    assert str(january.month) == "2027-01"
    assert str(january.free_fte) == "1.50"
    assert summary.idle_count == 0

    later = steering.next_months(Month(2026, 12), 4)
    idle = steering.occupancy_summary(
        year_rows, await steering.occupancy(db_session, later), later
    )
    assert idle.idle_count == 1


async def test_above_100_percent_is_counted_and_named(as_person, world, db_session):
    from datetime import date
    from decimal import Decimal

    from grip.models.assignment import BudgetLine
    from grip.services import assignments

    beta_line = (
        await db_session.execute(
            BudgetLine.__table__.select().where(
                BudgetLine.assignment_id == world.beta.id
            )
        )
    ).first()
    await assignments.add_allocation(
        db_session,
        beta_line.id,
        world.member.id,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        fte_pct=Decimal("30"),
        actor=world.beheerder,
    )
    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    assert occupancy["summary"]["over_count"] == 1
    assert occupancy["summary"]["over_months"] == ["2026-09"]
    member = next(
        p for p in occupancy["persons"] if p["person_name"] == world.member.name
    )
    assert member["over_months"] == ["2026-09"]
    september = _cells(member)["2026-09"]
    assert september["pct"] == "130"
    assert september["tentative_pct"] == "30"
    assert [
        (p["assignment_name"], p["pct"], p["tentative"]) for p in september["parts"]
    ] == [
        ("Opdracht Alfa", "100", False),
        ("Opdracht Beta", "30", True),
    ]


async def test_a_part_is_named_only_for_who_may_see_the_assignment(as_person, world):
    # The line manager sees how much the reports are allocated, but is on
    # neither assignment: the parts come without the name.
    leader = (await _steering(as_person(world.leader))).json()["occupancy"]
    member = next(p for p in leader["persons"] if p["person_name"] == world.member.name)
    part = _cells(member)["2026-08"]["parts"][0]
    assert part["pct"] == "100"
    assert "assignment_name" not in part
    assert "assignment_id" not in part

    own = (await _steering(as_person(world.member))).json()["occupancy"]
    part = _cells(own["persons"][0])["2026-08"]["parts"][0]
    assert part["assignment_name"] == "Opdracht Alfa"


async def test_people_who_are_not_deployable_are_listed_apart(as_person, world):
    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    rows = {person["person_name"] for person in occupancy["persons"]}
    left_out = {person["person_name"] for person in occupancy["not_deployable"]}
    assert rows == set(world.staff_names)
    assert world.beheerder.name in left_out
    assert world.planner.name in left_out
    assert rows.isdisjoint(left_out)
    for person in occupancy["not_deployable"]:
        assert set(person) == {"person_id", "person_name"}

    # A line manager is told about nobody outside the own reports.
    leader = (await _steering(as_person(world.leader))).json()["occupancy"]
    assert leader["not_deployable"] == [
        {"person_id": str(world.leader.id), "person_name": world.leader.name}
    ]


async def _set_status(db_session, assignment, status: str) -> None:
    assignment.status = status
    await db_session.flush()


async def test_a_verbal_agreement_counts_in_the_forecast_and_is_shown_apart(
    as_person, world, db_session
):
    await _set_status(db_session, world.beta, "verbally_agreed")
    turnover = (await _steering(as_person(world.beheerder))).json()["turnover"]
    assert turnover["forecast_cents"] == ALFA_FORECAST_2026 + BETA_PIPELINE_2026
    assert turnover["verbal_cents"] == BETA_PIPELINE_2026
    assert turnover["pipeline_cents"] == 0
    march = next(m for m in turnover["months"] if m["month"] == "2026-03")
    assert march["forecast_cents"] == march["verbal_cents"] == 1800000

    # Verbally agreed is still tentative inzet.
    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    other = next(
        p for p in occupancy["persons"] if p["person_name"] == world.other_person.name
    )
    part = _cells(other)["2026-03"]["parts"][0]
    assert (part["tentative"], part["verbally_agreed"]) == (True, True)


async def test_a_formal_agreement_is_committed(as_person, world, db_session):
    await _set_status(db_session, world.beta, "accepted")
    turnover = (await _steering(as_person(world.beheerder))).json()["turnover"]
    assert turnover["forecast_cents"] == ALFA_FORECAST_2026 + BETA_PIPELINE_2026
    assert turnover["verbal_cents"] == 0
    assert turnover["pipeline_cents"] == 0

    occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
    other = next(
        p for p in occupancy["persons"] if p["person_name"] == world.other_person.name
    )
    assert _cells(other)["2026-03"]["tentative_pct"] == "0"


async def test_what_is_not_agreed_yet_is_pipeline(as_person, world, db_session):
    for status in ("draft", "requested", "quoted"):
        await _set_status(db_session, world.beta, status)
        turnover = (await _steering(as_person(world.beheerder))).json()["turnover"]
        assert turnover["forecast_cents"] == ALFA_FORECAST_2026
        assert turnover["verbal_cents"] == 0
        assert turnover["pipeline_cents"] == BETA_PIPELINE_2026


async def test_a_rejected_or_cancelled_assignment_counts_for_nothing(
    as_person, world, db_session
):
    for status in ("rejected", "cancelled"):
        await _set_status(db_session, world.beta, status)
        turnover = (await _steering(as_person(world.beheerder))).json()["turnover"]
        assert turnover["forecast_cents"] == ALFA_FORECAST_2026
        assert turnover["verbal_cents"] == 0
        assert turnover["pipeline_cents"] == 0

        # Its inzet will not happen: the person is free, and still a row.
        occupancy = (await _steering(as_person(world.planner))).json()["occupancy"]
        other = next(
            p
            for p in occupancy["persons"]
            if p["person_name"] == world.other_person.name
        )
        assert _cells(other)["2026-03"]["pct"] == "0"
        assert _cells(other)["2026-03"]["available"] is True


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
    assert occupancy["summary"]["person_count"] == 2

    billability = body["billability"]
    assert billability["scope"] == "own"
    assert _names(billability) == reports
    listed = sum(
        (person["realised_cents"] or 0) + (person["forecast_cents"] or 0)
        for person in billability["persons"]
    )
    assert billability["realised_cents"] + billability["forecast_cents"] == listed
    # One of the two has a target; with 80 percent in July and a start in
    # July, the year ends far below 90 percent of twelve months.
    assert billability["with_target_count"] == 1
    assert billability["below_target_count"] == 1
    assert billability["realisation_cents"] == listed
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
