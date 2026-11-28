"""The billability KPI through the API (data class F)."""

from decimal import Decimal

from grip.calc import Month
from grip.services import month_close
from tests.api.reference.conftest import by_id
from tests.lifecycle import accept

KPI_FIELDS = {
    "year",
    "target_pct",
    "target_cents",
    "realised_cents",
    "forecast_cents",
    "realisation_cents",
    "unavailable_reason",
}


async def _kpi(client, year=2026):
    resp = await client.get("/api/kpi", params={"year": year})
    assert resp.status_code == 200
    return resp.json()


async def test_beheerder_sets_target_and_sees_worked_example(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.put(
        f"/api/kpi/{world.report.id}/2026", json={"target_pct": "90"}
    )
    assert resp.status_code == 200
    kpi = resp.json()
    # 90 percent of 12 months at 18,000 and 12 months at 100 percent.
    assert kpi["target_cents"] == 19440000
    assert Decimal(kpi["target_pct"]) == Decimal(90)
    assert kpi["forecast_cents"] == 21600000
    assert kpi["realised_cents"] == 0
    assert kpi["realisation_cents"] == 21600000

    body = await _kpi(client)
    assert body["may_manage"] is True
    assert len(body["items"]) == 8
    assert by_id(body["items"], world.report)["target_cents"] == 19440000
    assert by_id(body["items"], world.outsider)["target_cents"] is None


async def test_realised_and_forecast_are_shown_apart(
    client, world, as_person, db_session
):
    await accept(db_session, world.beta.id)
    # A month closes once the work has started. The lifecycle is not under
    # test here, so the status is set directly.
    world.beta.status = "in_progress"
    await db_session.flush()
    await month_close.close_month(
        db_session, world.beta.id, Month(2026, 1), actor=world.beheerder
    )
    as_person(world.beheerder)
    kpi = by_id((await _kpi(client))["items"], world.report)
    assert kpi["realised_cents"] == 1800000
    assert kpi["forecast_cents"] == 19800000
    assert kpi["realisation_cents"] == 21600000


async def test_line_manager_sees_direct_reports_and_self(client, world, as_person):
    as_person(world.lead)
    body = await _kpi(client)
    assert body["may_manage"] is False
    assert {i["person_id"] for i in body["items"]} == {
        str(world.lead.id),
        str(world.report.id),
    }
    assert KPI_FIELDS <= set(by_id(body["items"], world.report))


async def test_person_sees_own_kpi(client, world, as_person):
    as_person(world.report)
    body = await _kpi(client)
    assert [i["person_id"] for i in body["items"]] == [str(world.report.id)]
    own = await client.get(f"/api/kpi/{world.report.id}", params={"year": 2026})
    assert own.status_code == 200 and own.json()["forecast_cents"] == 21600000


async def test_planner_lezer_and_owner_see_no_kpi_of_others(client, world, as_person):
    for person in (world.planner, world.lezer, world.owner):
        as_person(person)
        body = await _kpi(client)
        assert [i["person_id"] for i in body["items"]] == [str(person.id)]
        # Not the KPI of someone else, not even of someone on the own assignment.
        for other in (world.report, world.hired):
            resp = await client.get(f"/api/kpi/{other.id}", params={"year": 2026})
            assert resp.status_code == 404


async def test_only_beheerder_sets_a_target(client, world, as_person):
    for person in (world.lead, world.planner, world.report):
        as_person(person)
        resp = await client.put(
            f"/api/kpi/{world.report.id}/2026", json={"target_pct": "80"}
        )
        assert resp.status_code == 403


async def test_target_out_of_range_is_refused(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.put(
        f"/api/kpi/{world.report.id}/2026", json={"target_pct": "120"}
    )
    assert resp.status_code == 422


async def test_year_without_rate_card_says_why(client, world, as_person, db_session):
    from datetime import date

    from grip.services import assignments

    # Staffing that runs into a year without rates cannot be priced.
    line = await assignments.add_budget_line(
        db_session,
        world.beta.id,
        description="Developer 2028",
        kind="personnel",
        role="Developer",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2028, 1, 1),
        end_date=date(2028, 12, 31),
        actor=world.beheerder,
    )
    await assignments.add_allocation(
        db_session,
        line.id,
        world.report.id,
        start_date=date(2028, 1, 1),
        end_date=date(2028, 3, 31),
        fte_pct=Decimal("100"),
        actor=world.beheerder,
    )
    as_person(world.beheerder)
    kpi = by_id((await _kpi(client, 2028))["items"], world.report)
    assert kpi["unavailable_reason"]
    assert kpi["realisation_cents"] is None
    assert kpi["gap_cents"] is None


async def test_gap_orders_those_below_target_first_with_a_total(
    client, world, as_person
):
    as_person(world.beheerder)
    for person, pct in ((world.report, "90"), (world.outsider, "50")):
        resp = await client.put(f"/api/kpi/{person.id}/2026", json={"target_pct": pct})
        assert resp.status_code == 200
    body = await _kpi(client)
    items = body["items"]
    below = by_id(items, world.outsider)
    above = by_id(items, world.report)
    assert above["gap_cents"] == 21600000 - 19440000
    assert below["gap_cents"] == below["realisation_cents"] - below["target_cents"]
    assert below["gap_cents"] < 0
    assert items.index(below) < items.index(above)
    # Those without a target come after everyone with one.
    no_target = [i for i in items if i["gap_cents"] is None]
    assert no_target and items[-len(no_target) :] == no_target
    assert body["scope"] == "all"
    assert body["totals"]["target_cents"] == sum(i["target_cents"] or 0 for i in items)
    assert body["totals"]["realisation_cents"] == sum(
        i["realisation_cents"] or 0 for i in items
    )
    assert (
        body["totals"]["gap_cents"]
        == body["totals"]["realisation_cents"] - body["totals"]["target_cents"]
    )


async def test_gap_and_totals_cover_only_what_the_reader_may_see(
    client, world, as_person
):
    as_person(world.beheerder)
    await client.put(f"/api/kpi/{world.report.id}/2026", json={"target_pct": "90"})
    for person in (world.lead, world.report):
        as_person(person)
        body = await _kpi(client)
        assert body["scope"] == "own"
        assert str(world.outsider.id) not in [i["person_id"] for i in body["items"]]
        assert body["totals"]["target_cents"] == sum(
            i["target_cents"] or 0 for i in body["items"]
        )
        assert body["totals"]["gap_cents"] == sum(
            i["realisation_cents"] or 0 for i in body["items"]
        ) - sum(i["target_cents"] or 0 for i in body["items"])
    as_person(world.report)
    one = by_id((await _kpi(client))["items"], world.report)
    assert one["gap_cents"] == 21600000 - 19440000
    # Not the gap of someone else, which would give away the target.
    resp = await client.get(f"/api/kpi/{world.outsider.id}", params={"year": 2026})
    assert resp.status_code == 404
