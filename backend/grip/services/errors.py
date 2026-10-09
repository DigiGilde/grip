"""Errors of the service layer. Messages are shown to users, so Dutch."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error the service layer raises on purpose."""


class NotFoundError(DomainError):
    def __init__(self, what: str, key: object) -> None:
        super().__init__(f"{what} niet gevonden: {key}")
        self.what = what
        self.key = key


class DomainValidationError(DomainError):
    pass


class IllegalTransitionError(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Een opdracht met status '{current}' kan niet naar '{target}'."
        )
        self.current = current
        self.target = target


class ClosedYearError(DomainError):
    """A change touches a period priced by a closed rate card.

    The name dates from when a card was a calendar year. ``year`` is the
    year the closed card starts in.
    """

    def __init__(self, year: int, card_name: str | None = None) -> None:
        what = f"De tarievenkaart '{card_name}'" if card_name else f"Het jaar {year}"
        super().__init__(
            f"{what} is gesloten. Wijzigen kan alleen door een beheerder "
            "en laat een auditregel achter."
        )
        self.year = year
        self.card_name = card_name


ClosedCardError = ClosedYearError


def _month_in_words(month: str) -> str:
    """ "2026-01" as a person reads it: "januari 2026". Anything else as given."""
    from grip.services.reports.labels import MONTH_NAMES

    year, _, number = month.partition("-")
    if year.isdigit() and number.isdigit() and 1 <= int(number) <= 12:
        return f"{MONTH_NAMES[int(number) - 1]} {year}"
    return month


class MonthClosedError(DomainError):
    def __init__(self, month: str) -> None:
        super().__init__(
            f"De maand {_month_in_words(month)} is afgesloten voor deze opdracht. "
            "Heropen de maand om de inzet te wijzigen."
        )
        self.month = month


class QuoteHashMismatchError(DomainError):
    def __init__(self) -> None:
        super().__init__("De hash in het akkoord hoort niet bij de uitgegeven offerte.")


class QuoteAlreadyDecidedError(DomainError):
    def __init__(self, status: str) -> None:
        super().__init__(f"Deze offerte is al afgehandeld (status '{status}').")
        self.status = status
