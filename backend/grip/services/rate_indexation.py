"""A new rate card as an indexed copy of an earlier year.

The rates of the source year go up by a percentage and are rounded by an
explicit rule; the scale-to-category mapping is copied unchanged. The new
card is a draft, so every rate can still be changed per category afterwards.

All arithmetic is in exact decimals. The percentage and the rounding rule
are written to the audit row of the creation, so a rate can be explained
later.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, record_audit
from grip.models.person import Person
from grip.models.rates import RateBand, RateCard, ScaleBand
from grip.repositories.domain import RateRepository
from grip.services.errors import DomainValidationError, NotFoundError

# The step a new rate is rounded to, in cents.
ROUNDING_STEPS_CENTS: dict[str, int] = {"euro": 100, "ten": 1000, "fifty": 5000}
DEFAULT_ROUNDING = "euro"

MIN_INCREASE_PCT = Decimal(0)
MAX_INCREASE_PCT = Decimal(25)


@dataclass(frozen=True)
class IndexedRate:
    category: str
    old_monthly_rate_cents: int
    new_monthly_rate_cents: int

    @property
    def difference_cents(self) -> int:
        return self.new_monthly_rate_cents - self.old_monthly_rate_cents


def validate_increase(increase_pct: Decimal, rounding: str) -> Decimal:
    """Check the percentage and the rounding rule; return the percentage."""
    pct = Decimal(increase_pct)
    if not pct.is_finite() or not MIN_INCREASE_PCT <= pct <= MAX_INCREASE_PCT:
        raise DomainValidationError(
            f"Een verhoging ligt tussen {MIN_INCREASE_PCT} en {MAX_INCREASE_PCT} "
            "procent."
        )
    if pct != pct.quantize(Decimal("0.01")):
        raise DomainValidationError(
            "Een verhoging heeft hoogstens twee cijfers achter de komma."
        )
    if rounding not in ROUNDING_STEPS_CENTS:
        raise DomainValidationError(f"Onbekende afronding: {rounding}")
    return pct


def indexed_rate_cents(old_cents: int, increase_pct: Decimal, rounding: str) -> int:
    """The old monthly rate plus the percentage, rounded to the step.

    Halves round up (away from zero for the amounts that occur here), the
    rule people expect from a rate sheet.
    """
    pct = validate_increase(increase_pct, rounding)
    step = Decimal(ROUNDING_STEPS_CENTS[rounding])
    exact = Decimal(old_cents) * (Decimal(100) + pct) / Decimal(100)
    steps = (exact / step).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(steps * step)


async def _source(session: AsyncSession, year: int) -> RateCard:
    card = await RateRepository(session).get_card(year)
    if card is None:
        raise NotFoundError("Tarievenkaart", year)
    return card


async def preview_indexed_rates(
    session: AsyncSession,
    copy_from: int,
    increase_pct: Decimal,
    rounding: str = DEFAULT_ROUNDING,
) -> list[IndexedRate]:
    """Per category of the source year: the old rate and what it becomes."""
    validate_increase(increase_pct, rounding)
    source = await _source(session, copy_from)
    return [
        IndexedRate(
            category=band.category,
            old_monthly_rate_cents=band.monthly_rate_cents,
            new_monthly_rate_cents=indexed_rate_cents(
                band.monthly_rate_cents, increase_pct, rounding
            ),
        )
        for band in sorted(source.rate_bands, key=lambda b: b.category)
    ]


async def create_indexed_rate_card(
    session: AsyncSession,
    year: int,
    *,
    copy_from: int,
    increase_pct: Decimal,
    actor: Person | None,
    rounding: str = DEFAULT_ROUNDING,
) -> RateCard:
    """Create the rate card of a year as a draft, indexed from another year."""
    pct = validate_increase(increase_pct, rounding)
    repo = RateRepository(session)
    if await repo.get_card(year) is not None:
        raise DomainValidationError(f"Er is al een tarievenkaart voor {year}.")
    rates = await preview_indexed_rates(session, copy_from, pct, rounding)
    source = await _source(session, copy_from)

    session.add(RateCard(year=year, status="draft"))
    for rate in rates:
        session.add(
            RateBand(
                year=year,
                category=rate.category,
                monthly_rate_cents=rate.new_monthly_rate_cents,
            )
        )
    for band in source.scale_bands:
        session.add(ScaleBand(year=year, scale=band.scale, category=band.category))
    await session.flush()

    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="rate_card",
        entity_id=str(year),
        new_value={
            "year": year,
            "status": "draft",
            "copied_from": copy_from,
            "increase_pct": format(pct.normalize(), "f"),
            "rounding": rounding,
            "rounding_step_cents": ROUNDING_STEPS_CENTS[rounding],
            "monthly_rate_cents": {
                rate.category: {
                    "old": rate.old_monthly_rate_cents,
                    "new": rate.new_monthly_rate_cents,
                }
                for rate in rates
            },
        },
    )
    card = await repo.get_card(year)
    assert card is not None
    return card
