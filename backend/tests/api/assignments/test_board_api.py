"""The planner's board: who is on what, when, and which roles are open."""

from decimal import Decimal

from grip.core import clock

URL = "/api/allocations/board?start=2026-01&months=12"


def _row(body, person):
    return next(p for p in body["persons"] if p["person_id"] == str(person.id))


async def test_planner_sees_rows_totals_bars_and_open_roles(world, as_person):
    response = await as_person(world.planner).get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["months"][0] == "2026-01-01"
    assert len(body["months"]) == 12
    assert body["can_add"] is True

    member = _row(body, world.member)
    assert len(member["cells"]) == 12
    assert Decimal(member["cells"][0]["pct"]) == 50
    # The assignment is still potential: the inzet is tentative.
    assert Decimal(member["cells"][0]["tentative_pct"]) == 50
    assert member["cells"][0]["over"] is False
    (bar,) = member["bars"]
    assert bar["assignment_name"] == "Opdracht Alfa 2026"
    assert bar["line_description"] == "Productmanager"
    assert Decimal(bar["fte_pct"]) == 50
    assert bar["start_date"] == "2026-01-01"
    assert bar["tentative"] is True
    assert bar["can_edit"] is True
    assert bar["closed_months"] == []

    # The line asks 0.8 FTE and has 0.5 plus 0.3 on it: nothing is open.
    assert body["open_roles"] == []


async def test_no_amounts_and_categories_only_for_who_may_see_them(world, as_person):
    planner = (await as_person(world.planner).get(URL)).json()
    bar = _row(planner, world.colleague)["bars"][0]
    assert bar["category_mismatch"] is True
    assert "person_category" not in bar and "line_category" not in bar

    owner = (await as_person(world.owner).get(URL)).json()
    bar = _row(owner, world.colleague)["bars"][0]
    assert (bar["person_category"], bar["line_category"]) == ("C", "D")

    for body in (planner, owner):
        text = str(body)
        assert "cents" not in text and "amount" not in text


async def test_owner_sees_bars_on_own_assignment_without_the_persons_totals(
    world, as_person
):
    # The total of a person covers other assignments too, which an owner of
    # one assignment may not see.
    body = (await as_person(world.owner).get(URL)).json()
    member = _row(body, world.member)
    assert len(member["bars"]) == 1
    assert member["cells"] == []
    assert "now_pct" not in member


async def test_team_member_sees_only_the_own_row(world, as_person):
    body = (await as_person(world.member).get(URL)).json()
    assert [p["person_name"] for p in body["persons"]] == ["Lot Lid"]
    row = body["persons"][0]
    assert len(row["cells"]) == 12
    assert row["bars"][0]["can_edit"] is False
    assert body["can_add"] is False
    assert body["open_roles"] == []


async def test_lezer_and_outsider_get_an_empty_board(world, as_person):
    for person in (world.lezer, world.outsider):
        body = (await as_person(person).get(URL)).json()
        assert body["persons"] == []
        assert body["open_roles"] == []


async def test_open_role_and_overbooking(world, as_person, db_session):
    from datetime import date

    from grip.services import assignments

    # A second role nobody fills, and the member doubled on another line.
    open_line = await assignments.add_budget_line(
        db_session,
        world.assignment.id,
        description="Developer",
        kind="personnel",
        role="Developer",
        fte=Decimal("1"),
        rate_category="C",
        start_date=date(2026, 4, 1),
        end_date=date(2030, 12, 31),
        actor=world.owner,
    )
    await assignments.add_allocation(
        db_session,
        open_line.id,
        world.member.id,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 5, 31),
        fte_pct=Decimal("60"),
        actor=world.owner,
    )
    body = (await as_person(world.planner).get(URL)).json()
    member = _row(body, world.member)
    april = next(c for c in member["cells"] if c["month"] == "2026-04-01")
    assert Decimal(april["pct"]) == 110
    assert april["over"] is True
    assert member["over_months"] == ["2026-04-01", "2026-05-01"]
    assert len(member["bars"]) == 2

    (role,) = body["open_roles"]
    assert role["description"] == "Developer"
    assert Decimal(role["fte"]) == 1
    assert role["can_fill"] is True
    # Open from the first month that is still to come: the past cannot be
    # filled, and the months someone was on the role were not open.
    still_open_from = max(date(2026, 4, 1), clock.today().replace(day=1))
    assert role["start_date"] == still_open_from.isoformat()


