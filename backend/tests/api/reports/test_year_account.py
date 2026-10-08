"""The year account, and its CSV export."""

import csv
import io

from grip.services.reports.year_account import CSV_COLUMNS

from .conftest import (
    ALFA_BUDGET_2026,
    ALFA_BUDGET_2027,
    ALFA_COVERAGE_2026,
    ALFA_FORECAST_2026,
    ALFA_REALISED_2026,
    BETA_PIPELINE_2026,
)

URL = "/api/reports/year-account"


def _row(body, name):
    return next(row for row in body["rows"] if row["name"] == name)


async def test_a_multi_year_assignment_is_split_per_year(as_person, world):
    client = as_person(world.beheerder)
    body = (await client.get(URL, params={"year": 2026})).json()
    assert body["scope"] == "all"
    alfa = _row(body, "Opdracht Alfa")
    assert alfa["client_name"] == "Voorbeeldministerie"
    assert alfa["status"] == "in_progress"
    assert alfa["agreed_cents"] == ALFA_BUDGET_2026
    assert alfa["budgeted_cents"] == ALFA_BUDGET_2026
    assert alfa["realised_cents"] == ALFA_REALISED_2026
    assert alfa["forecast_cents"] == ALFA_FORECAST_2026
    assert alfa["costs_cents"] == ALFA_COVERAGE_2026
    assert alfa["delivered_cents"] == world.export.total_cents == ALFA_REALISED_2026
    assert alfa["to_deliver_cents"] == 0
    # Delivered is not invoiced: no invoice is recorded yet.
    assert alfa["invoiced_cents"] == 0
    assert alfa["to_invoice_cents"] == ALFA_REALISED_2026
    assert alfa["difference_cents"] == ALFA_BUDGET_2026 - ALFA_REALISED_2026

    beta = _row(body, "Opdracht Beta")
    assert beta["agreed_cents"] is None
    assert beta["difference_cents"] is None
    assert beta["budgeted_cents"] == BETA_PIPELINE_2026

    totals = body["totals"]
    assert totals["agreed_cents"] == ALFA_BUDGET_2026
    assert totals["realised_cents"] == ALFA_REALISED_2026
    assert totals["delivered_cents"] == ALFA_REALISED_2026
    assert totals["budgeted_cents"] == ALFA_BUDGET_2026 + BETA_PIPELINE_2026

    next_year = (await client.get(URL, params={"year": 2027})).json()
    assert [row["name"] for row in next_year["rows"]] == ["Opdracht Alfa"]
    alfa_2027 = next_year["rows"][0]
    assert alfa_2027["agreed_cents"] == ALFA_BUDGET_2027
    assert alfa_2027["realised_cents"] == 0
    assert alfa_2027["delivered_cents"] == 0

    assert (await client.get(URL, params={"year": 2025})).json()["rows"] == []


async def test_realised_and_not_yet_delivered(as_person, world, db_session):
    from decimal import Decimal

    from grip.calc import Month
    from grip.services import month_close

    await month_close.close_month(
        db_session,
        world.alfa.id,
        Month(2026, 8),
        actor=world.owner,
        established={
            world.member_allocation.id: Decimal("100"),
            world.colleague_allocation.id: Decimal("50"),
        },
    )
    body = (await as_person(world.beheerder).get(URL, params={"year": 2026})).json()
    alfa = _row(body, "Opdracht Alfa")
    assert alfa["realised_cents"] == ALFA_REALISED_2026 + 1800000 + 750000
    assert alfa["delivered_cents"] == ALFA_REALISED_2026
    assert alfa["to_deliver_cents"] == 1800000 + 750000


async def test_invoiced_only_once_an_invoice_is_recorded(as_person, world, db_session):
    from datetime import date

    from grip.services import outgoing_invoices

    client = as_person(world.beheerder)
    before = (await client.get(URL, params={"year": 2026})).json()
    assert _row(before, "Opdracht Alfa")["invoiced_cents"] == 0
    assert before["totals"]["invoiced_cents"] == 0
    assert before["totals"]["to_invoice_cents"] == ALFA_REALISED_2026

    await outgoing_invoices.record_invoice(
        db_session,
        world.alfa.id,
        export_ids=[world.export.id],
        invoice_number="F-2026-001",
        invoice_date=date(2026, 8, 15),
        amount_cents=ALFA_REALISED_2026,
        actor=world.owner,
        today=date(2026, 10, 1),
    )
    after = (await client.get(URL, params={"year": 2026})).json()
    alfa = _row(after, "Opdracht Alfa")
    assert alfa["delivered_cents"] == ALFA_REALISED_2026
    assert alfa["invoiced_cents"] == ALFA_REALISED_2026
    assert alfa["to_invoice_cents"] == 0
    assert after["totals"]["invoiced_cents"] == ALFA_REALISED_2026


