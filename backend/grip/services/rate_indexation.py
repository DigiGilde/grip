"""A new rate card as an indexed copy of an earlier card.

The rates of the source card go up by a percentage and are rounded by an
explicit rule; the scale-to-category mapping is copied unchanged. The new
card starts on any first of a month: a new calendar year, or halfway. The new
card is a draft, so every rate can still be changed per category afterwards.

All arithmetic is in exact decimals. The percentage and the rounding rule
are written to the audit row of the creation, so a rate can be explained
later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.person import Person
from grip.models.rates import RateCard
from grip.repositories.domain import RateRepository
from grip.services import rates as rate_cards
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.rates import CardKey

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


async def _source(session: AsyncSession, key: CardKey) -> RateCard:
    card = await RateRepository(session).get_card(key)
    if card is None:
        raise NotFoundError("Tarievenkaart", key)
    return card


def _indexed(source: RateCard, pct: Decimal, rounding: str) -> list[IndexedRate]:
    return [
        IndexedRate(
            category=band.category,
            old_monthly_rate_cents=band.monthly_rate_cents,
            new_monthly_rate_cents=indexed_rate_cents(
                band.monthly_rate_cents, pct, rounding
            ),
        )
        for band in sorted(source.rate_bands, key=lambda b: b.category)
    ]


async def preview_indexed_rates(
    session: AsyncSession,
    copy_from: CardKey,
    increase_pct: Decimal,
    rounding: str = DEFAULT_ROUNDING,
) -> list[IndexedRate]:
    """Per category of the source card: the old rate and what it becomes."""
    validate_increase(increase_pct, rounding)
    return _indexed(await _source(session, copy_from), increase_pct, rounding)


async def create_indexed_card(
    session: AsyncSession,
    *,
    valid_from: date,
    increase_pct: Decimal,
    actor: Person | None,
    valid_to: date | None = None,
    name: str | None = None,
    copy_from: CardKey | None = None,
    rounding: str = DEFAULT_ROUNDING,
) -> RateCard:
    """Start a card from a date as a draft, indexed from another card.

    Without ``copy_from`` the source is the card valid just before the start
    date. The percentage and the rounding rule go into the audit row, so a
    rate can be explained later.
    """
    pct = validate_increase(increase_pct, rounding)
    source = (
        await _source(session, copy_from)
        if copy_from is not None
        else await rate_cards.previous_card(session, valid_from)
    )
    if source is None:
        raise DomainValidationError(
            "Er is geen eerdere tarievenkaart om van uit te gaan."
        )
    indexed = _indexed(source, pct, rounding)
    return await rate_cards.create_card(
        session,
        valid_from=valid_from,
        valid_to=valid_to,
        name=name,
        copy_from=source.id,
        actor=actor,
        indexed_rates={r.category: r.new_monthly_rate_cents for r in indexed},
        audit_extra={
            "year": valid_from.year,
            "increase_pct": format(pct.normalize(), "f"),
            "rounding": rounding,
            "rounding_step_cents": ROUNDING_STEPS_CENTS[rounding],
            "monthly_rate_cents": {
                rate.category: {
                    "old": rate.old_monthly_rate_cents,
                    "new": rate.new_monthly_rate_cents,
                }
                for rate in indexed
            },
        },
    )


async def create_indexed_rate_card(
    session: AsyncSession,
    year: int,
    *,
    copy_from: CardKey,
    increase_pct: Decimal,
    actor: Person | None,
    rounding: str = DEFAULT_ROUNDING,
) -> RateCard:
    """The card of a calendar year, indexed from another card. The shape
    from before a card had a validity."""
    return await create_indexed_card(
        session,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
        copy_from=copy_from,
        increase_pct=increase_pct,
        rounding=rounding,
        actor=actor,
    )
