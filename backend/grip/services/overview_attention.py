"""What needs attention on an assignment, as sentences for the start page.

Built from the same read model as the Financieel tab, so the start page and
the tab never disagree. Each point names the tab where it is solved.
"""

from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.services import outgoing_invoices, pricing
from grip.services.assignment_finance import AssignmentFinance


@dataclass(frozen=True)
class Attention:
    kind: str
    text: str
    # The tab of the assignment where the point is solved.
    tab: str
    # Money points are for a reader of the finances; the rate mismatch is a
    # signal a planner sees too, without category or amount.
    about_money: bool


def _euro(cents: int) -> str:
    return "€ " + f"{round(cents / 100):,}".replace(",", ".")


def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def attention_points(data: AssignmentFinance) -> list[Attention]:
    """The points of one assignment, the most pressing first."""
    points: list[Attention] = []
    by_kind = {signal.kind: signal for signal in data.signals}
    if data.totals is not None and data.totals.overrun:
        over = _euro(-data.totals.variance_cents)
        points.append(
            Attention(
                "overrun",
                f"Verwacht totaal {over} boven de begroting.",
                "finance",
                True,
            )
        )
    overdue = by_kind.get("months_not_closed")
    if overdue is not None and overdue.count:
        text = (
            "1 maand met inzet is nog niet afgesloten."
            if overdue.count == 1
            else f"{overdue.count} maanden met inzet zijn nog niet afgesloten."
        )
        points.append(Attention("months_not_closed", text, "monthClose", True))
    unpriced = by_kind.get("not_priced")
    if unpriced is not None and unpriced.count:
        text = (
            "1 begrotingsregel kan niet worden berekend."
            if unpriced.count == 1
            else f"{unpriced.count} begrotingsregels kunnen niet worden berekend."
        )
        points.append(Attention("not_priced", text, "budget", True))
    mismatch = by_kind.get("rate_mismatch")
    if mismatch is not None and mismatch.count:
        who = _count(mismatch.count, "persoon declareert", "mensen declareren")
        points.append(
            Attention(
                "rate_mismatch",
                f"{who} in een andere schaal dan de begrotingsregel aanneemt.",
                "staffing",
                False,
            )
        )
    return points


# -- naverrekening ------------------------------------------------------------

# Why a delivered month costs something else now, in the words of the signal.
_CORRECTION_CAUSES = {
    pricing.CAUSE_PROMOTION: "een schaalwijziging",
    pricing.CAUSE_SCALE_CHANGE: "een schaalwijziging",
    pricing.CAUSE_RATE_CARD: "een nieuwe tarievenkaart",
}


@dataclass(frozen=True)
class CorrectionDue:
    # First days of the delivered months that cost something else now.
    months: tuple[date, ...]
    # What is still to deliver for them; negative when they became cheaper.
    amount_cents: int
    # "een schaalwijziging", "een nieuwe tarievenkaart", or None when the
    # cause is not a rate difference grip can name.
    cause: str | None


async def correction_due(
    session: AsyncSession,
    assignment_id: UUID,
    differences: Iterable[pricing.RateDifference],
) -> CorrectionDue | None:
    """Delivered months whose price changed afterwards: a naverrekening.

    The amount comes from the billing position, the same source as "nog aan
    te leveren", so the two agree.
    """
    months = [
        month
        for month in await outgoing_invoices.month_billing(session, assignment_id)
        if month.closed and month.export_id is not None and month.to_deliver_cents
    ]
    if not months:
        return None
    first = min(month.month for month in months)
    last_day = date(first.year, first.month, monthrange(first.year, first.month)[1])
    cause = next(
        (
            _CORRECTION_CAUSES[d.cause]
            for d in sorted(differences, key=lambda d: d.since)
            if d.cause in _CORRECTION_CAUSES and d.since <= last_day
        ),
        None,
    )
    return CorrectionDue(
        months=tuple(sorted(month.month for month in months)),
        amount_cents=sum(month.to_deliver_cents or 0 for month in months),
        cause=cause,
    )
