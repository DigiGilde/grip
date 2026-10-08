"""The financial state of an assignment: figures, tie-out, signals, export."""

from datetime import date
from decimal import Decimal

from grip.calc import Month
from grip.services import assignment_finance as finance
from grip.services import costs, month_close

from .conftest import by_id

PM_BUDGETED = 17280000
HOSTING = 1500000
MEMBER_MONTH = 900000  # 50 percent of category D
COLLEAGUE_MONTH = 450000  # 30 percent of category C


async def _agree(world, db_session):
    """A month can only be closed once the client has agreed."""
    from grip.services import assignments

    for target in ("quoted", "accepted"):
        await assignments.transition(
            db_session,
            world.assignment.id,
            target,
            actor=world.owner,
            enforce_readiness=False,
        )


async def _close_january(world, db_session):
    await _agree(world, db_session)
    # The member worked 40 percent instead of the planned 50.
    await month_close.close_month(
        db_session,
        world.assignment.id,
        Month.of(date(2026, 1, 1)),
        actor=world.owner,
        established={world.member_allocation.id: Decimal("40")},
    )


async def _hosting_costs(world, db_session):
    item = await costs.create_cost_item(
        db_session,
        description="Hostingcontract",
        budgeted_cents=1500000,
        actor=world.owner,
    )
    await costs.add_invoice_line(
        db_session,
        item.id,
        reference="HOST-26-01",
        description="Januari",
        kind="actual",
        amount_cents=400000,
        period=date(2026, 1, 1),
        actor=world.owner,
    )
    await costs.add_invoice_line(
        db_session,
        item.id,
        reference="HOST-26-02",
        description="Rest van het jaar",
        kind="estimate",
        amount_cents=600000,
        period=date(2026, 6, 1),
        actor=world.owner,
    )
    await costs.set_coverage(
        db_session, item.id, world.fixed_line.id, Decimal("30"), actor=world.owner
    )


async def test_figures_separate_realised_planned_and_costs(
    world, as_person, db_session
):
    await _close_january(world, db_session)
    await _hosting_costs(world, db_session)
    url = f"/api/assignments/{world.assignment.id}/financial?year=2026"
    body = (await as_person(world.owner).get(url)).json()

    assert body["reference_month"] == "2026-01-01"
    pm = by_id(body["lines"], "budget_line_id", world.line.id)["figures"]
    realised = 720000 + COLLEAGUE_MONTH  # 40 percent of D, plus the colleague
    planned = 11 * (MEMBER_MONTH + COLLEAGUE_MONTH)
    assert pm["budgeted_cents"] == PM_BUDGETED
    assert pm["realised_cents"] == realised
    assert pm["planned_cents"] == planned
    assert pm["expected_total_cents"] == realised + planned
    assert pm["variance_cents"] == PM_BUDGETED - realised - planned
    assert pm["overrun"] is False

    hosting = by_id(body["lines"], "budget_line_id", world.fixed_line.id)["figures"]
    # 30 percent of 4,000 actual and of 6,000 estimated.
    assert hosting["costs_realised_cents"] == 120000
    assert hosting["costs_forecast_cents"] == 180000
    assert hosting["costs_cents"] == 300000
    assert hosting["expected_total_cents"] == 300000
    assert Decimal(hosting["realised_pct"]) == Decimal("8.0")


async def test_detail_adds_up_to_the_line_and_lines_to_the_total(
    world, as_person, db_session
):
    await _close_january(world, db_session)
    await _hosting_costs(world, db_session)
    url = f"/api/assignments/{world.assignment.id}/financial?year=all"
    body = (await as_person(world.owner).get(url)).json()

    keys = (
        "budgeted_cents",
        "realised_cents",
        "planned_cents",
        "costs_realised_cents",
        "costs_forecast_cents",
        "expected_total_cents",
        "variance_cents",
    )
    for key in keys:
        assert body["totals"][key] == sum(
            line["figures"][key] for line in body["lines"]
        ), key
    for line in body["lines"]:
        figures = line["figures"]
        assert figures["realised_cents"] == sum(
            p["realised_cents"] for p in line["persons"]
        )
        assert figures["planned_cents"] == sum(
            p["planned_cents"] for p in line["persons"]
        )
        assert figures["costs_cents"] == sum(c["total_cents"] for c in line["costs"])
        for person in line["persons"]:
            assert (
                person["total_cents"]
                == person["realised_cents"] + person["planned_cents"]
            )


async def test_key_figures_and_billing(world, as_person, db_session):
    await _close_january(world, db_session)
    url = f"/api/assignments/{world.assignment.id}/financial?year=2026"
    key = (await as_person(world.owner).get(url)).json()["key_figures"]
    assert key["agreed_cents"] is None
    assert key["budgeted_cents"] == PM_BUDGETED + HOSTING
    assert key["agreed_minus_budgeted_cents"] is None
    assert (
        key["budgeted_minus_expected_cents"]
        == key["budgeted_cents"] - key["expected_total_cents"]
    )
    assert key["realised_cents"] == 720000 + COLLEAGUE_MONTH
    # Nothing was delivered to the financial administration yet, and no
    # invoice was recorded: the closed month is still to deliver, and
    # nothing counts as invoiced.
    assert key["delivered_cents"] == 0
    assert key["to_deliver_cents"] == key["realised_cents"]
    assert key["invoiced_cents"] == 0
    assert key["to_invoice_cents"] == 0
    assert "billed_cents" not in key


