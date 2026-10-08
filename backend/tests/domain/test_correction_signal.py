"""A delivered month that costs something else now is said, with its cause."""

from datetime import date
from decimal import Decimal

from grip.calc import Month
from grip.services import assignments, month_close, pricing, rates
from grip.services.overview_attention import correction_due

# Scale 11 bills in category B (12,000), scale 12 in category C (15,000).
B, C = 12_000_00, 15_000_00


async def test_promotion_recorded_afterwards_is_a_correction_with_its_cause(
    db_session,
    rate_cards,
    beheerder,
    make_person,
    make_assignment,
    add_personnel_line,
    accept,
):
    person = await make_person(11)
    assignment = await make_assignment(end_date=date(2026, 12, 31))
    line = await add_personnel_line(assignment, fte="1", category="B")
    await assignments.add_allocation(
        db_session, line.id, person.id, fte_pct=Decimal(100), actor=beheerder
    )
    await accept(assignment)
    for month in (Month(2026, 7), Month(2026, 8)):
        await month_close.close_month(db_session, assignment.id, month, actor=beheerder)
        await month_close.create_billing_export(
            db_session, assignment.id, month, actor=beheerder
        )

    async def due():
        differences = await pricing.rate_differences(db_session, assignment.id)
        return await correction_due(db_session, assignment.id, differences)

    assert await due() is None

    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 12, actor=beheerder
    )
    correction = await due()
    assert correction is not None
    assert correction.months == (date(2026, 7, 1), date(2026, 8, 1))
    assert correction.amount_cents == 2 * (C - B)
    assert correction.cause == "een schaalwijziging"