async def test_bad_start_month(world, as_person):
    response = await as_person(world.planner).get("/api/allocations/board?start=april")
    assert response.status_code == 422


# -- the staffing of one assignment -------------------------------------------


async def test_staffing_shows_demand_fill_and_the_gap(world, as_person, db_session):
    from datetime import date

    from grip.services import assignments, staffing_board

    # The colleague leaves the role at the end of September.
    await assignments.update_allocation(
        db_session,
        world.colleague_allocation.id,
        actor=world.owner,
        end_date=date(2026, 9, 30),
    )
    data = await staffing_board.assignment_staffing(
        db_session, world.assignment.id, today=date(2026, 4, 15)
    )
    (role,) = data.roles
    assert len(data.months) == 12
    march = next(m for m in role.months if m.month == date(2026, 3, 1))
    october = next(m for m in role.months if m.month == date(2026, 10, 1))
    assert (march.asked_pct, march.filled_pct, march.open_pct) == (80, 80, 0)
    assert (october.filled_pct, october.open_pct) == (50, 30)
    (gap,) = role.gaps
    assert (gap.start, gap.end) == (date(2026, 10, 1), date(2026, 12, 1))
    assert gap.open_fte == Decimal("0.30")
    assert not role.fully_staffed
    assert (data.open_from, data.open_fte) == (date(2026, 10, 1), Decimal("0.30"))
    assert data.tentative is True

    body = (
        await as_person(world.planner).get(
            f"/api/assignments/{world.assignment.id}/staffing"
        )
    ).json()
    assert body["role_count"] == 1 and body["staffed_count"] in (0, 1)
    api_role = body["roles"][0]
    assert {bar["person_name"] for bar in api_role["bars"]} == {
        "Lot Lid",
        "Cas Collega",
    }
    assert api_role["can_fill"] is True
    assert "cents" not in str(body) and "amount" not in str(body)


async def test_staffing_for_a_team_member_is_names_only(world, as_person):
    url = f"/api/assignments/{world.assignment.id}/staffing"
    body = (await as_person(world.member).get(url)).json()
    role = body["roles"][0]
    assert role["names"] == ["Cas Collega", "Lot Lid"]
    assert role["bars"] == []
    for hidden in ("months", "gaps", "fte"):
        assert not role.get(hidden)
    assert "open_fte" not in body
    assert (await as_person(world.lezer).get(url)).status_code == 403
    assert (await as_person(world.outsider).get(url)).status_code == 404


async def test_a_team_member_does_not_read_the_category_of_the_line(world, as_person):
    """The colleague bills in C on a line budgeted in D. Their own category
    is theirs to know; the price level of the line is money of the assignment
    and stays out of everything a team member reads about their own inzet."""
    client = as_person(world.colleague)
    answers = [
        await client.get(URL),
        await client.get("/api/allocations?year=2026"),
        await client.get(f"/api/assignments/{world.assignment.id}/staffing"),
        await client.get(f"/api/people/{world.colleague.id}"),
    ]
    for answer in answers:
        assert "line_category" not in answer.text, answer.request.url
    board = _row(answers[0].json(), world.colleague)
    assert board["bars"][0]["category_mismatch"] is True

    # Who reads the money of the assignment still reads both.
    owner = (await as_person(world.owner).get(URL)).json()
    bar = _row(owner, world.colleague)["bars"][0]
    assert (bar["person_category"], bar["line_category"]) == ("C", "D")