async def test_months_show_plan_actual_and_cumulative(world, as_person, db_session):
    await _close_january(world, db_session)
    url = f"/api/assignments/{world.assignment.id}/financial?year=2026"
    body = (await as_person(world.owner).get(url)).json()
    months = body["months"]
    assert [m["month"] for m in months][:2] == ["2026-01-01", "2026-02-01"]
    assert len(months) == 12
    january, february = months[0], months[1]
    assert january["closed"] is True
    assert january["budgeted_cents"] == PM_BUDGETED // 12
    assert january["planned_cents"] == MEMBER_MONTH + COLLEAGUE_MONTH
    assert january["realised_cents"] == 720000 + COLLEAGUE_MONTH
    assert february["closed"] is False
    assert february["realised_cents"] is None
    assert february["cumulative_realised_cents"] == january["realised_cents"]
    assert february["cumulative_planned_open_cents"] == february["planned_cents"]
    assert february["cumulative_expected_cents"] == (
        january["realised_cents"] + february["planned_cents"]
    )
    assert months[-1]["cumulative_budgeted_cents"] == PM_BUDGETED
    # The fixed line has no month; the tab says how much that leaves out.
    assert body["budgeted_outside_months_cents"] == HOSTING


async def test_signals(world, db_session):
    data = await finance.assignment_finance(
        db_session, world.assignment.id, year=2026, today=date(2026, 4, 15)
    )
    kinds = {s.kind: s for s in data.signals}
    # Hosting has no costs on it at all: all of its budget is free.
    assert kinds["free_room"].description == "Hosting"
    assert kinds["rate_mismatch"].count == 1
    assert kinds["months_not_closed"].months == (
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    )
    assert "overrun" not in kinds


async def test_overrun_is_a_signal(world, db_session):
    from grip.services import assignments

    await assignments.update_budget_line(
        db_session, world.line.id, actor=world.owner, fte=Decimal("0.5")
    )
    data = await finance.assignment_finance(db_session, world.assignment.id, year=2026)
    overrun = next(s for s in data.signals if s.kind == "overrun")
    assert overrun.description == "Productmanager"
    assert overrun.amount_cents == 12 * (MEMBER_MONTH + COLLEAGUE_MONTH) - 10800000
    assert overrun.amount_cents > 0


async def test_only_class_b_gets_the_tab(world, as_person):
    url = f"/api/assignments/{world.assignment.id}/financial"
    assert (await as_person(world.owner).get(url)).status_code == 200
    assert (await as_person(world.lezer).get(url)).status_code == 200
    for person in (world.planner, world.member):
        assert (await as_person(person).get(url)).status_code == 403
        assert (await as_person(person).get(f"{url}/csv")).status_code == 403
    assert (await as_person(world.outsider).get(url)).status_code == 404


async def test_lezer_gets_totals_without_amounts_per_person(world, as_person):
    url = f"/api/assignments/{world.assignment.id}/financial?year=2026"
    body = (await as_person(world.lezer).get(url)).json()
    pm = by_id(body["lines"], "budget_line_id", world.line.id)
    assert pm["figures"]["planned_cents"] == 12 * (MEMBER_MONTH + COLLEAGUE_MONTH)
    assert pm["persons"] == []
    assert pm["persons_hidden"] == 2


async def test_csv_has_stable_columns_and_the_same_figures(world, as_person):
    base = f"/api/assignments/{world.assignment.id}/financial"
    response = await as_person(world.owner).get(f"{base}/csv?year=2026")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "financieel-regels-2026.csv" in response.headers["content-disposition"]
    rows = response.text.strip().split("\r\n")
    assert rows[0] == ",".join(finance.LINE_CSV_COLUMNS)
    assert len(rows) == 4  # header, two lines, total
    total = dict(zip(finance.LINE_CSV_COLUMNS, rows[-1].split(","), strict=True))
    assert total["description"] == "total"
    assert total["budgeted"] == "187800.00"
    assert total["period"] == "2026"
    assert total["currency"] == "EUR"
    assert "Lot Lid" not in response.text

    months = await as_person(world.owner).get(f"{base}/csv?year=2026&section=months")
    lines = months.text.strip().split("\r\n")
    assert lines[0] == ",".join(finance.MONTH_CSV_COLUMNS)
    assert len(lines) == 13
    assert lines[1].split(",")[1:3] == ["2026-01", "false"]


async def test_preview_prices_a_line_before_it_is_saved(world, as_person):
    url = f"/api/assignments/{world.assignment.id}/budget-lines/preview"
    client = as_person(world.owner)
    body = (
        await client.post(
            url,
            json={
                "kind": "personnel",
                "fte": "0.8",
                "rate_category": "D",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
    ).json()
    assert body == {
        "budgeted_cents": PM_BUDGETED,
        "budgeted_by_year": {"2026": PM_BUDGETED},
        "reason": None,
    }
    # Not complete yet: no amount and no error.
    incomplete = (await client.post(url, json={"kind": "personnel", "fte": "1"})).json()
    assert incomplete["budgeted_cents"] is None
    assert incomplete["reason"] == (
        "Nog niet te berekenen: de schaal en de periode ontbreken."
    )
    # A following line is priced over the period of the assignment.
    following = (
        await client.post(
            url,
            json={"fte": "0.8", "rate_category": "D", "period_source": "assignment"},
        )
    ).json()
    assert following["budgeted_cents"] is not None or "looptijd" in following["reason"]
    # A year without a rate card says so.
    missing = (
        await client.post(
            url,
            json={
                "fte": "1",
                "rate_category": "D",
                "start_date": "2029-01-01",
                "end_date": "2029-03-31",
            },
        )
    ).json()
    assert missing["budgeted_cents"] is None
    assert "tarievenkaart" in missing["reason"]
    assert (await as_person(world.planner).post(url, json={})).status_code == 403
