"""Calendar months and month fractions.

Every amount in grip is split per calendar month and priced with the rate
card of the year of that month. This module only knows about dates.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from fractions import Fraction


class PartialMonths(StrEnum):
    """How a period that does not cover whole calendar months is counted.

    CALENDAR_DAYS: pro rata, days in the period divided by days in the month.
    WHOLE_MONTHS: every calendar month the period touches counts fully.
    GRIST_DATEDIF: the number of months is DATEDIF(start, end, "M") + 1, as
        in the Grist document; those months are attributed to the first
        calendar months of the period, each counting fully.
    """

    CALENDAR_DAYS = "calendar_days"
    WHOLE_MONTHS = "whole_months"
    GRIST_DATEDIF = "grist_datedif"


@dataclass(frozen=True, order=True)
class Month:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month must be 1..12, got {self.month}")

    @classmethod
    def of(cls, day: date) -> Month:
        return cls(day.year, day.month)

    @property
    def days(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def last_day(self) -> date:
        return date(self.year, self.month, self.days)

    def next(self) -> Month:
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def months_of_year(year: int) -> tuple[Month, ...]:
    return tuple(Month(year, m) for m in range(1, 13))


def _check_period(start: date, end: date) -> None:
    if end < start:
        raise ValueError(f"period ends ({end}) before it starts ({start})")


def months_between(start: date, end: date) -> tuple[Month, ...]:
    """All calendar months touched by the inclusive period [start, end]."""
    _check_period(start, end)
    months = []
    current = Month.of(start)
    last = Month.of(end)
    while current <= last:
        months.append(current)
        current = current.next()
    return tuple(months)


def overlap(month: Month, start: date, end: date) -> tuple[date, date] | None:
    """The part of the inclusive period [start, end] that falls in the month."""
    first = max(month.first_day, start)
    last = min(month.last_day, end)
    if last < first:
        return None
    return first, last


def datedif_months(start: date, end: date) -> int:
    """Complete months between two dates, as spreadsheet DATEDIF(.., "M")."""
    _check_period(start, end)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def month_fractions(
    start: date,
    end: date,
    strategy: PartialMonths = PartialMonths.CALENDAR_DAYS,
) -> tuple[tuple[Month, Fraction], ...]:
    """Month fraction per touched calendar month, months with zero left out."""
    touched = months_between(start, end)
    if strategy is PartialMonths.WHOLE_MONTHS:
        return tuple((month, Fraction(1)) for month in touched)
    if strategy is PartialMonths.GRIST_DATEDIF:
        count = datedif_months(start, end) + 1
        return tuple((month, Fraction(1)) for month in touched[:count])
    fractions = []
    for month in touched:
        first, last = overlap(month, start, end)  # type: ignore[misc]
        fractions.append((month, Fraction((last - first).days + 1, month.days)))
    return tuple(fractions)
