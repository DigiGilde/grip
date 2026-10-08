"""Monthly close and billing data routes."""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from tests.lifecycle import accept

# 80 percent in category D: 0.8 x 18,000.
PLANNED_CENTS = 1_440_000


def _base(world) -> str:
    return f"/api/assignments/{world.assignment.id}"


@pytest.fixture(autouse=True)
async def _accepted(world, db_session):
    """Months close and billing data exists only from an agreement on."""
    await accept(db_session, world.assignment.id)


async def test_timeline_lists_every_month(act_as, world):
    client = act_as(world.manager)
    body = (await client.get(f"{_base(world)}/months")).json()
    months = body["months"]
    assert [m["month"] for m in months] == [f"2026-{n:02d}" for n in range(1, 13)]
    assert all(m["closed"] is False for m in months)
    assert months[0]["closable"] is True


async def test_month_shows_the_proposal(act_as, world):
    client = act_as(world.manager)
    body = (await client.get(f"{_base(world)}/months/2026-03")).json()
    assert body["closed"] is False
    assert body["may_close"] is True
    assert body["may_reopen"] is False
    line = body["lines"][0]
    assert line["person_name"] == "Teamlid Voorbeeld"
    assert line["description"] == "Productmanager"
    assert Decimal(line["planned_fte_pct"]) == Decimal("80")
    assert line["established_fte_pct"] is None
    assert line["category"] == "D"
    assert line["planned_amount_cents"] == PLANNED_CENTS
    assert body["planned_total_cents"] == PLANNED_CENTS
    assert body["established_total_cents"] is None


