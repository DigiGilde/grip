"""The pricing bridge reproduces the worked examples through the database."""

from datetime import date
from decimal import Decimal

import pytest

from grip import calc
from grip.calc import Month
from grip.services import assignments, costs, month_close, pricing, rates
from grip.services.errors import DomainValidationError


async def test_r4_budgeted_personnel_line(
    db_session, rate_cards, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    await add_personnel_line(assignment)  # 0.8 FTE, category D, all of 2026

    overview = await pricing.assignment_overview(db_session, assignment.id)

    assert overview.budgeted_cents == 172_800_00
    assert overview.used_cents == 0
    assert overview.available_cents == 172_800_00


async def test_r7_coverage_of_a_cost_item(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    line = await add_personnel_line(assignment)
    item = await costs.create_cost_item(
        db_session, description="Hostingcontract", actor=beheerder
    )
    await costs.add_invoice_line(
        db_session,
        item.id,
        kind="actual",
        amount_cents=10_000_00,
        period=date(2026, 3, 1),
        actor=beheerder,
    )
    await costs.add_invoice_line(
        db_session,
        item.id,
        kind="estimate",
        amount_cents=5_000_00,
        period=date(2026, 9, 1),
        actor=beheerder,
    )
    await costs.set_coverage(db_session, item.id, line.id, Decimal(30), actor=beheerder)

    overview = await pricing.assignment_overview(db_session, assignment.id)
    coverage = await pricing.cost_item_coverage(db_session, item.id)

    assert overview.coverage_cents == 4_500_00
    assert overview.used_cents == 4_500_00
    assert coverage.basis_cents == 15_000_00
    assert coverage.covered_cents == 4_500_00
    assert coverage.uncovered_cents == 10_500_00


async def test_coverage_above_100_percent_is_refused(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    first = await add_personnel_line(assignment)
    second = await add_personnel_line(assignment, description="Developer")
    item = await costs.create_cost_item(
        db_session, description="Hosting", actor=beheerder
    )
    await costs.set_coverage(
        db_session, item.id, first.id, Decimal(70), actor=beheerder
    )

    with pytest.raises(DomainValidationError):
        await costs.set_coverage(
            db_session, item.id, second.id, Decimal(40), actor=beheerder
        )


async def test_r12_and_r13_kpi(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)  # scale 14 bills in category D
    assignment = await make_assignment()
    line = await add_personnel_line(assignment, fte="1")
    await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal(100),
        actor=beheerder,
    )
    await rates.set_billability_target(
        db_session, person.id, 2026, Decimal(90), actor=beheerder
    )

    kpi = await pricing.kpi_overview(db_session, person.id, 2026)

    assert kpi.realisation_cents == 216_000_00
    assert kpi.target_cents == 194_400_00
    # Nothing is closed yet, so all of it is forecast.
    assert kpi.realised_cents == 0
    assert kpi.forecast_cents == 216_000_00


async def test_period_over_new_year_is_priced_per_year(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await add_personnel_line(
        assignment, fte="1", start=date(2026, 7, 1), end=date(2027, 6, 30)
    )
    await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        fte_pct=Decimal(100),
        actor=beheerder,
    )

    whole = await pricing.assignment_overview(db_session, assignment.id)
    y2026 = await pricing.assignment_overview(db_session, assignment.id, year=2026)
    y2027 = await pricing.assignment_overview(db_session, assignment.id, year=2027)
    by_year = await pricing.budgeted_by_year(db_session, assignment.id)

    assert y2026.budgeted_cents == 6 * 18_000_00
    assert y2027.budgeted_cents == 6 * 18_900_00
    assert whole.budgeted_cents == y2026.budgeted_cents + y2027.budgeted_cents
    assert y2026.used_cents == 6 * 18_000_00
    assert y2027.used_cents == 6 * 18_900_00
    assert by_year == {2026: 6 * 18_000_00, 2027: 6 * 18_900_00}


async def test_month_without_rate_card_is_an_error(
    db_session, rate_cards, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    await add_personnel_line(assignment, start=date(2028, 1, 1), end=date(2028, 3, 31))

    with pytest.raises(calc.MissingRateCardError):
        await pricing.assignment_overview(db_session, assignment.id)


async def test_closed_months_count_established_open_months_planned(
    db_session,
    rate_cards,
    beheerder,
    make_person,
    make_assignment,
    add_personnel_line,
    accept,
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await add_personnel_line(assignment, fte="1")
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal(100),
        actor=beheerder,
    )

    await accept(assignment)

    # January as planned, February established at 50 percent.
    await month_close.close_month(
        db_session, assignment.id, Month(2026, 1), actor=beheerder
    )
    await month_close.close_month(
        db_session,
        assignment.id,
        Month(2026, 2),
        actor=beheerder,
        established={allocation.id: Decimal(50)},
    )

    overview = await pricing.assignment_overview(db_session, assignment.id)
    totals = await pricing.assignment_totals(db_session, assignment.id)
    kpi = await pricing.kpi_overview(db_session, person.id, 2026)

    assert overview.realised_cents == 18_000_00 + 9_000_00
    assert overview.forecast_cents == 10 * 18_000_00
    assert overview.used_cents == 207_000_00
    # The split adds up to R9 and R11 of the calculation module.
    assert totals.used_cents == overview.used_cents
    assert totals.budgeted_cents == overview.budgeted_cents
    assert totals.available_cents == overview.available_cents
    assert kpi.realised_cents == 27_000_00
    assert kpi.forecast_cents == 180_000_00


async def test_overrun_is_flagged(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(16)  # category E, dearer than the line assumes
    assignment = await make_assignment()
    line = await add_personnel_line(assignment, fte="1", category="D")
    await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal(100),
        actor=beheerder,
    )

    overview = await pricing.assignment_overview(db_session, assignment.id)
    signals = await pricing.category_signals(db_session, assignment.id)

    assert overview.available_cents == 12 * (18_000_00 - 21_000_00)
    assert overview.overrun
    assert len(signals) == 1
    assert signals[0].line_category == "D"
    assert signals[0].person_category == "E"
    assert signals[0].direction is calc.MismatchDirection.OVERRUN


async def test_mid_year_scale_change(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(12)  # category C
    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 14, actor=beheerder
    )
    assignment = await make_assignment()
    line = await add_personnel_line(assignment, fte="1")
    await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal(100),
        actor=beheerder,
    )

    overview = await pricing.assignment_overview(db_session, assignment.id)

    assert overview.used_cents == 6 * 15_000_00 + 6 * 18_000_00
