"""We invoice what it costs us, always at the correct rate.

A promotion halfway through the year, a promotion recorded after the fact,
and a rate card with effect in the past: one rule for "the price of a past
month changed".
"""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from sqlalchemy import select

from grip.calc import Month
from grip.models.month_close import BillingExport
from grip.services import (
    assignments,
    events,
    month_close,
    outgoing_invoices,
    price_changes,
    pricing,
    rate_indexation,
    rates,
)
from grip.services.errors import DomainValidationError

# Scale 11 bills in category B (12,000), scale 12 in category C (15,000).
B, C = 12_000_00, 15_000_00
JULY, AUGUST = Month(2026, 7), Month(2026, 8)


@pytest.fixture
async def work(
    db_session, rate_cards, beheerder, make_person, make_assignment,
    add_personnel_line, accept,
):
    """A person at scale 11 on an assignment all year, on a line budgeted at B."""
    person = await make_person(11)
    assignment = await make_assignment(end_date=date(2026, 12, 31))
    line = await add_personnel_line(assignment, fte="1", category="B")
    allocation = await assignments.add_allocation(
        db_session, line.id, person.id, fte_pct=Decimal(100), actor=beheerder
    )
    await accept(assignment)
    return assignment, line, allocation, person


@pytest.fixture
def seen():
    found = []

    async def record(session, event_type, payload):
        found.append((event_type, payload))

    for event_type in (events.PERSON_SCALE_CHANGED, events.BILLING_CORRECTION_AROSE):
        events.register_handler(event_type, record)
    return found


async def _position(db_session, assignment):
    months = await outgoing_invoices.month_billing(db_session, assignment.id)
    return {str(Month.of(m.month)): m for m in months}


async def test_promoted_from_1_july_and_the_invoices_follow(
    db_session, work, beheerder, seen
):
    """At scale 11 all year, promoted to 12 from 1 July."""
    assignment, line, allocation, person = work
    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 12, actor=beheerder
    )

    # The months price at the rate of the scale valid in each of them.
    overview = await pricing.assignment_overview(db_session, assignment.id)
    assert overview.used_cents == 6 * B + 6 * C
    # The line keeps the category it was budgeted with, and runs over.
    assert line.rate_category == "B"
    assert overview.budgeted_cents == 12 * B
    assert overview.available_cents == -6 * (C - B) and overview.overrun
    # The signal says what it is.
    (difference,) = await pricing.rate_differences(db_session, assignment.id)
    assert difference.cause == "promotion" and difference.since == date(2026, 7, 1)
    assert difference.text == (
        "gepromoveerd per 1 juli 2026: vanaf dan categorie C, de regel is "
        "begroot op B"
    )
    assert difference.generic_text == "tariefwijziging per 1 juli 2026"

    # June closes and delivers at the old rate, July at the new one.
    for month, rate in ((Month(2026, 6), B), (JULY, C)):
        await month_close.close_month(db_session, assignment.id, month, actor=beheerder)
        data = await month_close.billing_data(db_session, assignment.id, month)
        export = await month_close.create_billing_export(
            db_session, assignment.id, month, actor=beheerder
        )
        assert data.total_cents == export.total_cents == rate
        assert data.lines[0].category == ("B" if rate == B else "C")
    # And an invoice recorded for July compares at the new rate.
    await outgoing_invoices.record_invoice(
        db_session, assignment.id, export_ids=[export.id], invoice_number="F-07",
        invoice_date=date(2026, 8, 5), amount_cents=C, actor=beheerder,
        today=date(2026, 8, 5),
    )
    july = (await _position(db_session, assignment))["2026-07"]
    assert (july.delivered_cents, july.invoiced_cents) == (C, C)
    assert july.to_deliver_cents == 0 and july.to_invoice_cents == 0
    # Recorded ahead of time: nothing in the past changed, nothing to correct.
    assert [kind for kind, _ in seen] == [events.PERSON_SCALE_CHANGED]
    assert seen[0][1]["previous_billing_scale"] == 11