async def test_close_at_an_adjusted_percentage(act_as, world):
    client = act_as(world.manager)
    response = await client.post(
        f"{_base(world)}/months/2026-03/close",
        json={
            "established": [
                {"allocation_id": str(world.allocation.id), "fte_pct": "60"}
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["closed"] is True
    assert body["closed_by_name"] == "Opdracht Manager"
    assert body["may_close"] is False
    line = body["lines"][0]
    assert Decimal(line["established_fte_pct"]) == Decimal("60")
    assert line["established_amount_cents"] == 1_080_000
    assert body["established_total_cents"] == 1_080_000
    assert len(body["history"]) == 1

    timeline = (await client.get(f"{_base(world)}/months")).json()["months"]
    assert [m["closed"] for m in timeline[:4]] == [False, False, True, False]

    # Closing twice is refused.
    again = await client.post(f"{_base(world)}/months/2026-03/close", json={})
    assert again.status_code == 422


async def test_the_amount_follows_the_percentage_before_the_month_is_closed(
    act_as, world
):
    """The same figure the close then settles, and nothing is changed by asking."""
    client = act_as(world.manager)
    url = f"{_base(world)}/months/2026-03/preview"
    plan = (await client.post(url, json={})).json()
    assert plan["total_cents"] == PLANNED_CENTS
    preview = await client.post(
        url,
        json={
            "established": [
                {"allocation_id": str(world.allocation.id), "fte_pct": "60"}
            ]
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["lines"] == [
        {"allocation_id": str(world.allocation.id), "amount_cents": 1_080_000}
    ]
    assert body["total_cents"] == 1_080_000
    still = (await client.get(f"{_base(world)}/months/2026-03")).json()
    assert still["closed"] is False
    assert still["lines"][0]["planned_amount_cents"] == PLANNED_CENTS

    # Only who closes the month may ask.
    for person in (world.planner, world.member, world.lezer, world.outsider):
        refused = await act_as(person).post(url, json={})
        assert refused.status_code in (403, 404)


async def test_close_without_changes_takes_the_plan(act_as, world):
    client = act_as(world.manager)
    body = (await client.post(f"{_base(world)}/months/2026-02/close", json={})).json()
    assert Decimal(body["lines"][0]["established_fte_pct"]) == Decimal("80")
    assert body["established_total_cents"] == PLANNED_CENTS


async def test_a_month_that_has_not_ended_cannot_be_closed(act_as, world, db_session):
    world.assignment.end_date = date(2099, 12, 31)
    await db_session.flush()
    client = act_as(world.manager)
    response = await client.post(f"{_base(world)}/months/2099-01/close", json={})
    assert response.status_code == 422
    assert "nog niet voorbij" in response.json()["detail"]


async def test_close_refuses_bad_input(act_as, world):
    client = act_as(world.manager)
    for payload in (
        {
            "established": [
                {"allocation_id": str(world.allocation.id), "fte_pct": "120"}
            ]
        },
        {"established": [{"allocation_id": str(world.line.id), "fte_pct": "50"}]},
    ):
        response = await client.post(
            f"{_base(world)}/months/2026-03/close", json=payload
        )
        assert response.status_code == 422, payload
    assert (await client.get(f"{_base(world)}/months/20260")).status_code == 422


async def test_only_a_manager_closes_and_only_a_beheerder_reopens(act_as, world):
    for person in (world.lezer, world.planner, world.member, world.beheerder):
        client = act_as(person)
        response = await client.post(f"{_base(world)}/months/2026-03/close", json={})
        assert response.status_code == 403, person.email

    client = act_as(world.manager)
    assert (
        await client.post(f"{_base(world)}/months/2026-03/close", json={})
    ).status_code == 200
    refused = await client.post(
        f"{_base(world)}/months/2026-03/reopen", json={"reason": "Vergissing"}
    )
    assert refused.status_code == 403

    client = act_as(world.beheerder)
    no_reason = await client.post(
        f"{_base(world)}/months/2026-03/reopen", json={"reason": ""}
    )
    assert no_reason.status_code == 422
    reopened = await client.post(
        f"{_base(world)}/months/2026-03/reopen",
        json={"reason": "Inzet was 60 procent"},
    )
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["closed"] is False
    assert body["history"][0]["reopen_reason"] == "Inzet was 60 procent"
    assert body["history"][0]["reopened_by_name"] == world.beheerder.name

    client = act_as(world.manager)
    timeline = (await client.get(f"{_base(world)}/months")).json()["months"]
    assert timeline[2]["closed"] is False
    assert timeline[2]["reopen_count"] == 1


async def test_what_each_reader_sees_of_a_month(act_as, world):
    client = act_as(world.manager)
    await client.post(f"{_base(world)}/months/2026-03/close", json={})

    # Lezer: basics and totals, nobody's name or rate.
    body = (await act_as(world.lezer).get(f"{_base(world)}/months/2026-03")).json()
    assert body["closed"] is True
    assert body["planned_total_cents"] == PLANNED_CENTS
    assert "lines" not in body
    assert body["may_close"] is False

    # Planner: who and how much time, no rate, no amount, no totals.
    body = (await act_as(world.planner).get(f"{_base(world)}/months/2026-03")).json()
    line = body["lines"][0]
    assert line["person_name"] == "Teamlid Voorbeeld"
    assert "planned_fte_pct" in line
    for hidden in (
        "category",
        "monthly_rate_cents",
        "planned_amount_cents",
        "established_amount_cents",
    ):
        assert hidden not in line
    assert "planned_total_cents" not in body
    assert "established_total_cents" not in body

    # Member: names and roles only.
    body = (await act_as(world.member).get(f"{_base(world)}/months/2026-03")).json()
    line = body["lines"][0]
    assert set(line) == {"allocation_id", "person_id", "person_name", "description"}
    assert "planned_total_cents" not in body

    # Outsider: the assignment does not exist.
    for path in ("/months", "/months/2026-03", "/months/2026-03/billing-data"):
        response = await act_as(world.outsider).get(f"{_base(world)}{path}")
        assert response.status_code == 404, path


async def test_billing_data_follows_the_established_inzet(act_as, world):
    client = act_as(world.manager)
    not_closed = await client.get(f"{_base(world)}/months/2026-03/billing-data")
    assert not_closed.status_code == 422

    await client.post(
        f"{_base(world)}/months/2026-03/close",
        json={
            "established": [
                {"allocation_id": str(world.allocation.id), "fte_pct": "50"}
            ]
        },
    )
    body = (await client.get(f"{_base(world)}/months/2026-03/billing-data")).json()
    assert body["total_cents"] == 900_000
    line = body["lines"][0]
    assert line["description"] == "Productmanager"
    assert line["person_name"] == "Teamlid Voorbeeld"
    assert line["amount_cents"] == 900_000

    # Lezer: the total, no line.
    body = (
        await act_as(world.lezer).get(f"{_base(world)}/months/2026-03/billing-data")
    ).json()
    assert body["total_cents"] == 900_000
    assert "lines" not in body
    # Planner: the line without money, and no total.
    body = (
        await act_as(world.planner).get(f"{_base(world)}/months/2026-03/billing-data")
    ).json()
    assert "total_cents" not in body
    assert "amount_cents" not in body["lines"][0]
    assert "category" not in body["lines"][0]


async def test_export_run_and_csv(act_as, world):
    client = act_as(world.manager)
    await client.post(f"{_base(world)}/months/2026-03/close", json={})
    created = await client.post(f"{_base(world)}/months/2026-03/billing-exports")
    assert created.status_code == 201, created.text
    export = created.json()
    assert export["month"] == "2026-03"
    assert export["total_cents"] == PLANNED_CENTS
    assert export["exported_by_name"] == "Opdracht Manager"
    assert export["lines"][0]["amount_cents"] == PLANNED_CENTS

    listed = (await client.get(f"{_base(world)}/billing-exports")).json()
    assert [e["id"] for e in listed["exports"]] == [export["id"]]

    response = await client.get(f"/api/billing-exports/{export['id']}/csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "export_id",
        "exported_at",
        "assignment_uri",
        "assignment_name",
        "client_name",
        "month",
        "line_number",
        "description",
        "fte_pct",
        "rate_category",
        "monthly_rate",
        "amount",
        "currency",
    ]
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["assignment_name"] == "Opdracht Alfa"
    assert row["client_name"] == "Voorbeeldministerie"
    assert row["month"] == "2026-03"
    assert row["description"] == "Productmanager"
    assert row["fte_pct"] == "80"
    assert row["rate_category"] == "D"
    assert row["monthly_rate"] == "18000.00"
    assert row["amount"] == "14400.00"
    assert row["currency"] == "EUR"
    # No person's name anywhere in the file.
    assert "Teamlid" not in response.text


async def test_export_is_for_the_manager(act_as, world):
    client = act_as(world.manager)
    await client.post(f"{_base(world)}/months/2026-03/close", json={})
    export = (
        await client.post(f"{_base(world)}/months/2026-03/billing-exports")
    ).json()

    for person in (world.lezer, world.planner, world.member):
        response = await act_as(person).post(
            f"{_base(world)}/months/2026-03/billing-exports"
        )
        assert response.status_code == 403, person.email
    # The CSV holds a rate per line, so totals alone are not enough.
    for person in (world.lezer, world.planner):
        response = await act_as(person).get(f"/api/billing-exports/{export['id']}/csv")
        assert response.status_code == 403, person.email
    assert (
        await act_as(world.outsider).get(f"/api/billing-exports/{export['id']}/csv")
    ).status_code == 404

    # Lezer: the runs and their totals, no lines.
    listed = (await act_as(world.lezer).get(f"{_base(world)}/billing-exports")).json()
    assert listed["exports"][0]["total_cents"] == PLANNED_CENTS
    assert "lines" not in listed["exports"][0]


async def test_export_needs_a_closed_month(act_as, world):
    client = act_as(world.manager)
    response = await client.post(f"{_base(world)}/months/2026-03/billing-exports")
    assert response.status_code == 422


async def test_csv_does_not_start_a_formula(act_as, world, db_session):
    world.line.role = "=HYPERLINK(1)"
    await db_session.flush()
    client = act_as(world.manager)
    await client.post(f"{_base(world)}/months/2026-03/close", json={})
    export = (
        await client.post(f"{_base(world)}/months/2026-03/billing-exports")
    ).json()
    text = (await client.get(f"/api/billing-exports/{export['id']}/csv")).text
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[1][7] == "'=HYPERLINK(1)"
