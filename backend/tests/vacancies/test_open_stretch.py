"""What of a role is open, and when: counted per month of its own period."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from grip.services.vacancies.service import _open_stretch


@dataclass
class Inzet:
    start_date: date
    end_date: date
    fte_pct: int


@dataclass
class Line:
    fte: Decimal
    start_date: date | None
    end_date: date | None
    allocations: list[Inzet] = field(default_factory=list)


TODAY = date(2026, 10, 9)


def role(*inzet: Inzet) -> Line:
    return Line(Decimal("0.8"), date(2027, 1, 1), date(2027, 6, 30), list(inzet))


def test_a_role_nobody_is_on_is_open_for_its_whole_period() -> None:
    assert _open_stretch(role(), TODAY) == (
        Decimal("0.8"),
        date(2027, 1, 1),
        date(2027, 6, 30),
    )


def test_a_role_filled_for_its_whole_period_is_not_open() -> None:
    line = role(Inzet(date(2027, 1, 1), date(2027, 6, 30), 80))
    assert _open_stretch(line, TODAY)[0] == 0


def test_someone_who_stops_early_leaves_the_rest_of_the_period_open() -> None:
    """Seen on the board: shortened to the end of April, the role vanished
    from "Open rollen" while May and June had nobody."""
    line = role(Inzet(date(2027, 1, 1), date(2027, 4, 30), 80))
    assert _open_stretch(line, TODAY) == (
        Decimal("0.8"),
        date(2027, 5, 1),
        date(2027, 6, 30),
    )


def test_someone_who_starts_late_leaves_the_first_months_open() -> None:
    line = role(Inzet(date(2027, 3, 1), date(2027, 6, 30), 80))
    assert _open_stretch(line, TODAY) == (
        Decimal("0.8"),
        date(2027, 1, 1),
        date(2027, 2, 28),
    )


def test_a_part_of_the_role_is_open_as_a_part() -> None:
    line = role(Inzet(date(2027, 1, 1), date(2027, 6, 30), 50))
    amount, start, end = _open_stretch(line, TODAY)
    assert amount == Decimal("0.3")
    assert (start, end) == (date(2027, 1, 1), date(2027, 6, 30))


def test_two_people_after_each_other_fill_the_role() -> None:
    line = role(
        Inzet(date(2027, 1, 1), date(2027, 3, 15), 80),
        Inzet(date(2027, 3, 16), date(2027, 6, 30), 80),
    )
    assert _open_stretch(line, TODAY)[0] == 0


def test_months_that_are_over_do_not_count() -> None:
    """Halfway the period only what is still to come is looked at."""
    line = role(Inzet(date(2027, 3, 1), date(2027, 6, 30), 80))
    assert _open_stretch(line, date(2027, 3, 10))[0] == 0


def test_a_role_without_an_end_counts_who_has_not_left() -> None:
    line = Line(Decimal("1"), date(2026, 1, 1), None, [])
    assert _open_stretch(line, TODAY) == (Decimal("1"), date(2026, 1, 1), None)
    line.allocations.append(Inzet(date(2026, 1, 1), date(2099, 12, 31), 100))
    assert _open_stretch(line, TODAY)[0] == 0
