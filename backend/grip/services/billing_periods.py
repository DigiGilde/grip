"""Billing periods: the stretches an assignment is billed over.

Work is settled per month. Billing follows the rhythm the agreement names:
per month or per calendar quarter. A period is a run of whole calendar
months; the first and the last period of an assignment can hold fewer
months than the rhythm, because the assignment starts or ends inside them.

This module is pure: no database, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from grip.calc import Month

MONTHLY = "month"
QUARTERLY = "quarter"
RHYTHMS = (MONTHLY, QUARTERLY)

RHYTHM_TEXTS = {MONTHLY: "per maand", QUARTERLY: "per kwartaal"}

_MONTH_NAMES = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)
_ORDINALS = ("eerste", "tweede", "derde", "vierde")


def month_name(month: Month) -> str:
    return f"{_MONTH_NAMES[month.month - 1]} {month.year}"


@dataclass(frozen=True)
class Period:
    """One billing period: whole months, in order."""

    rhythm: str
    months: tuple[Month, ...]
    # False when the assignment covers only part of the calendar quarter.
    whole: bool

    @property
    def first(self) -> Month:
        return self.months[0]

    @property
    def last(self) -> Month:
        return self.months[-1]

    @property
    def start(self) -> date:
        return self.first.first_day

    @property
    def end(self) -> date:
        return self.last.last_day

    @property
    def key(self) -> str:
        """``2026-Q3`` for a quarter, ``2026-07`` for a month."""
        if self.rhythm == QUARTERLY:
            return f"{self.first.year}-Q{quarter_of(self.first)}"
        return str(self.first)

    @property
    def label(self) -> str:
        """``derde kwartaal 2026`` or ``juli 2026``."""
        if self.rhythm == QUARTERLY:
            return f"{_ORDINALS[quarter_of(self.first) - 1]} kwartaal {self.first.year}"
        return month_name(self.first)

    @property
    def span(self) -> str:
        """The months in words: ``juli t/m september 2026``."""
        if len(self.months) == 1:
            return month_name(self.first)
        return (
            f"{_MONTH_NAMES[self.first.month - 1]} t/m "
            f"{_MONTH_NAMES[self.last.month - 1]} {self.last.year}"
        )


def quarter_of(month: Month) -> int:
    return (month.month - 1) // 3 + 1


def _months_between(first: Month, last: Month) -> list[Month]:
    months: list[Month] = []
    current = first
    while (current.year, current.month) <= (last.year, last.month):
        months.append(current)
        current = current.next()
    return months


def periods_of(months: list[Month], rhythm: str) -> list[Period]:
    """Group the months of an assignment into billing periods, in order.

    ``months`` are the calendar months the assignment touches. A quarter
    that the assignment covers only in part is a period of fewer months.
    """
    if rhythm not in RHYTHMS:
        raise ValueError(f"unknown billing rhythm: {rhythm}")
    ordered = sorted(set(months), key=lambda m: (m.year, m.month))
    if rhythm == MONTHLY:
        return [Period(MONTHLY, (month,), True) for month in ordered]
    grouped: dict[tuple[int, int], list[Month]] = {}
    for month in ordered:
        grouped.setdefault((month.year, quarter_of(month)), []).append(month)
    return [
        Period(QUARTERLY, tuple(members), len(members) == 3)
        for _, members in sorted(grouped.items())
    ]


def periods_between(start: date, end: date, rhythm: str) -> list[Period]:
    """The billing periods of an assignment that runs from start to end."""
    return periods_of(_months_between(Month.of(start), Month.of(end)), rhythm)


def find(periods: list[Period], key: str) -> Period | None:
    for period in periods:
        if period.key == key:
            return period
    return None