async def test_an_export_of_a_reopened_month_does_not_count(
    as_person, world, db_session
):
    from grip.calc import Month
    from grip.services import month_close

    await month_close.reopen_month(
        db_session,
        world.alfa.id,
        Month(2026, 7),
        actor=world.beheerder,
        reason="Fictieve correctie",
    )
    body = (await as_person(world.beheerder).get(URL, params={"year": 2026})).json()
    alfa = _row(body, "Opdracht Alfa")
    assert alfa["delivered_cents"] == 0
    assert alfa["realised_cents"] == 0


async def test_a_planner_gets_the_rows_without_amounts(as_person, world):
    response = await as_person(world.planner).get(URL, params={"year": 2026})
    body = response.json()
    assert {row["name"] for row in body["rows"]} == {"Opdracht Alfa", "Opdracht Beta"}
    assert "totals" not in body
    assert "cents" not in response.text


async def test_an_owner_gets_the_own_rows_and_their_total(as_person, world):
    body = (await as_person(world.owner).get(URL, params={"year": 2026})).json()
    assert body["scope"] == "own"
    assert [row["name"] for row in body["rows"]] == ["Opdracht Alfa"]
    assert body["totals"]["budgeted_cents"] == ALFA_BUDGET_2026


async def test_someone_without_a_relation_gets_nothing(as_person, world):
    body = (await as_person(world.outsider).get(URL, params={"year": 2026})).json()
    assert body == {"year": 2026, "scope": "own", "rows": []}


async def test_the_csv_has_the_documented_columns(as_person, world):
    response = await as_person(world.beheerder).get(f"{URL}/csv", params={"year": 2026})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "jaarverantwoording-2026.csv" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert tuple(rows[0]) == CSV_COLUMNS
    by_name = {row[2]: dict(zip(CSV_COLUMNS, row, strict=True)) for row in rows[1:]}
    alfa = by_name["Opdracht Alfa"]
    assert alfa["year"] == "2026"
    assert alfa["assignment_uri"] == world.alfa.uri
    assert alfa["agreed"] == "153000.00"
    assert alfa["realised"] == "21900.00"
    assert alfa["delivered"] == "21900.00"
    assert alfa["to_deliver"] == "0.00"
    assert alfa["currency"] == "EUR"
    # Billing data delivered is not an invoice: nothing is invoiced until
    # an invoice is recorded.
    assert "billed" not in rows[0]
    assert alfa["invoiced"] == "0.00"
    assert alfa["to_invoice"] == "21900.00"
    assert rows[0][-3:] == ["currency", "invoiced", "to_invoice"]
    # Not agreed: empty, which is not the same as zero.
    assert by_name["Opdracht Beta"]["agreed"] == ""
    for name in world.staff_names:
        assert name not in response.text


async def test_the_csv_follows_the_reader(as_person, world):
    owner = await as_person(world.owner).get(f"{URL}/csv", params={"year": 2026})
    rows = list(csv.reader(io.StringIO(owner.text)))
    assert [row[2] for row in rows[1:]] == ["Opdracht Alfa"]

    for person in (world.planner, world.member, world.outsider):
        refused = await as_person(person).get(f"{URL}/csv", params={"year": 2026})
        assert refused.status_code == 403


async def test_a_name_cannot_become_a_formula(as_person, world, db_session):
    from grip.services import assignments

    await assignments.update_assignment(
        db_session, world.alfa.id, actor=world.owner, name="=SOM(A1:A9)"
    )
    response = await as_person(world.beheerder).get(f"{URL}/csv", params={"year": 2026})
    rows = list(csv.reader(io.StringIO(response.text)))
    assert "'=SOM(A1:A9)" in [row[2] for row in rows[1:]]
