"""Unit tests for months and month fractions."""

from datetime import date
from fractions import Fraction

import pytest

from grip.calc import (
    Month,
    PartialMonths,
    datedif_months,
    month_fractions,
    months_between,
    months_of_year,
)


def test_month_basics():
    feb = Month(2028, 2)
    assert feb.days == 29
    assert (feb.first_day, feb.last_day) == (date(2028, 2, 1), date(2028, 2, 29))
    assert Month(2026, 12).next() == Month(2027, 1)
    assert Month.of(date(2026, 7, 15)) == Month(2026, 7)
    assert str(Month(2026, 7)) == "2026-07"
    assert Month(2026, 12) < Month(2027, 1)
    assert len(months_of_year(2026)) == 12
    with pytest.raises(ValueError):
        Month(2026, 13)


def test_months_between_is_inclusive_and_crosses_years():
    months = months_between(date(2026, 11, 30), date(2027, 2, 1))
    assert months == (Month(2026, 11), Month(2026, 12), Month(2027, 1), Month(2027, 2))
    with pytest.raises(ValueError):
        months_between(date(2026, 2, 1), date(2026, 1, 1))


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 1, 1), date(2026, 12, 31), 11),
        (date(2026, 1, 16), date(2026, 3, 10), 1),
        (date(2026, 1, 16), date(2026, 3, 16), 2),
        (date(2026, 1, 31), date(2026, 2, 28), 0),
        (date(2026, 7, 1), date(2027, 6, 30), 11),
        (date(2026, 5, 5), date(2026, 5, 5), 0),
    ],
)
def test_datedif_months(start, end, expected):
    assert datedif_months(start, end) == expected


def test_calendar_days_fractions():
    fractions = month_fractions(date(2026, 1, 16), date(2026, 3, 10))
    assert fractions == (
        (Month(2026, 1), Fraction(16, 31)),
        (Month(2026, 2), Fraction(1)),
        (Month(2026, 3), Fraction(10, 31)),
    )


def test_single_day():
    assert month_fractions(date(2026, 2, 14), date(2026, 2, 14)) == (
        (Month(2026, 2), Fraction(1, 28)),
    )


def test_whole_months_counts_every_touched_month():
    fractions = month_fractions(
        date(2026, 1, 31), date(2026, 3, 1), PartialMonths.WHOLE_MONTHS
    )
    assert [f for _, f in fractions] == [1, 1, 1]


def test_grist_datedif_counts_complete_months_plus_one():
    fractions = month_fractions(
        date(2026, 1, 16), date(2026, 3, 10), PartialMonths.GRIST_DATEDIF
    )
    assert fractions == ((Month(2026, 1), Fraction(1)), (Month(2026, 2), Fraction(1)))


@pytest.mark.parametrize("strategy", list(PartialMonths))
def test_full_year_is_twelve_months_under_every_strategy(strategy):
    fractions = month_fractions(date(2026, 1, 1), date(2026, 12, 31), strategy)
    assert sum(f for _, f in fractions) == 12