async def test_promotion_recorded_afterwards_is_billed_as_a_correction(
    db_session, work, beheerder, seen
):
    """The decision arrives in September, with effect from 1 July."""
    assignment, line, allocation, person = work
    for month in (JULY, AUGUST):
        await month_close.close_month(db_session, assignment.id, month, actor=beheerder)
    original = await month_close.create_billing_export(
        db_session, assignment.id, JULY, actor=beheerder
    )
    await outgoing_invoices.record_invoice(
        db_session, assignment.id, export_ids=[original.id], invoice_number="F-07",
        invoice_date=date(2026, 8, 5), amount_cents=B, actor=beheerder,
        today=date(2026, 8, 5),
    )

    # Before saving: what it touches.
    impact = await rates.scale_change_preview(db_session, person.id, date(2026, 7, 1), 12)
    (touched,) = impact.assignments
    assert touched.assignment_id == assignment.id
    by_month = {str(m.month): m for m in touched.months}
    assert (by_month["2026-07"].state, by_month["2026-07"].invoice_number) == (
        "invoiced", "F-07",
    )
    assert by_month["2026-08"].state == "closed"
    assert by_month["2026-09"].state == "open"
    assert all(m.difference_cents == C - B for m in touched.months)
    assert impact.correction_cents == C - B  # July: to deliver as a correction
    assert impact.closed_difference_cents == C - B  # August: prices right
    assert impact.open_difference_cents == 4 * (C - B)
    assert impact.reaches_into_the_past
    # Nothing was saved, and nothing was announced.
    assert (await pricing.assignment_overview(db_session, assignment.id)).used_cents == 12 * B
    assert seen == []

    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 12, actor=beheerder
    )

    # The delivery of July is a record and stays as it was.
    await db_session.refresh(original, ["lines"])
    assert original.total_cents == B and original.kind == "original"
    assert [line.amount_cents for line in original.lines] == [B]
    # The difference is still to deliver, and the task layer hears of it.
    position = await _position(db_session, assignment)
    assert position["2026-07"].to_deliver_cents == C - B
    arisen = [payload for kind, payload in seen if kind == events.BILLING_CORRECTION_AROSE]
    assert len(arisen) == 1
    assert arisen[0]["month"] == "2026-07"
    assert arisen[0]["difference_cents"] == C - B
    assert arisen[0]["assignment_id"] == str(assignment.id)
    assert "1 juli 2026" in arisen[0]["cause"]
    # August was closed but not delivered: it simply prices right.
    assert position["2026-08"].deliverable_cents == C
    august = await month_close.billing_data(db_session, assignment.id, AUGUST)
    assert august.total_cents == C

    correction = await month_close.create_correction_export(
        db_session, assignment.id, JULY, actor=beheerder,
        reason="Promotie met ingang van 1 juli.",
    )
    await db_session.refresh(correction, ["lines"])
    assert (correction.kind, correction.total_cents) == ("correction", C - B)
    assert correction.reason == "Promotie met ingang van 1 juli."
    (correction_line,) = correction.lines
    assert correction_line.amount_cents == C - B
    assert correction_line.description == "Naverrekening 2026-07: Productmanager"
    assert correction_line.category == "C"
    # Delivered now, and to invoice until an invoice is recorded on it.
    july = (await _position(db_session, assignment))["2026-07"]
    assert july.delivered_cents == C and july.to_deliver_cents == 0
    assert (july.invoiced_cents, july.to_invoice_cents) == (B, C - B)
    with pytest.raises(DomainValidationError, match="niets na te verrekenen"):
        await month_close.create_correction_export(
            db_session, assignment.id, JULY, actor=beheerder
        )
    await outgoing_invoices.record_invoice(
        db_session, assignment.id, export_ids=[correction.id], invoice_number="F-07a",
        invoice_date=date(2026, 9, 20), amount_cents=C - B, actor=beheerder,
        today=date(2026, 9, 20),
    )
    july = (await _position(db_session, assignment))["2026-07"]
    assert (july.invoiced_cents, july.to_invoice_cents) == (C, 0)
    whole = await outgoing_invoices.billing_position(db_session, assignment.id)
    assert whole.delivered_cents == C and whole.invoiced_cents == C


async def test_a_scale_recorded_too_high_is_corrected_down(
    db_session, work, beheerder, seen
):
    assignment, _, _, person = work
    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 14, actor=beheerder
    )  # by mistake: category D
    await month_close.close_month(db_session, assignment.id, JULY, actor=beheerder)
    original = await month_close.create_billing_export(
        db_session, assignment.id, JULY, actor=beheerder
    )
    assert original.total_cents == 18_000_00
    seen.clear()

    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 12, actor=beheerder
    )  # the same start: corrected in place

    arisen = [p for kind, p in seen if kind == events.BILLING_CORRECTION_AROSE]
    assert [p["difference_cents"] for p in arisen] == [C - 18_000_00]
    correction = await month_close.create_correction_export(
        db_session, assignment.id, JULY, actor=beheerder
    )
    assert correction.total_cents == -3_000_00
    july = (await _position(db_session, assignment))["2026-07"]
    assert (july.delivered_cents, july.to_deliver_cents) == (C, 0)
    exports = (
        await db_session.execute(
            select(BillingExport.kind, BillingExport.total_cents).order_by(
                BillingExport.created_at
            )
        )
    ).all()
    assert [tuple(row) for row in exports] == [
        ("original", 18_000_00), ("correction", -3_000_00),
    ]


