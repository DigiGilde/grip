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
    def __init__(self, year: int) -> None:
        super().__init__(
            f"Het jaar {year} is gesloten. Wijzigen kan alleen door een beheerder "
            "en laat een auditregel achter."
        )
        self.year = year


class MonthClosedError(DomainError):
    def __init__(self, month: str) -> None:
        super().__init__(
            f"De maand {month} is afgesloten voor deze opdracht. Heropen de maand "
            "om de inzet te wijzigen."
        )
        self.month = month


class QuoteHashMismatchError(DomainError):
    def __init__(self) -> None:
        super().__init__("De hash in het akkoord hoort niet bij de uitgegeven offerte.")


class QuoteAlreadyDecidedError(DomainError):
    def __init__(self, status: str) -> None:
        super().__init__(f"Deze offerte is al afgehandeld (status '{status}').")
        self.status = status
