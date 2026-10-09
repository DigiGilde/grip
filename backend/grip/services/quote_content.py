"""What a quote may be built from, and what it may contain.

A quote goes to the client. The budget it is built from also holds things
the client must never see: who the role is meant for, and whatever is added
to a budget line later. Leaving those out by remembering to is not enough,
so two things here are explicit:

1. The source. A quote line is built from a ``QuoteLineSource``, a copy of
   the columns of a budget line that are listed in ``QUOTE_SOURCE_COLUMNS``.
   The builder never holds the budget line itself, so it cannot read a
   column that is not on the list. Every column of ``budget_line`` is either
   on that list or in ``INTERNAL_COLUMNS``; a test fails when a new column is
   in neither, so adding a column forces the choice.

2. The result. ``check_content`` refuses a quote content with a key that is
   not on the allow-list. It runs every time a content is built, before it is
   previewed, hashed or stored.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from grip.calc import MonthAmount
from grip.models.assignment import BudgetLine

# Columns of budget_line that may feed a quote line.
QUOTE_SOURCE_COLUMNS = frozenset(
    {
        "position",
        "description",
        "kind",
        "role",
        "fte",
        "rate_category",
        "start_date",
        "end_date",
        "amount_cents",
        "year",
    }
)

# Columns of budget_line that never reach a quote. The two ids are handed to
# the calculation module to tell lines apart and are not copied into the
# content; the intended person is staffing data; the reference to the role
# catalogue is internal, the name of the role (``role``) is what is quoted.
INTERNAL_COLUMNS = frozenset(
    {
        "id",
        "assignment_id",
        "intended_person_id",
        "role_id",
        # A quote shows the period in force (start_date, end_date), not
        # whether the line follows the assignment.
        "period_source",
        "created_at",
        "updated_at",
        # Counts the changes of the row; says nothing a quote needs.
        "version",
    }
)

_MONEY_KEYS = frozenset({"amount_cents", "currency"})
_PERIOD_KEYS = frozenset({"start_date", "end_date"})
_SUBTOTAL_KEYS = frozenset({"year", "amount"})
_RATE_PER_YEAR_KEYS = frozenset({"year", "monthly_rate"})
_RATE_PERIOD_KEYS = frozenset({"start_date", "end_date", "monthly_rate"})

# Keys a quote content may have, in code names.
ALLOWED_CONTENT_KEYS = frozenset(
    {
        "name",
        "context_refs",
        "lines",
        "subtotals_per_year",
        "total",
        "valid_until",
        "conditions",
        # The reference people quote, the client's own reference, and the
        # organisation that sends the quote. None of them names a person.
        "reference",
        "client_reference",
        "sender",
        # The text of the quote as a letter: subject, addressee, sections,
        # closing, the sender's addresses and who signs. Checked key by key
        # below; the names in it are the ones a letter carries on purpose
        # (who it is addressed to, who signs), never staff on the work.
        "letter",
    }
)

ALLOWED_LETTER_KEYS = frozenset(
    {
        "subject",
        "addressee",
        "salutation",
        "opening",
        "closing",
        "sections",
        "sender_details",
        "signatures",
        "billing_annex",
    }
)
ALLOWED_SECTION_KEYS = frozenset({"key", "heading", "body", "with_costs", "numbered"})
ALLOWED_SENDER_DETAIL_KEYS = frozenset(
    {"organisation", "part_of", "unit", "visiting_address", "postal_address", "website"}
)
ALLOWED_SIGNATURE_KEYS = frozenset({"on_behalf_of", "name", "function", "organisation"})

# Keys a quote line may have.
ALLOWED_LINE_KEYS = frozenset(
    {
        "position",
        "description",
        "kind",
        "role",
        "fte",
        "rate_category",
        "period",
        "monthly_rate",
        # The rates per period of validity the line touches, when the rate
        # changes inside the line's period. A period can begin and end on
        # any day.
        "monthly_rate_periods",
        # The same, when the rate changes only on 1 January: a rate per
        # calendar year.
        "monthly_rates_per_year",
        "year",
        "amount",
        # The scales the rate category of the line covers: what a client
        # reads on the rate leaflet.
        "scales",
    }
)


class QuoteContentError(RuntimeError):
    """A quote content holds something that is not allowed in a quote.

    This is a fault in the program, not in what a user entered: it means a
    field found its way into the quote without being put on the allow-list.
    """


@dataclass(frozen=True)
class QuoteLineSource:
    """The part of a budget line a quote line is built from. Nothing else."""

    # For the calculation module only; never copied into the content.
    id: UUID
    assignment_id: UUID
    position: int
    description: str
    kind: str
    role: str | None
    fte: Decimal | None
    rate_category: str | None
    start_date: date | None
    end_date: date | None
    amount_cents: int | None
    year: int | None


def line_source(line: BudgetLine) -> QuoteLineSource:
    """Copy the allowed columns of a budget line."""
    return QuoteLineSource(
        id=line.id,
        assignment_id=line.assignment_id,
        **{name: getattr(line, name) for name in sorted(QUOTE_SOURCE_COLUMNS)},
    )


def _check_keys(where: str, value: Any, allowed: frozenset[str]) -> None:
    if not isinstance(value, dict):
        raise QuoteContentError(f"{where} is not an object")
    extra = set(value) - allowed
    if extra:
        raise QuoteContentError(
            f"{where} holds keys that are not allowed in a quote: "
            f"{', '.join(sorted(extra))}"
        )


def check_content(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Refuse a quote content with anything outside the allow-list.

    Returns the content, so a builder can end with
    ``return check_content(snapshot)``.
    """
    _check_keys("quote", snapshot, ALLOWED_CONTENT_KEYS)
    _check_keys("quote.total", snapshot.get("total"), _MONEY_KEYS)
    for index, sub in enumerate(snapshot.get("subtotals_per_year") or []):
        where = f"quote.subtotals_per_year[{index}]"
        _check_keys(where, sub, _SUBTOTAL_KEYS)
        _check_keys(f"{where}.amount", sub.get("amount"), _MONEY_KEYS)
    for index, line in enumerate(snapshot.get("lines") or []):
        where = f"quote.lines[{index}]"
        _check_keys(where, line, ALLOWED_LINE_KEYS)
        _check_keys(f"{where}.amount", line.get("amount"), _MONEY_KEYS)
        if "period" in line:
            _check_keys(f"{where}.period", line["period"], _PERIOD_KEYS)
        if "monthly_rate" in line:
            _check_keys(f"{where}.monthly_rate", line["monthly_rate"], _MONEY_KEYS)
        for i, rate in enumerate(line.get("monthly_rate_periods") or []):
            inner = f"{where}.monthly_rate_periods[{i}]"
            _check_keys(inner, rate, _RATE_PERIOD_KEYS)
            _check_keys(f"{inner}.monthly_rate", rate.get("monthly_rate"), _MONEY_KEYS)
        for i, rate in enumerate(line.get("monthly_rates_per_year") or []):
            inner = f"{where}.monthly_rates_per_year[{i}]"
            _check_keys(inner, rate, _RATE_PER_YEAR_KEYS)
            _check_keys(f"{inner}.monthly_rate", rate.get("monthly_rate"), _MONEY_KEYS)
    if "letter" in snapshot:
        letter = snapshot["letter"]
        _check_keys("quote.letter", letter, ALLOWED_LETTER_KEYS)
        for index, section in enumerate(letter.get("sections") or []):
            _check_keys(
                f"quote.letter.sections[{index}]", section, ALLOWED_SECTION_KEYS
            )
        if "sender_details" in letter:
            _check_keys(
                "quote.letter.sender_details",
                letter["sender_details"],
                ALLOWED_SENDER_DETAIL_KEYS,
            )
        for index, signature in enumerate(letter.get("signatures") or []):
            _check_keys(
                f"quote.letter.signatures[{index}]", signature, ALLOWED_SIGNATURE_KEYS
            )
    return snapshot


