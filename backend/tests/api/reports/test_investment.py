"""Investeerruimte: in money for the year, in time for the coming months."""

from datetime import date
from decimal import Decimal

from grip.calc import Month
from grip.core import clock
from grip.services import assignments, rates
from grip.services.reports import investment, steering

from .conftest import (
    ALFA_FORECAST_2026,
    ALFA_REALISED_2026,
    BETA_PIPELINE_2026,
)

URL = "/api/reports/investment"

# The member must bring in 90 percent of twelve months in category D.
TARGET_2026 = 19440000
# 70 percent of the hosting contract of 15,000 is covered by nothing.
UNCOVERED_2026 = 1050000
EXPECTED_2026 = ALFA_REALISED_2026 + ALFA_FORECAST_2026


async def _get(client, year: int = 2026):
    response = await client.get(URL, params={"year": year})
    assert response.status_code == 200
    return response


async def test_the_derivation_adds_up_line_by_line(as_person, world):
    money = (await _get(as_person(world.beheerder))).json()["money"]
    assert money["realised_cents"] == ALFA_REALISED_2026
    assert money["planned_cents"] == ALFA_FORECAST_2026
    assert money["expected_cents"] == EXPECTED_2026
    assert money["target_cents"] == TARGET_2026
    assert money["target_person_count"] == 1
    assert money["uncovered_cents"] == UNCOVERED_2026
    assert money["internal_budget_cents"] == 0
    assert money["room_cents"] == EXPECTED_2026 - TARGET_2026 - UNCOVERED_2026
    # Less expected than the people must bring in: a shortfall, said as such.
    assert money["room_cents"] < 0
    assert money["shortfall"] is True
    # The pipeline does not count; it is shown apart.
    assert money["pipeline_cents"] == BETA_PIPELINE_2026
    assert money["room_with_pipeline_cents"] == (
        money["room_cents"] + BETA_PIPELINE_2026
    )


async def test_the_months_add_up_to_the_year(as_person, world):
    money = (await _get(as_person(world.beheerder))).json()["money"]
    months = money["months"]
    assert len(months) == 12
    assert sum(m["realised_cents"] for m in months) == money["realised_cents"]
    assert sum(m["planned_cents"] for m in months) == money["planned_cents"]
    assert sum(m["target_cents"] for m in months) == money["target_cents"]
    july = next(m for m in months if m["month"] == "2026-07")
    assert july["realised_cents"] == ALFA_REALISED_2026
    assert july["target_cents"] == TARGET_2026 // 12
    assert july["turnover_minus_target_cents"] == ALFA_REALISED_2026 - TARGET_2026 // 12


