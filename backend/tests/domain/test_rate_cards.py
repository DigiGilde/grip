"""Rate cards valid from a date to a date, and starting one halfway."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from sqlalchemy import select

from grip import calc
from grip.models.audit_log import AuditLog
from grip.repositories.domain import RateRepository
from grip.services import assignments, pricing, quotes, rate_indexation, rates
from grip.services.errors import ClosedYearError, DomainValidationError

MID = date(2026, 7, 15)


async def _staffed(
    db_session, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)  # category D
    assignment = await make_assignment(end_date=date(2026, 12, 31))
    line = await add_personnel_line(assignment, fte="1")
    allocation = await assignments.add_allocation(
        db_session, line.id, person.id, fte_pct=Decimal(100), actor=beheerder
    )
    return assignment, line, allocation, person


async def _new_card(db_session, beheerder, **kwargs):
    kwargs.setdefault("valid_to", date(2026, 12, 31))
    return await rate_indexation.create_indexed_card(
        db_session,
        valid_from=MID,
        increase_pct=Decimal("4"),
        rounding="ten",
        actor=beheerder,
        **kwargs,
    )


async def test_year_cards_are_cards_with_a_validity(db_session, rate_cards):
    cards = await RateRepository(db_session).all_cards()
    assert [(c.name, c.valid_from, c.valid_to, c.status) for c in cards] == [
        ("Tarieven 2026", date(2026, 1, 1), date(2026, 12, 31), "active"),
        ("Tarieven 2027", date(2027, 1, 1), date(2027, 12, 31), "active"),
    ]
    assert (await rates.get_card(db_session, 2026)).id == cards[0].id
    assert (await rates.get_card(db_session, cards[1].id)).year == 2027


async def test_new_card_halfway_is_an_indexed_draft_that_prices_nothing(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    assignment, *_ = await _staffed(
        db_session, beheerder, make_person, make_assignment, add_personnel_line
    )
    before = await pricing.assignment_overview(db_session, assignment.id)

    card = await _new_card(db_session, beheerder)

    assert (card.name, card.status) == ("Tarieven vanaf 15 juli 2026", "draft")
    assert (card.valid_from, card.valid_to) == (MID, date(2026, 12, 31))
    # 18,000 plus 4 percent, rounded to tens; the scale mapping is copied.
    assert {b.category: b.monthly_rate_cents for b in card.rate_bands}["D"] == 18_720_00
    assert len(card.scale_bands) == 10
    after = await pricing.assignment_overview(db_session, assignment.id)
    assert after.budgeted_cents == before.budgeted_cents
    assert after.used_cents == before.used_cents
    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "rate_card", AuditLog.entity_id == str(card.id)
            )
        )
    ).scalar_one()
    assert row.new_value["copied_from_name"] == "Tarieven 2026"
    assert row.new_value["increase_pct"] == "4"
    assert row.new_value["valid_from"] == "2026-07-15"
    with pytest.raises(DomainValidationError, match="Er is al een tarievenkaart"):
        await _new_card(db_session, beheerder)


async def test_preview_shows_what_activating_does_and_saves_nothing(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    assignment, line, *_ = await _staffed(
        db_session, beheerder, make_person, make_assignment, add_personnel_line
    )
    card = await _new_card(db_session, beheerder)
    card_id = card.id

    found, shortened, impact = await rates.activation_preview(db_session, card_id)

    assert found.status == "draft"
    assert shortened == {
        "id": (await rates.get_card(db_session, 2026)).id,
        "name": "Tarieven 2026",
        "old_valid_to": date(2026, 12, 31),
        "new_valid_to": date(2026, 7, 14),
    }
    # 17 days of July and five months at 720 more per month.
    extra = round(Fraction(17, 31) * 720_00) + 5 * 720_00
    assert impact.budget_lines_changed == 1
    assert impact.budget_difference_cents == extra
    assert impact.allocations_changed == 1
    assert impact.open_difference_cents == extra
    assert impact.correction_cents == 0 and impact.closed_difference_cents == 0
    assert not impact.reaches_into_the_past
    (touched,) = impact.assignments
    assert touched.assignment_id == assignment.id
    assert [str(m.month) for m in touched.months] == [
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
    ]
    # Nothing was saved.
    assert (await rates.get_card(db_session, card_id)).status == "draft"
    assert (await rates.get_card(db_session, 2026)).valid_to == date(2026, 12, 31)
    overview = await pricing.assignment_overview(db_session, assignment.id)
    assert overview.budgeted_cents == 12 * 18_000_00


async def test_activating_ends_the_previous_card_and_reprices_by_day(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    assignment, line, allocation, _ = await _staffed(
        db_session, beheerder, make_person, make_assignment, add_personnel_line
    )
    quote = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    issued = bytes(quote.canonical)
    card = await _new_card(db_session, beheerder)

    await rates.set_rate_card_status(db_session, card.id, "active", actor=beheerder)

    old = await rates.get_card(db_session, 2026)
    assert (old.valid_to, old.status) == (date(2026, 7, 14), "active")
    rows = list(
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "rate_card", AuditLog.action == "update"
                )
            )
        ).scalars()
    )
    activation = [r for r in rows if (r.new_value or {}).get("shortened")]
    assert len(activation) == 1 and activation[0].entity_id == str(card.id)
    assert activation[0].new_value["shortened"] == {
        "id": str(old.id),
        "name": "Tarieven 2026",
        "old_valid_to": "2026-12-31",
        "new_valid_to": "2026-07-14",
    }
    # The budget and the inzet reprice from 15 July, by day.
    july = round(Fraction(14, 31) * 18_000_00 + Fraction(17, 31) * 18_720_00)
    expected = 6 * 18_000_00 + july + 5 * 18_720_00
    overview = await pricing.assignment_overview(db_session, assignment.id)
    assert overview.budgeted_cents == expected
    assert overview.used_cents == expected
    # The issued quote keeps the rates it was issued with.
    assert bytes(quote.canonical) == issued and quote.total_cents == 12 * 18_000_00
    # A quote issued now carries the rates per period of validity.
    (new_line,) = (await quotes.build_snapshot(db_session, assignment))["lines"]
    assert new_line["monthly_rate_periods"] == [
        {
            "start_date": "2026-01-01",
            "end_date": "2026-07-14",
            "monthly_rate": {"amount_cents": 18_000_00, "currency": "EUR"},
        },
        {
            "start_date": "2026-07-15",
            "end_date": "2026-12-31",
            "monthly_rate": {"amount_cents": 18_720_00, "currency": "EUR"},
        },
    ]
    assert new_line["amount"]["amount_cents"] == expected


async def test_cards_that_price_never_overlap(db_session, rate_cards, beheerder):
    # Open-ended from 15 July 2026 would run into the card of 2027.
    card = await _new_card(db_session, beheerder, valid_to=None)
    with pytest.raises(DomainValidationError, match="uiterlijk 31 december 2026"):
        await rates.set_rate_card_status(db_session, card.id, "active", actor=beheerder)
    assert (await rates.get_card(db_session, 2026)).valid_to == date(2026, 12, 31)

    await rates.update_card(
        db_session, card.id, actor=beheerder, valid_to=date(2026, 12, 31)
    )
    await rates.set_rate_card_status(db_session, card.id, "active", actor=beheerder)
    assert [
        (c.name, c.valid_from, c.valid_to)
        for c in await RateRepository(db_session).pricing_cards()
    ] == [
        ("Tarieven 2026", date(2026, 1, 1), date(2026, 7, 14)),
        ("Tarieven vanaf 15 juli 2026", MID, date(2026, 12, 31)),
        ("Tarieven 2027", date(2027, 1, 1), date(2027, 12, 31)),
    ]


async def test_shortening_a_closed_card_needs_the_override(
    db_session, rate_cards, beheerder
):
    await rates.set_rate_card_status(db_session, 2026, "closed", actor=beheerder)
    card = await _new_card(db_session, beheerder)
    with pytest.raises(ClosedYearError, match="Tarieven 2026"):
        await rates.set_rate_card_status(db_session, card.id, "active", actor=beheerder)
    await rates.set_rate_card_status(
        db_session, card.id, "active", actor=beheerder, allow_closed_year=True
    )
    assert (await rates.get_card(db_session, 2026)).valid_to == date(2026, 7, 14)


async def test_closed_card_locks_its_own_period_only(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    card = await _new_card(db_session, beheerder)
    await rates.set_rate_card_status(db_session, card.id, "active", actor=beheerder)
    await rates.set_rate_card_status(db_session, 2026, "closed", actor=beheerder)
    assignment = await make_assignment(end_date=date(2026, 12, 31))

    # Up to 14 July the closed card prices: locked.
    with pytest.raises(ClosedYearError, match="Tarieven 2026"):
        await add_personnel_line(
            assignment, start=date(2026, 3, 1), end=date(2026, 5, 31)
        )
    # From 15 July another card prices: free.
    await add_personnel_line(assignment, start=date(2026, 8, 1), end=date(2026, 10, 31))
    with pytest.raises(ClosedYearError):
        await rates.set_rate_band(db_session, 2026, "D", 1, actor=beheerder)


async def test_gap_between_cards_is_reported_and_never_priced(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    await rates.update_card(
        db_session, 2026, actor=beheerder, valid_to=date(2026, 10, 31)
    )
    stretches = await rates.valid_rates(
        db_session, date(2026, 10, 1), date(2027, 1, 31)
    )
    assert [
        (s.start_date, s.end_date, s.card.name if s.card else None) for s in stretches
    ] == [
        (date(2026, 10, 1), date(2026, 10, 31), "Tarieven 2026"),
        (date(2026, 11, 1), date(2026, 12, 31), None),
        (date(2027, 1, 1), date(2027, 1, 31), "Tarieven 2027"),
    ]
    assert "geen tarievenkaart" in rates.valid_rates_summary(stretches)
    assignment = await make_assignment(end_date=date(2026, 12, 31))
    await add_personnel_line(assignment)
    with pytest.raises(calc.MissingRateCardError) as error:
        await pricing.assignment_overview(db_session, assignment.id)
    assert error.value.day == date(2026, 11, 1)


async def test_valid_rates_for_a_form(db_session, rate_cards, beheerder):
    one = await rates.valid_rates(db_session, date(2026, 3, 1), date(2026, 9, 30))
    assert rates.valid_rates_summary(one) == (
        "Volgens Tarieven 2026, geldig t/m 31 december 2026."
    )
    assert not rates.rates_differ(one)
    two = await rates.valid_rates(db_session, date(2026, 7, 1), date(2027, 6, 30))
    assert rates.rates_differ(two)
    assert rates.valid_rates_summary(two) == (
        "Volgens Tarieven 2026, geldig t/m 31 december 2026. Vanaf 1 januari 2027 "
        "geldt Tarieven 2027 met andere tarieven; de periode wordt per dag geprijsd."
    )
    with pytest.raises(DomainValidationError):
        await rates.valid_rates(db_session, date(2026, 3, 1), date(2026, 1, 1))


async def test_any_date_is_accepted_for_a_card(db_session, beheerder):
    card = await rates.create_card(
        db_session,
        valid_from=date(2030, 5, 17),
        valid_to=date(2030, 11, 3),
        actor=beheerder,
    )
    assert card.name == "Tarieven vanaf 17 mei 2030"
    with pytest.raises(DomainValidationError, match="einddatum"):
        await rates.create_card(
            db_session,
            valid_from=date(2031, 5, 17),
            valid_to=date(2031, 1, 1),
            actor=beheerder,
        )


async def test_a_card_after_a_draft_builds_on_that_draft(
    db_session, rate_cards, beheerder
):
    """Two years ahead: the second new card continues from the first, which is
    still a draft, and not from the last card that is in force."""
    first = await rate_indexation.create_indexed_card(
        db_session,
        valid_from=date(2028, 1, 1),
        valid_to=date(2028, 12, 31),
        increase_pct=Decimal("10"),
        rounding="euro",
        actor=beheerder,
    )
    assert first.status == "draft"
    base = await rates.previous_card(db_session, date(2029, 1, 1))
    assert base is not None and base.id == first.id
    second = await rate_indexation.create_indexed_card(
        db_session,
        valid_from=date(2029, 1, 1),
        increase_pct=Decimal("0"),
        rounding="euro",
        actor=beheerder,
    )
    rate = {b.category: b.monthly_rate_cents for b in second.rate_bands}
    assert rate == {b.category: b.monthly_rate_cents for b in first.rate_bands}
