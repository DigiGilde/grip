"""Whether the budget still says what the quote in force says.

A quote freezes the budget. When the budget changes afterwards, the quote
that is out no longer matches it, also when the total happens to stay the
same: a line moved from one role to another, a period shifted. The screens
then lead to a new quote, and this module is the one place that decides it.

The comparison is on content, not on totals: the lines, the subtotals and
the total of the quote against what a quote made now would hold. What
belongs to the quote itself (reference, validity, conditions, sender) is
left out, because it is no part of the budget.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.models.assignment import Assignment
from grip.models.quote import Quote
from grip.services import canonical, quotes
from grip.services.errors import DomainValidationError

# A quote the budget is held against: still open, or accepted.
COMPARED_STATUSES = ("issued", "accepted")
# Derived from the rate card, not from the budget, and absent on quotes made
# before it was recorded: no ground to call the budget changed.
_NOT_BUDGET_LINE_KEYS = frozenset({"scales"})


def budget_fingerprint(content: dict[str, Any]) -> str:
    """The hash of the part of a quote's content that comes from the budget."""
    lines = [
        {key: value for key, value in line.items() if key not in _NOT_BUDGET_LINE_KEYS}
        for line in content.get("lines") or []
    ]
    part = {
        "lines": lines,
        "subtotals_per_year": content.get("subtotals_per_year") or [],
        "total": content.get("total"),
    }
    return canonical.hash_of(canonical.canonical_json(part))


async def quote_in_force(session: AsyncSession, assignment_id: UUID) -> Quote | None:
    """The latest quote that is open or accepted, or none."""
    result = await session.execute(
        select(Quote)
        .where(
            Quote.assignment_id == assignment_id,
            Quote.status.in_(COMPARED_STATUSES),
        )
        .order_by(Quote.issued_at.desc(), Quote.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def budget_moved(
    session: AsyncSession, assignment: Assignment
) -> tuple[bool | None, UUID | None]:
    """Whether the budget changed since the quote in force, and which quote.

    None when there is nothing to compare: no such quote, or the budget
    cannot be turned into a quote right now. Saying nothing is then right;
    the preview says why no quote can be made.
    """
    quote = await quote_in_force(session, assignment.id)
    if quote is None:
        return None, None
    try:
        current = await quotes.build_snapshot(session, assignment)
    except (calc.CalcError, DomainValidationError):
        return None, quote.id
    moved = budget_fingerprint(current) != budget_fingerprint(quote.snapshot)
    return moved, quote.id
