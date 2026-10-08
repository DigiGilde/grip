"""Rate cards per year: rates per category and the scale-to-category mapping.

Everyone who is logged in may read them; only the beheerder changes them.
A closed year is locked: a change needs ``confirm_closed_year`` in the body,
and the service then writes an audit row that names the override.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, Resource
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.reference_support import filtered, may
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.models.rates import RateCard
from grip.repositories.domain import RateRepository
from grip.schema.rates import (
    Category,
    IndexationPreviewOut,
    IndexedRateOut,
    RateBandOut,
    RateBandUpdate,
    RateCardCreate,
    RateCardListOut,
    RateCardOut,
    RateCardStatusUpdate,
    Rounding,
    ScaleBandOut,
    ScaleBandUpdate,
)
from grip.services import rate_indexation, rates
from grip.services.errors import NotFoundError

router = APIRouter(prefix="/rates", tags=["rates"])

_CARDS = Resource.rate_card()

Year = Annotated[int, Path(ge=2000, le=2100)]
Scale = Annotated[int, Path(ge=1, le=30)]


def _card_out(card: RateCard) -> RateCardOut:
    return RateCardOut(
        year=card.year,
        status=card.status,
        rate_bands=[
            RateBandOut(category=b.category, monthly_rate_cents=b.monthly_rate_cents)
            for b in sorted(card.rate_bands, key=lambda b: b.category)
        ],
        scale_bands=[
            ScaleBandOut(scale=b.scale, category=b.category)
            for b in sorted(card.scale_bands, key=lambda b: b.scale)
        ],
    )


async def _fresh_card(db: AsyncSession, year: int) -> RateCard:
    card = await RateRepository(db).get_card(year)
    if card is None:
        raise NotFoundError("Tarievenkaart", year)
    # The service added or changed bands through the session; the card that
    # is already loaded does not show new ones until it is refreshed.
    await db.refresh(card, attribute_names=["status", "rate_bands", "scale_bands"])
    return card


@router.get("/cards", response_model=None)
async def list_rate_cards(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """All rate cards, newest year first."""
    await require(decider, subject, Action.READ, _CARDS, DataClass.MASTER_DATA)
    cards = await RateRepository(db).all_cards()
    value = RateCardListOut(
        items=[_card_out(c) for c in sorted(cards, key=lambda c: c.year, reverse=True)],
        may_manage=await may(decider, subject, Action.MANAGE_RATES, _CARDS),
        default_increase_pct=settings.RATE_INDEXATION_DEFAULT_PCT,
    )
    return await filtered(decider, subject, _CARDS, value)


@router.get("/indexation-preview", response_model=None)
async def preview_indexation(
    subject: CurrentSubject,
    decider: AccessDecider,
    copy_from: Annotated[int, Query(ge=2000, le=2100)],
    increase_pct: Annotated[Decimal, Query(ge=0, le=25, decimal_places=2)],
    rounding: Rounding = "euro",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What a new rate card would contain: old rate, new rate and difference.

    Creates nothing. For whoever manages rates, as the step before starting
    a new year.
    """
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    rates_ = await rate_indexation.preview_indexed_rates(
        db, copy_from, increase_pct, rounding
    )
    value = IndexationPreviewOut(
        copy_from=copy_from,
        increase_pct=increase_pct,
        rounding=rounding,
        rates=[
            IndexedRateOut(
                category=r.category,
                old_monthly_rate_cents=r.old_monthly_rate_cents,
                new_monthly_rate_cents=r.new_monthly_rate_cents,
                difference_cents=r.difference_cents,
            )
            for r in rates_
        ],
    )
    return await filtered(decider, subject, _CARDS, value)


@router.get("/cards/{year}", response_model=None)
async def get_rate_card(
    year: Year,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require(decider, subject, Action.READ, _CARDS, DataClass.MASTER_DATA)
    card = await RateRepository(db).get_card(year)
    if card is None:
        raise NotFoundError("Tarievenkaart", year)
    return await filtered(decider, subject, _CARDS, _card_out(card))


@router.post("/cards", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_rate_card(
    body: RateCardCreate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start the rate card of a year as a draft, optionally as a copy."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    if body.copy_from is not None and body.increase_pct is not None:
        await rate_indexation.create_indexed_rate_card(
            db,
            body.year,
            copy_from=body.copy_from,
            increase_pct=body.increase_pct,
            rounding=body.rounding,
            actor=person,
        )
    else:
        await rates.create_rate_card(
            db, body.year, actor=person, copy_from=body.copy_from
        )
    card = await _fresh_card(db, body.year)
    return await filtered(decider, subject, _CARDS, _card_out(card))


@router.put("/cards/{year}/status", response_model=None)
async def set_rate_card_status(
    year: Year,
    body: RateCardStatusUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate, close or (with confirmation) reopen a rate card."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    await rates.set_rate_card_status(
        db,
        year,
        body.status,
        actor=person,
        allow_closed_year=body.confirm_closed_year,
    )
    card = await _fresh_card(db, year)
    return await filtered(decider, subject, _CARDS, _card_out(card))


@router.put("/cards/{year}/bands/{category}", response_model=None)
async def set_rate_band(
    year: Year,
    category: Category,
    body: RateBandUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set the monthly rate per FTE of a category in a year."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    await rates.set_rate_band(
        db,
        year,
        category,
        body.monthly_rate_cents,
        actor=person,
        allow_closed_year=body.confirm_closed_year,
    )
    card = await _fresh_card(db, year)
    return await filtered(decider, subject, _CARDS, _card_out(card))


@router.put("/cards/{year}/scales/{scale}", response_model=None)
async def set_scale_band(
    year: Year,
    scale: Scale,
    body: ScaleBandUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set the category a scale bills in for a year."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    await rates.set_scale_band(
        db,
        year,
        scale,
        body.category,
        actor=person,
        allow_closed_year=body.confirm_closed_year,
    )
    card = await _fresh_card(db, year)
    return await filtered(decider, subject, _CARDS, _card_out(card))
