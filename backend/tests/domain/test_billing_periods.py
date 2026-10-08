"""Billing periods: whole months, grouped by the rhythm of the agreement."""

from datetime import date

import pytest

from grip.calc import Month
from grip.services import billing_periods
from grip.services.billing_periods import MONTHLY, QUARTERLY


def _keys(periods):
    return [period.key for period in periods]


def test_a_year_per_quarter_is_four_whole_periods():
    periods = billing_periods.periods_between(
        date(2026, 1, 1), date(2026, 12, 31), QUARTERLY
    )
    assert _keys(periods) == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    assert all(period.whole and len(period.months) == 3 for period in periods)
    assert periods[2].label == "derde kwartaal 2026"
    assert periods[2].span == "juli t/m september 2026"
    assert periods[2].start == date(2026, 7, 1)
    assert periods[2].end == date(2026, 9, 30)


def test_the_first_and_last_period_can_be_part_of_a_quarter():
    periods = billing_periods.periods_between(
        date(2026, 8, 15), date(2027, 1, 20), QUARTERLY
    )
    assert _keys(periods) == ["2026-Q3", "2026-Q4", "2027-Q1"]
    assert [len(p.months) for p in periods] == [2, 3, 1]
    assert [p.whole for p in periods] == [False, True, False]
    assert periods[0].span == "augustus t/m september 2026"
    assert periods[2].span == "januari 2027"


def test_per_month_every_month_is_a_period():
    periods = billing_periods.periods_between(
        date(2026, 11, 1), date(2027, 1, 31), MONTHLY
    )
    assert _keys(periods) == ["2026-11", "2026-12", "2027-01"]
    assert periods[0].label == "november 2026"
    assert periods[0].span == "november 2026"


def test_months_outside_the_plan_still_get_a_period():
    periods = billing_periods.periods_of(
        [Month(2026, 3), Month(2026, 7), Month(2026, 8)], QUARTERLY
    )
    assert _keys(periods) == ["2026-Q1", "2026-Q3"]
    assert billing_periods.find(periods, "2026-Q3").months == (
        Month(2026, 7),
        Month(2026, 8),
    )
    assert billing_periods.find(periods, "2026-Q2") is None


def test_an_unknown_rhythm_is_refused():
    with pytest.raises(ValueError):
        billing_periods.periods_of([Month(2026, 1)], "year")