async def test_an_internal_assignment_consumes_room(as_person, world, db_session):
    before = (await _get(as_person(world.beheerder))).json()["money"]
    internal = await assignments.create_assignment(
        db_session,
        name="Interne opdracht Kennisdeling",
        kind="internal",
        actor=world.beheerder,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    await assignments.add_budget_line(
        db_session,
        internal.id,
        description="Opleidingsbudget",
        kind="fixed",
        amount_cents=500000,
        year=2026,
        actor=world.beheerder,
    )
    # Not agreed yet: budgeted, but nothing is consumed.
    draft = (await _get(as_person(world.beheerder))).json()["money"]
    assert draft["internal_budget_cents"] == 0
    assert draft["internal_count"] == 0

    await assignments.transition(
        db_session, internal.id, "accepted", actor=world.beheerder
    )
    after = (await _get(as_person(world.beheerder))).json()["money"]
    assert after["internal_budget_cents"] == 500000
    assert after["internal_count"] == 1
    assert after["room_cents"] == before["room_cents"] - 500000
    # An internal assignment brings in no turnover.
    assert after["expected_cents"] == before["expected_cents"]


async def test_verbally_agreed_turnover_counts_and_is_shown_apart(
    as_person, world, db_session
):
    world.beta.status = "verbally_agreed"
    await db_session.flush()
    money = (await _get(as_person(world.beheerder))).json()["money"]
    assert money["planned_cents"] == ALFA_FORECAST_2026 + BETA_PIPELINE_2026
    assert money["verbal_cents"] == BETA_PIPELINE_2026
    assert money["pipeline_cents"] == 0


async def test_a_lezer_gets_no_sum_that_gives_one_target_away(as_person, world):
    response = await _get(as_person(world.lezer))
    body = response.json()
    # One person has a target: the sum is that person's target, and so is
    # the figure minus the other lines. Neither is shown.
    assert "money" not in body
    assert body["money_withheld"] == {"reason": "few_targets", "min_persons": 5}
    assert str(TARGET_2026) not in response.text
    assert "room_cents" not in response.text
    # No reading in time either: a lezer sees no staffing.
    assert "time" not in body


async def test_a_lezer_gets_the_totals_when_the_sum_covers_enough_people(
    as_person, world, db_session, create_person
):
    for index in range(4):
        person = await create_person(
            f"extra{index}@example.org", name=f"Extra Persoon {index}"
        )
        await rates.set_person_scale(
            db_session, person.id, date(2026, 1, 1), 14, actor=world.beheerder
        )
        await rates.set_billability_target(
            db_session, person.id, 2026, Decimal("50"), actor=world.beheerder
        )
    response = await _get(as_person(world.lezer))
    body = response.json()
    assert "money_withheld" not in body
    money = body["money"]
    assert money["target_person_count"] == 5
    assert money["target_cents"] == TARGET_2026 + 4 * 10800000
    assert money["room_cents"] == (
        EXPECTED_2026 - money["target_cents"] - UNCOVERED_2026
    )
    # Totals only: no name, and per month no target, since a month can hold
    # fewer people than the year.
    for name in world.staff_names:
        assert name not in response.text
    assert all(month["target_cents"] is None for month in money["months"])
    assert all(
        month["turnover_minus_target_cents"] is None for month in money["months"]
    )


async def test_without_any_target_there_is_nothing_to_give_away(
    as_person, world, db_session
):
    from grip.models.person_details import BillabilityTarget

    await db_session.execute(BillabilityTarget.__table__.delete())
    body = (await _get(as_person(world.lezer))).json()
    assert body["money"]["target_cents"] == 0
    assert body["money"]["target_person_count"] == 0


async def test_free_capacity_is_valued_at_each_persons_billing_rate(db_session, world):
    window = steering.next_months(Month(2026, 10), 4)
    reading = await investment.time_reading(db_session, window)
    october, november, december, january = reading.months
    assert reading.person_count == 3
    # The colleague is at 50 percent in category C: half of 15,000.
    assert str(october.free_fte) == "0.50"
    assert october.value_cents == 750000
    assert (november.value_cents, december.value_cents) == (750000, 750000)
    # In January the tentative inzet has ended: one more person is free, at
    # the rates of the new year (category C 15,750 and D 18,900).
    assert str(january.free_fte) == "1.50"
    assert january.value_cents == 787500 + 1890000
    assert all(month.unvalued_count == 0 for month in reading.months)
    assert reading.value_cents == 3 * 750000 + 787500 + 1890000


async def test_a_person_without_a_billing_rate_is_free_but_not_valued(
    db_session, world
):
    # A month without a rate card: free capacity is known, its value is not.
    window = steering.next_months(Month(2028, 1), 1)
    reading = await investment.time_reading(db_session, window)
    (january,) = reading.months
    assert str(january.free_fte) == "3.00"
    assert january.value_cents == 0
    assert january.unvalued_count == 3


async def test_a_planner_gets_the_time_in_fte_and_no_money(as_person, world):
    response = await _get(as_person(world.planner))
    body = response.json()
    assert set(body) == {"year", "time"}
    time = body["time"]
    assert time["person_count"] == 3
    assert len(time["months"]) == 4
    assert "free_fte" in time and "free_fte" in time["months"][0]
    assert "cents" not in response.text
    assert "unvalued_count" not in response.text


async def test_the_beheerder_gets_both_readings_with_the_valuation(as_person, world):
    body = (await _get(as_person(world.beheerder))).json()
    assert set(body) == {"year", "money", "time"}
    assert "value_cents" in body["time"]
    assert "value_cents" in body["time"]["months"][0]
    today = clock.today()
    assert body["time"]["months"][0]["month"] == f"{today.year:04d}-{today.month:02d}"


async def test_it_is_not_for_someone_who_sees_part_of_the_organisation(
    as_person, world
):
    # An owner sees the own assignments, a line manager the own reports:
    # neither sees the organisation, and this figure is about nothing less.
    for person in (world.owner, world.leader, world.member, world.outsider):
        body = (await _get(as_person(person))).json()
        assert body == {"year": 2026}
