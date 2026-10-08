"""Monthly close, reopening and billing data."""

from datetime import date
from decimal import Decimal

import pytest

from grip.calc import AmountSource, Month
from grip.services import assignments, month_close
from grip.services.errors import DomainValidationError, MonthClosedError

JAN = Month(2026, 1)


@pytest.fixture
async def staffed(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await add_personnel_line(assignment, fte="1")
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
        fte_pct=Decimal(80),
        actor=beheerder,
    )
    return assignment, line, allocation, person


async def test_proposal_is_the_planned_inzet(db_session, staffed):
    assignment, _, allocation, _ = staffed
    lines = await month_close.proposal(db_session, assignment.id, JAN)

    assert len(lines) == 1
    assert lines[0].allocation_id == str(allocation.id)
    assert lines[0].fte_pct == Decimal(80)
    assert lines[0].amount_cents == 14_400_00
    assert lines[0].source is AmountSource.PLANNED


async def test_close_establishes_and_billing_data_follows(
    db_session, staffed, beheerder
):
    assignment, _, allocation, person = staffed
    close = await month_close.close_month(
        db_session,
        assignment.id,
        JAN,
        actor=beheerder,
        established={allocation.id: Decimal(60)},
    )
    data = await month_close.billing_data(db_session, assignment.id, JAN)

    assert [
        (line.planned_fte_pct, line.established_fte_pct) for line in close.lines
    ] == [(Decimal(80), Decimal(60))]
    assert data.total_cents == 10_800_00
    assert data.lines[0].source is AmountSource.ACTUAL
    assert data.lines[0].person_id == str(person.id)
    assert data.closed_at == close.closed_at


async def test_billing_data_needs_a_closed_month(db_session, staffed):
    assignment, *_ = staffed
    with pytest.raises(DomainValidationError):
        await month_close.billing_data(db_session, assignment.id, JAN)


async def test_month_cannot_be_closed_twice(db_session, staffed, beheerder):
    assignment, *_ = staffed
    await month_close.close_month(db_session, assignment.id, JAN, actor=beheerder)
    with pytest.raises(DomainValidationError):
        await month_close.close_month(db_session, assignment.id, JAN, actor=beheerder)


async def test_established_for_foreign_allocation_is_refused(
    db_session, staffed, beheerder
):
    import uuid

    assignment, *_ = staffed
    with pytest.raises(DomainValidationError):
        await month_close.close_month(
            db_session,
            assignment.id,
            JAN,
            actor=beheerder,
            established={uuid.uuid4(): Decimal(50)},
        )


async def test_reopen_keeps_the_trail_and_allows_a_new_close(
    db_session, staffed, beheerder
):
    assignment, _, allocation, _ = staffed
    first = await month_close.close_month(
        db_session,
        assignment.id,
        JAN,
        actor=beheerder,
        established={allocation.id: Decimal(60)},
    )
    with pytest.raises(DomainValidationError):
        await month_close.reopen_month(
            db_session, assignment.id, JAN, actor=beheerder, reason=" "
        )
    reopened = await month_close.reopen_month(
        db_session, assignment.id, JAN, actor=beheerder, reason="Ziekte niet verwerkt"
    )
    assert reopened.id == first.id
    assert reopened.reopened_at is not None
    assert reopened.reopen_reason == "Ziekte niet verwerkt"

    second = await month_close.close_month(
        db_session,
        assignment.id,
        JAN,
        actor=beheerder,
        established={allocation.id: Decimal(40)},
    )
    data = await month_close.billing_data(db_session, assignment.id, JAN)

    assert second.id != first.id
    assert data.total_cents == 7_200_00


async def test_allocation_may_not_enter_or_leave_a_closed_month(
    db_session, staffed, beheerder, make_person
):
    assignment, line, allocation, _ = staffed
    await month_close.close_month(db_session, assignment.id, JAN, actor=beheerder)
    other = await make_person(14)

    # Changing the planned percentage or the end is fine.
    await assignments.update_allocation(
        db_session,
        allocation.id,
        fte_pct=Decimal(50),
        end_date=date(2026, 9, 30),
        actor=beheerder,
    )
    with pytest.raises(MonthClosedError):
        await assignments.update_allocation(
            db_session, allocation.id, start_date=date(2026, 2, 1), actor=beheerder
        )
    with pytest.raises(MonthClosedError):
        await assignments.add_allocation(
            db_session,
            line.id,
            other.id,
            start_date=date(2026, 1, 15),
            end_date=date(2026, 3, 31),
            fte_pct=Decimal(50),
            actor=beheerder,
        )
    with pytest.raises(MonthClosedError):
        await assignments.delete_allocation(db_session, allocation.id, actor=beheerder)
    # Starting after the closed month is fine.
    await assignments.add_allocation(
        db_session,
        line.id,
        other.id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 3, 31),
        fte_pct=Decimal(50),
        actor=beheerder,
    )


async def test_billing_export_is_frozen(db_session, staffed, beheerder):
    from grip.services import rates

    assignment, _, allocation, _ = staffed
    await month_close.close_month(db_session, assignment.id, JAN, actor=beheerder)
    export = await month_close.create_billing_export(
        db_session, assignment.id, JAN, actor=beheerder
    )
    assert export.total_cents == 14_400_00

    await rates.set_rate_band(db_session, 2026, "D", 20_000_00, actor=beheerder)
    await db_session.refresh(export, ["lines"])

    assert export.total_cents == 14_400_00
    assert [line.amount_cents for line in export.lines] == [14_400_00]
    assert export.lines[0].description == "Productmanager"
    # The live figure does follow the rate card.
    data = await month_close.billing_data(db_session, assignment.id, JAN)
    assert data.total_cents == 16_000_00