def rate_periods(months: Iterable[MonthAmount]) -> list[tuple[date, date, int]]:
    """The stretches of a priced line in which the monthly rate is constant.

    From the stretches the calculation module priced, so the periods are
    exactly what the amount was built from. Adjacent stretches at the same
    rate are one period; a period can begin and end on any day.
    """
    periods: list[tuple[date, date, int]] = []
    for month in months:
        for stretch in month.stretches:
            if periods and periods[-1][2] == stretch.monthly_rate_cents:
                periods[-1] = (periods[-1][0], stretch.end, stretch.monthly_rate_cents)
            else:
                periods.append((stretch.start, stretch.end, stretch.monthly_rate_cents))
    return periods


def line_rates(
    months: Iterable[MonthAmount], *, currency: str = "EUR"
) -> dict[str, Any]:
    """What a quote line carries about its rate.

    - ``monthly_rate`` when one rate holds over the whole period of the line.
    - ``monthly_rates_per_year`` when the rate changes only on 1 January: a
      rate per calendar year, the form the contract already knows.
    - ``monthly_rate_periods`` when the rate changes inside a year: per
      period of validity the line touches its first day, its last day and
      the monthly rate. A period can begin and end on any day; the amount of
      the line is priced by day over those periods.
    """
    periods = rate_periods(months)

    def money(cents: int) -> dict[str, Any]:
        return {"amount_cents": cents, "currency": currency}

    if len(periods) == 1:
        return {"monthly_rate": money(periods[0][2])}
    if all((start.month, start.day) == (1, 1) for start, _, _ in periods[1:]) and len(
        {start.year for start, _, _ in periods}
    ) == len(periods):
        return {
            "monthly_rates_per_year": [
                {"year": start.year, "monthly_rate": money(cents)}
                for start, _, cents in periods
            ]
        }
    return {
        "monthly_rate_periods": [
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "monthly_rate": money(cents),
            }
            for start, end, cents in periods
        ]
    }
