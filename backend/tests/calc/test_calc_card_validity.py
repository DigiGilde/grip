"""Rate cards with a validity: a month is priced by the card valid in it."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from grip.calc import (
    Allocation,
    BillabilityTarget,
    BudgetLine,
    BudgetLineKind,
    InvalidInputError,
    MissingRateCardError,
    Month,
    PartialMonths,
    PersonScale,
    RateBand,
    RateBook,
    RateCard,
    RateCardStatus,
    ScaleBand,
    allocation_amount,
    allocation_months,
    budget_line_months,
    budgeted,
    budgeted_by_year,
    category_mismatches,
    kpi_realisation,
    kpi_target,
    person_monthly_rate,
    rate_category,
)

EUR = 100
SCALES = {12: "C", 13: "C", 14: "D", 15: "D"}


def card(start, end, rates, *, scales=SCALES, status=RateCardStatus.ACTIVE, name=""):
    return RateCard(
        valid_from=start,
        valid_to=end,
        status=status,
        rate_bands=tuple(RateBand(c, r * EUR) for c, r in rates.items()),
        scale_bands=tuple(ScaleBand(s, c) for s, c in scales.items()),
        name=name,
    )


FIRST_HALF = card(date(2026, 1, 1), date(2026, 6, 30), {"C": 15_000, "D": 18_000})
FROM_JULY = card(date(2026, 7, 1), None, {"C": 15_600, "D": 19_000})
BOOK = RateBook(cards=(FIRST_HALF, FROM_JULY))
PERSON = (PersonScale("p", date(2025, 1, 1), 14),)


def allocation(start, end, pct=100):
    return Allocation(
        id="a",
        person_id="p",
        budget_line_id="line",
        start_date=start,
        end_date=end,
        fte_pct=Decimal(pct),
    )


def line(start, end, fte="1", category="D"):
    return BudgetLine(
        id="line",
        assignment_id="x",
        kind=BudgetLineKind.PERSONNEL,
        fte=Decimal(fte),
        rate_category=category,
        start_date=start,
        end_date=end,
    )


def test_card_change_on_1_july_inside_an_allocation():
    alloc = allocation(date(2026, 1, 1), date(2026, 12, 31))
    months = allocation_months(alloc, BOOK, PERSON)

    assert [m.monthly_rate_cents for m in months] == [18_000 * EUR] * 6 + [
        19_000 * EUR
    ] * 6
    assert allocation_amount(alloc, BOOK, PERSON) == (6 * 18_000 + 6 * 19_000) * EUR
    # Subtotals stay per calendar year: a way of presenting, not of pricing.
    assert allocation_amount(alloc, BOOK, PERSON, year=2026) == 222_000 * EUR
    assert person_monthly_rate(BOOK, PERSON, "p", Month(2026, 6)) == 18_000 * EUR
    assert person_monthly_rate(BOOK, PERSON, "p", Month(2026, 7)) == 19_000 * EUR


def test_budget_line_over_two_cards_in_one_year():
    budget = line(date(2026, 4, 1), date(2026, 9, 30), fte="0.5")
    assert budgeted(budget, BOOK) == (3 * 9_000 + 3 * 9_500) * EUR
    assert budgeted_by_year(budget, BOOK) == {2026: 55_500 * EUR}


def test_open_ended_card_prices_every_later_month():
    alloc = allocation(date(2027, 11, 1), date(2031, 2, 28), pct=50)
    months = allocation_months(alloc, BOOK, PERSON)
    assert len(months) == 40
    assert {m.monthly_rate_cents for m in months} == {19_000 * EUR}
    assert BOOK.card(Month(2099, 12)) is FROM_JULY


def test_scale_mapping_that_differs_between_two_cards_in_one_year():
    moved = card(date(2026, 7, 1), None, {"C": 15_600, "D": 19_000}, scales={14: "C"})
    book = RateBook(cards=(FIRST_HALF, moved))

    assert rate_category(book, PERSON, "p", Month(2026, 6)) == "D"
    assert rate_category(book, PERSON, "p", Month(2026, 7)) == "C"
    alloc = allocation(date(2026, 1, 1), date(2026, 12, 31))
    assert allocation_amount(alloc, book, PERSON) == (6 * 18_000 + 6 * 15_600) * EUR
    # R14 follows: from July the person bills below what the line assumes.
    (mismatch,) = category_mismatches(
        line(date(2026, 1, 1), date(2026, 12, 31)), [alloc], book, PERSON
    )
    assert (str(mismatch.first_month), str(mismatch.last_month)) == (
        "2026-07",
        "2026-12",
    )
    assert (mismatch.line_category, mismatch.person_category) == ("D", "C")


def test_gap_between_cards_is_an_error_never_zero():
    later = card(date(2026, 9, 1), None, {"D": 19_000})
    book = RateBook(cards=(FIRST_HALF, later))

    assert person_monthly_rate(book, PERSON, "p", Month(2026, 6)) == 18_000 * EUR
    assert person_monthly_rate(book, PERSON, "p", Month(2026, 9)) == 19_000 * EUR
    for month in (Month(2026, 7), Month(2026, 8)):
        with pytest.raises(MissingRateCardError) as error:
            person_monthly_rate(book, PERSON, "p", month)
        assert error.value.month == month and error.value.year == 2026
    with pytest.raises(MissingRateCardError):
        allocation_amount(
            allocation(date(2026, 1, 1), date(2026, 12, 31)), book, PERSON
        )
    with pytest.raises(MissingRateCardError):
        budgeted(line(date(2026, 6, 1), date(2026, 7, 31)), book)
    # Before the first card there is nothing either.
    with pytest.raises(MissingRateCardError):
        person_monthly_rate(BOOK, PERSON, "p", Month(2025, 12))


def test_kpi_target_and_realisation_over_a_year_with_two_cards():
    target = BillabilityTarget(person_id="p", year=2026, target_pct=Decimal(90))
    # The target stays a yearly agreement; the amount sums the monthly rates.
    assert (
        kpi_target(target, BOOK, PERSON) == round(0.9 * (6 * 18_000 + 6 * 19_000)) * EUR
    )
    alloc = allocation(date(2026, 1, 1), date(2026, 12, 31), pct=80)
    assert (
        kpi_realisation("p", 2026, [alloc], BOOK, PERSON)
        == round(0.8 * (6 * 18_000 + 6 * 19_000)) * EUR
    )


def test_draft_does_not_price_and_never_wins_over_an_active_card():
    draft = card(date(2026, 10, 1), None, {"D": 25_000}, status=RateCardStatus.DRAFT)
    book = RateBook(cards=(FIRST_HALF, FROM_JULY, draft))
    assert person_monthly_rate(book, PERSON, "p", Month(2026, 11)) == 19_000 * EUR
    with_draft = RateBook(cards=(FIRST_HALF, FROM_JULY, draft), include_draft=True)
    assert person_monthly_rate(with_draft, PERSON, "p", Month(2026, 11)) == 19_000 * EUR
    only_draft = RateBook(cards=(FIRST_HALF, draft), include_draft=True)
    assert person_monthly_rate(only_draft, PERSON, "p", Month(2026, 11)) == 25_000 * EUR
    with pytest.raises(MissingRateCardError):
        person_monthly_rate(
            RateBook(cards=(FIRST_HALF, draft)), PERSON, "p", Month(2026, 11)
        )


def test_a_card_can_start_and_end_on_any_day():
    mid = card(date(2026, 7, 15), date(2026, 12, 15), {"D": 1})
    assert mid.valid_on(date(2026, 7, 15)) and not mid.valid_on(date(2026, 7, 14))
    assert mid.valid_on(date(2026, 12, 15)) and not mid.valid_on(date(2026, 12, 16))
    with pytest.raises(InvalidInputError):
        card(date(2026, 7, 1), date(2026, 5, 31), {"D": 1})


# -- by day: a change inside a month ------------------------------------------------

UNTIL_14_JULY = card(date(2026, 1, 1), date(2026, 7, 14), {"C": 15_000, "D": 18_000})
FROM_15_JULY = card(date(2026, 7, 15), None, {"C": 15_600, "D": 19_000})
MID_BOOK = RateBook(cards=(UNTIL_14_JULY, FROM_15_JULY))


def test_new_card_on_the_15th_inside_an_allocation():
    alloc = allocation(date(2026, 1, 1), date(2026, 12, 31))
    months = {str(m.month): m for m in allocation_months(alloc, MID_BOOK, PERSON)}

    july = months["2026-07"]
    assert [(s.start, s.end, s.monthly_rate_cents) for s in july.stretches] == [
        (date(2026, 7, 1), date(2026, 7, 14), 18_000 * EUR),
        (date(2026, 7, 15), date(2026, 7, 31), 19_000 * EUR),
    ]
    assert sum(s.fraction for s in july.stretches) == 1
    # 14 days at the old rate and 17 at the new, of a month of 31.
    exact = Fraction(14, 31) * 18_000 * EUR + Fraction(17, 31) * 19_000 * EUR
    assert july.exact == exact
    assert july.cents == 1_854_839  # rounded once, for the month
    assert july.changes_inside
    # The months around it are whole months at one rate, as always.
    assert months["2026-06"].cents == 18_000 * EUR
    assert months["2026-08"].cents == 19_000 * EUR
    assert not months["2026-06"].changes_inside


def test_promotion_on_the_15th_inside_an_allocation():
    promoted = (
        PersonScale("p", date(2025, 1, 1), 12, valid_to=date(2026, 7, 14)),
        PersonScale("p", date(2026, 7, 15), 14),
    )
    alloc = allocation(date(2026, 7, 1), date(2026, 7, 31), pct=80)
    (july,) = allocation_months(alloc, BOOK, promoted)

    assert [(s.category, s.start) for s in july.stretches] == [
        ("C", date(2026, 7, 1)),
        ("D", date(2026, 7, 15)),
    ]
    exact = Fraction(8, 10) * (
        Fraction(14, 31) * 15_600 * EUR + Fraction(17, 31) * 19_000 * EUR
    )
    assert july.exact == exact and july.cents == round(exact)
    # R14 dates the difference from the day of the promotion.
    (mismatch,) = category_mismatches(
        line(date(2026, 7, 1), date(2026, 7, 31), category="C"), [alloc], BOOK, promoted
    )
    assert mismatch.since == date(2026, 7, 15)
    assert (mismatch.line_category, mismatch.person_category) == ("C", "D")


def test_promotion_and_new_card_in_the_same_month():
    promoted = (
        PersonScale("p", date(2025, 1, 1), 12, valid_to=date(2026, 7, 9)),
        PersonScale("p", date(2026, 7, 10), 14),
    )
    alloc = allocation(date(2026, 7, 1), date(2026, 7, 31))
    (july,) = allocation_months(alloc, MID_BOOK, promoted)

    assert [
        (s.start, s.end, s.category, s.monthly_rate_cents) for s in july.stretches
    ] == [
        (date(2026, 7, 1), date(2026, 7, 9), "C", 15_000 * EUR),
        (date(2026, 7, 10), date(2026, 7, 14), "D", 18_000 * EUR),
        (date(2026, 7, 15), date(2026, 7, 31), "D", 19_000 * EUR),
    ]
    exact = (
        Fraction(9, 31) * 15_000 + Fraction(5, 31) * 18_000 + Fraction(17, 31) * 19_000
    ) * EUR
    assert july.exact == exact
    assert sum(s.exact for s in july.stretches) == july.exact
    assert july.cents == round(exact)


def test_an_unchanged_month_is_priced_exactly_as_before():
    """The invariant: no change inside a month, no change in its amount."""
    alloc = allocation(date(2026, 3, 16), date(2026, 9, 20), pct=Decimal("37.5"))
    for month in allocation_months(alloc, MID_BOOK, PERSON):
        if month.month == Month(2026, 7):
            continue
        # One stretch, with the month fraction and the formula of R2 itself.
        (only,) = month.stretches
        assert only.fraction == month.fraction
        assert month.exact == (
            Fraction("37.5") / 100 * month.monthly_rate_cents * month.fraction
        )
    # A book whose cards change on month boundaries gives what a book with
    # year cards gives for the same rates.
    yearly = RateBook(
        cards=(
            RateCard.for_year(
                2026,
                RateCardStatus.ACTIVE,
                FIRST_HALF.rate_bands,
                FIRST_HALF.scale_bands,
            ),
        )
    )
    split = RateBook(
        cards=(
            FIRST_HALF,
            card(date(2026, 7, 1), date(2026, 12, 31), {"C": 15_000, "D": 18_000}),
        )
    )
    assert [m.cents for m in allocation_months(alloc, yearly, PERSON)] == [
        m.cents for m in allocation_months(alloc, split, PERSON)
    ]


def test_established_percentage_applies_to_each_stretch_alike():
    alloc = allocation(date(2026, 7, 1), date(2026, 7, 31), pct=100)
    (july,) = allocation_months(
        alloc, MID_BOOK, PERSON, actuals={("a", Month(2026, 7)): Decimal(60)}
    )
    assert july.fraction == 1 and july.fte_pct == Decimal(60)
    exact = Fraction(6, 10) * (
        Fraction(14, 31) * 18_000 * EUR + Fraction(17, 31) * 19_000 * EUR
    )
    assert july.exact == exact and july.cents == round(exact)


def test_budget_line_across_a_card_change_inside_a_month():
    budget = line(date(2026, 7, 1), date(2026, 7, 31), fte="0.5")
    (july,) = budget_line_months(budget, MID_BOOK)
    assert {s.category for s in july.stretches} == {"D"}  # one category
    exact = Fraction(1, 2) * (
        Fraction(14, 31) * 18_000 * EUR + Fraction(17, 31) * 19_000 * EUR
    )
    assert july.exact == exact
    assert budgeted(budget, MID_BOOK) == round(exact)


def test_kpi_target_by_day_inside_a_month_with_a_change():
    target = BillabilityTarget(person_id="p", year=2026, target_pct=Decimal(100))
    year_rate = (
        6 * 18_000 + Fraction(14, 31) * 18_000 + Fraction(17, 31) * 19_000 + 5 * 19_000
    ) * EUR
    assert kpi_target(target, MID_BOOK, PERSON) == round(year_rate)


def test_gap_by_day_inside_a_month():
    later = card(date(2026, 7, 20), None, {"D": 19_000})
    book = RateBook(cards=(UNTIL_14_JULY, later))
    with pytest.raises(MissingRateCardError) as error:
        allocation_months(allocation(date(2026, 7, 1), date(2026, 7, 31)), book, PERSON)
    assert error.value.day == date(2026, 7, 15)
    # Inzet that stays out of the gap prices.
    assert (
        allocation_amount(allocation(date(2026, 7, 1), date(2026, 7, 14)), book, PERSON)
        > 0
    )


def test_whole_month_strategy_spreads_a_month_over_its_stretches():
    # For reconciling with Grist a touched month counts fully; a change
    # inside it still splits by the days of the inzet.
    alloc = allocation(date(2026, 7, 11), date(2026, 7, 20))
    (july,) = allocation_months(
        alloc, MID_BOOK, PERSON, partial_months=PartialMonths.WHOLE_MONTHS
    )
    assert july.fraction == 1
    assert [s.fraction for s in july.stretches] == [Fraction(4, 10), Fraction(6, 10)]


def test_partial_month_at_a_card_boundary():
    # 16 June to 15 July: half of June at the old rate, half of July at the new.
    alloc = allocation(date(2026, 6, 16), date(2026, 7, 15))
    june, july = allocation_months(alloc, BOOK, PERSON)
    assert (june.monthly_rate_cents, july.monthly_rate_cents) == (
        18_000 * EUR,
        19_000 * EUR,
    )
    assert june.cents == 9_000 * EUR
    assert july.cents == round(19_000 * EUR * 15 / 31)


def test_a_bare_year_still_finds_the_card_of_january():
    # Callers from before cards had a validity ask per year.
    assert BOOK.card(2026) is FIRST_HALF
    assert BOOK.monthly_rate_cents(2027, "D") == 19_000 * EUR
    with pytest.raises(MissingRateCardError) as error:
        BOOK.card(2025)
    assert error.value.year == 2025
