"""Audit rows, and the lock on a closed year."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from grip.calc import Month
from grip.models.audit_log import AuditLog
from grip.services import assignments, costs, month_close, rates
from grip.services.errors import ClosedYearError, DomainValidationError


async def _audit(db_session, entity: str) -> list[AuditLog]:
    result = await db_session.execute(select(AuditLog).where(AuditLog.entity == entity))
    # Rows of one transaction share a timestamp; create sorts before update.
    return sorted(result.scalars(), key=lambda r: r.action)


async def test_changes_write_audit_rows(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await add_personnel_line(assignment)
    await assignments.update_budget_line(
        db_session, line.id, fte=Decimal("0.6"), actor=beheerder
    )
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        fte_pct=Decimal(60),
        actor=beheerder,
    )
    await assignments.update_allocation(
        db_session, allocation.id, fte_pct=Decimal(40), actor=beheerder
    )
    item = await costs.create_cost_item(
        db_session, description="Hosting", actor=beheerder
    )
    await costs.set_coverage(db_session, item.id, line.id, Decimal(30), actor=beheerder)
    await costs.set_coverage(db_session, item.id, line.id, Decimal(50), actor=beheerder)
    await rates.set_rate_band(db_session, 2026, "D", 19_000_00, actor=beheerder)
    await db_session.flush()

    line_rows = await _audit(db_session, "budget_line")
    assert [r.action for r in line_rows] == ["create", "update"]
    assert line_rows[1].old_value == {"fte": "0.8"}
    assert line_rows[1].new_value == {"fte": "0.6"}
    assert all(r.actor_id == beheerder.id for r in line_rows)

    allocation_rows = await _audit(db_session, "allocation")
    assert [r.action for r in allocation_rows] == ["create", "update"]
    assert allocation_rows[1].old_value["fte_pct"] == "60"
    assert allocation_rows[1].new_value["fte_pct"] == "40"

    coverage_rows = await _audit(db_session, "cost_coverage")
    assert [r.action for r in coverage_rows] == ["create", "update"]
    assert coverage_rows[1].old_value["pct"] == "30"

    band_rows = [
        r
        for r in await _audit(db_session, "rate_band")
        if r.entity_id == "2026/D" and r.action == "update"
    ]
    assert band_rows[-1].old_value == {"monthly_rate_cents": 18_000_00}
    assert band_rows[-1].new_value == {"monthly_rate_cents": 19_000_00}

    scale_rows = await _audit(db_session, "person_scale")
    assert scale_rows and scale_rows[0].new_value["billing_scale"] == 14


async def test_closed_year_refuses_changes_without_the_flag(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await add_personnel_line(assignment)
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal(100),
        actor=beheerder,
    )
    await rates.set_rate_card_status(db_session, 2026, "closed", actor=beheerder)

    with pytest.raises(ClosedYearError):
        await rates.set_rate_band(db_session, 2026, "D", 19_000_00, actor=beheerder)
    with pytest.raises(ClosedYearError):
        await rates.set_scale_band(db_session, 2026, 14, "E", actor=beheerder)
    with pytest.raises(ClosedYearError):
        await assignments.update_budget_line(
            db_session, line.id, fte=Decimal("0.5"), actor=beheerder
        )
    with pytest.raises(ClosedYearError):
        await assignments.update_allocation(
            db_session, allocation.id, fte_pct=Decimal(50), actor=beheerder
        )
    with pytest.raises(ClosedYearError):
        await assignments.add_budget_line(
            db_session,
            assignment.id,
            description="Hosting",
            kind="fixed",
            amount_cents=100,
            year=2026,
            actor=beheerder,
        )
    with pytest.raises(ClosedYearError):
        await rates.set_person_scale(
            db_session, person.id, date(2026, 6, 1), 15, actor=beheerder
        )
    with pytest.raises(ClosedYearError):
        await month_close.close_month(
            db_session, assignment.id, Month(2026, 1), actor=beheerder
        )
    with pytest.raises(ClosedYearError):
        await rates.set_rate_card_status(db_session, 2026, "active", actor=beheerder)

    # 2027 is open: the same kind of change goes through there.
    await rates.set_rate_band(db_session, 2027, "D", 19_500_00, actor=beheerder)


async def test_closed_year_change_with_the_flag_is_audited(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    line = await add_personnel_line(assignment)
    await rates.set_rate_card_status(db_session, 2026, "closed", actor=beheerder)

    await rates.set_rate_band(
        db_session, 2026, "D", 19_000_00, actor=beheerder, allow_closed_year=True
    )
    await assignments.update_budget_line(
        db_session, line.id, fte=Decimal("0.5"), actor=beheerder, allow_closed_year=True
    )
    await db_session.flush()

    band = [
        r
        for r in await _audit(db_session, "rate_band")
        if r.entity_id == "2026/D" and r.action == "update"
    ][-1]
    assert band.new_value == {
        "monthly_rate_cents": 19_000_00,
        "closed_year_override": [2026],
    }
    assert band.actor_id == beheerder.id
    line_row = [
        r for r in await _audit(db_session, "budget_line") if r.action == "update"
    ][-1]
    assert line_row.new_value["closed_year_override"] == [2026]


async def test_new_year_starts_as_draft_copy(db_session, rate_cards, beheerder):
    card = await rates.create_rate_card(
        db_session, 2028, actor=beheerder, copy_from=2027
    )

    assert card.status == "draft"
    assert {b.category: b.monthly_rate_cents for b in card.rate_bands}["D"] == 18_900_00
    assert len(card.scale_bands) == 10
    with pytest.raises(DomainValidationError):
        await rates.create_rate_card(db_session, 2028, actor=beheerder)
    with pytest.raises(DomainValidationError):
        await rates.set_rate_card_status(db_session, 2026, "draft", actor=beheerder)


async def test_person_scale_periods(db_session, rate_cards, beheerder, make_person):
    from grip.repositories.domain import PersonDetailRepository

    person = await make_person(12)
    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 14, actor=beheerder
    )
    scales = await PersonDetailRepository(db_session).scales([person.id])

    assert [(s.valid_from, s.valid_to, s.billing_scale) for s in scales] == [
        (date(2026, 1, 1), date(2026, 6, 30), 12),
        (date(2026, 7, 1), None, 14),
    ]
    with pytest.raises(DomainValidationError):
        await rates.set_person_scale(
            db_session,
            person.id,
            date(2026, 3, 1),
            13,
            actor=beheerder,
            valid_to=date(2026, 8, 31),
        )


async def test_hire_margin(db_session, rate_cards, beheerder, make_person):
    person = await make_person(14)
    assert await rates.hire_margin(db_session, person.id, Month(2026, 3)) is None
    await rates.add_hire(
        db_session,
        person.id,
        supplier="Leverancier",
        cost_monthly_rate_cents=15_000_00,
        valid_from=date(2026, 1, 1),
        actor=beheerder,
    )

    assert await rates.hire_margin(db_session, person.id, Month(2026, 3)) == (
        18_000_00,
        15_000_00,
        3_000_00,
    )
