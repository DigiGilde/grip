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

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

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
    }
)

_MONEY_KEYS = frozenset({"amount_cents", "currency"})
_PERIOD_KEYS = frozenset({"start_date", "end_date"})
_SUBTOTAL_KEYS = frozenset({"year", "amount"})
_RATE_PER_YEAR_KEYS = frozenset({"year", "monthly_rate"})

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
    }
)

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
        "monthly_rates_per_year",
        "year",
        "amount",
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
        for i, rate in enumerate(line.get("monthly_rates_per_year") or []):
            inner = f"{where}.monthly_rates_per_year[{i}]"
            _check_keys(inner, rate, _RATE_PER_YEAR_KEYS)
            _check_keys(f"{inner}.monthly_rate", rate.get("monthly_rate"), _MONEY_KEYS)
    return snapshot
