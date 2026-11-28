"""The naverrekening: delivered months whose price changed afterwards."""

from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.services import outgoing_invoices, pricing

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