async def test_promotion_on_the_15th_prices_and_delivers_by_day(
    db_session, work, beheerder
):
    assignment, _, allocation, person = work
    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 15), 12, actor=beheerder
    )
    july_exact = Fraction(14, 31) * B + Fraction(17, 31) * C
    overview = await pricing.assignment_overview(db_session, assignment.id)
    assert overview.used_cents == 6 * B + round(july_exact) + 5 * C

    # The established percentage of a closed month applies to each stretch.
    await month_close.close_month(
        db_session, assignment.id, JULY, actor=beheerder,
        established={allocation.id: Decimal(80)},
    )
    data = await month_close.billing_data(db_session, assignment.id, JULY)
    assert data.total_cents == round(Fraction(8, 10) * july_exact)
    (difference,) = await pricing.rate_differences(db_session, assignment.id)
    assert difference.text.startswith("gepromoveerd per 15 juli 2026")
    # June, with no change inside it, is what it always was.
    await month_close.close_month(
        db_session, assignment.id, Month(2026, 6), actor=beheerder
    )
    june = await month_close.billing_data(db_session, assignment.id, Month(2026, 6))
    assert june.total_cents == B


async def test_rate_card_with_effect_in_the_past_follows_the_same_rule(
    db_session, work, beheerder, seen
):
    assignment, *_ = work
    for month in (JULY, AUGUST):
        await month_close.close_month(db_session, assignment.id, month, actor=beheerder)
    original = await month_close.create_billing_export(
        db_session, assignment.id, JULY, actor=beheerder
    )
    card = await rate_indexation.create_indexed_card(
        db_session, valid_from=date(2026, 7, 1), valid_to=date(2026, 12, 31),
        increase_pct=Decimal("5"), rounding="euro", actor=beheerder,
    )
    card_id = card.id
    more = 600_00  # 5 percent of 12,000

    _, shortened, impact = await rates.activation_preview(db_session, card_id)
    assert shortened["new_valid_to"] == date(2026, 6, 30)
    assert impact.correction_cents == more  # July was delivered
    assert impact.closed_difference_cents == more  # August was only closed
    assert impact.open_difference_cents == 4 * more
    assert impact.reaches_into_the_past and seen == []

    await rates.set_rate_card_status(db_session, card_id, "active", actor=beheerder)

    await db_session.refresh(original)
    assert original.total_cents == B
    position = await _position(db_session, assignment)
    assert position["2026-07"].to_deliver_cents == more
    assert position["2026-08"].deliverable_cents == B + more
    arisen = [p for kind, p in seen if kind == events.BILLING_CORRECTION_AROSE]
    assert [(p["month"], p["difference_cents"]) for p in arisen] == [("2026-07", more)]
    assert "Tarieven vanaf 1 juli 2026" in arisen[0]["cause"]
    correction = await month_close.create_correction_export(
        db_session, assignment.id, JULY, actor=beheerder
    )
    assert correction.total_cents == more
    assert await price_changes.pending_corrections(db_session) == {}


async def test_any_date_is_accepted_for_a_scale(db_session, rate_cards, beheerder, make_person):
    from grip.repositories.domain import PersonDetailRepository

    person = await make_person(11)
    await rates.set_person_scale(db_session, person.id, date(2026, 9, 1), 13, actor=beheerder)
    # Recorded afterwards, for a day inside the first period: that period is
    # cut, and the new one runs until the next.
    await rates.set_person_scale(db_session, person.id, date(2026, 3, 17), 12, actor=beheerder)
    scales = await PersonDetailRepository(db_session).scales([person.id])
    assert [(s.valid_from, s.valid_to, s.billing_scale) for s in scales] == [
        (date(2026, 1, 1), date(2026, 3, 16), 11),
        (date(2026, 3, 17), date(2026, 8, 31), 12),
        (date(2026, 9, 1), None, 13),
    ]
    with pytest.raises(DomainValidationError, match="overlapt"):
        await rates.set_person_scale(
            db_session, person.id, date(2026, 5, 1), 12, actor=beheerder,
            valid_to=date(2026, 10, 31),
        )
    # The refusal changed nothing.
    scales = await PersonDetailRepository(db_session).scales([person.id])
    assert scales[1].valid_to == date(2026, 8, 31)
