"""Rate cards: rates per category and the scale-to-category mapping, each
card valid from a date to a date.

Everyone who is logged in may read which cards there are and which scales
a category covers; the amounts are for who may read the price list (the
beheerder, the lezer and who owns or manages an assignment). Only the
beheerder changes them, and only the beheerder sees a draft.
A closed card is locked: a change needs ``confirm_closed_year`` in the body,
and the service then writes an audit row that names the override.

A card is addressed by its id. A year in the path still addresses the card
that starts on 1 January of that year, for screens from before a card had a
validity.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
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
    ActivationPreviewOut,
    AssignmentImpactOut,
    Category,
    ClosedYearConfirmation,
    IndexationPreviewOut,
    IndexedRateOut,
    MonthChangeOut,
    PriceImpactOut,
    RateBandOut,
    RateBandUpdate,
    RateCardCreate,
    RateCardListOut,
    RateCardOut,
    RateCardStatusUpdate,
    RateCardUpdate,
    RateGapOut,
    Rounding,
    ScaleBandOut,
    ScaleBandUpdate,
    ShortenedCardOut,
    ValidRateOut,
    ValidRatesOut,
)
from grip.services import price_changes, rate_indexation, rates
from grip.services.errors import DomainValidationError, NotFoundError

router = APIRouter(prefix="/rates", tags=["rates"])

_CARDS = Resource.rate_card()

Scale = Annotated[int, Path(ge=1, le=30)]
# The id of a card, or the year of the card that starts on 1 January of it.
CardRef = Annotated[str, Path(min_length=4, max_length=36)]


def _key(ref: str) -> rates.CardKey:
    if ref.isdigit() and len(ref) == 4:
        return int(ref)
    try:
        return UUID(ref)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Onbekende verwijzing naar een tarievenkaart."
        ) from None


def _bands(card: RateCard) -> tuple[list[RateBandOut], list[ScaleBandOut]]:
    return (
        [
            RateBandOut(
                id=b.id,
                version=b.version,
                category=b.category,
                monthly_rate_cents=b.monthly_rate_cents,
            )
            for b in sorted(card.rate_bands, key=lambda b: b.category)
        ],
        [
            ScaleBandOut(scale=b.scale, category=b.category)
            for b in sorted(card.scale_bands, key=lambda b: b.scale)
        ],
    )


def _card_out(card: RateCard) -> RateCardOut:
    rate_bands, scale_bands = _bands(card)
    return RateCardOut(
        id=card.id,
        version=card.version,
        name=card.name,
        valid_from=card.valid_from,
        valid_to=card.valid_to,
        status=card.status,
        year=card.year,
        spans_calendar_year=card.spans_calendar_year,
        rate_bands=rate_bands,
        scale_bands=scale_bands,
    )


def _impact_out(impact: price_changes.PriceImpact) -> PriceImpactOut:
    return PriceImpactOut(
        budget_lines_changed=impact.budget_lines_changed,
        budget_difference_cents=impact.budget_difference_cents,
        allocations_changed=impact.allocations_changed,
        open_difference_cents=impact.open_difference_cents,
        closed_difference_cents=impact.closed_difference_cents,
        correction_cents=impact.correction_cents,
        unpriced_months=impact.unpriced_months,
        reaches_into_the_past=impact.reaches_into_the_past,
        signed_assignments_changed=impact.signed_assignments_changed,
        signed_difference_cents=impact.signed_difference_cents,
        assignments=[
            AssignmentImpactOut(
                assignment_id=a.assignment_id,
                assignment_name=a.assignment_name,
                open_difference_cents=a.open_difference_cents,
                closed_difference_cents=a.closed_difference_cents,
                correction_cents=a.correction_cents,
                months=[
                    MonthChangeOut(
                        month=str(m.month),
                        state=m.state,
                        before_cents=m.before_cents,
                        after_cents=m.after_cents,
                        difference_cents=m.difference_cents,
                        invoice_number=m.invoice_number,
                    )
                    for m in a.months
                ],
            )
            for a in impact.assignments
        ],
    )


async def _fresh_card(db: AsyncSession, key: rates.CardKey) -> RateCard:
    card = await RateRepository(db).get_card(key)
    if card is None:
        raise NotFoundError("Tarievenkaart", key)
    # The service added or changed bands through the session; the card that
    # is already loaded does not show new ones until it is refreshed.
    await db.refresh(
        card,
        attribute_names=["status", "name", "valid_to", "rate_bands", "scale_bands"],
    )
    return card


@router.get("/cards", response_model=None)
async def list_rate_cards(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """All rate cards, the one that starts last first."""
    await require(decider, subject, Action.READ, _CARDS, DataClass.MASTER_DATA)
    cards = await RateRepository(db).all_cards()
    may_manage = await may(decider, subject, Action.MANAGE_RATES, _CARDS)
    value = RateCardListOut(
        items=[
            _card_out(c)
            for c in sorted(cards, key=lambda c: c.valid_from, reverse=True)
            # A draft is the beheerder's work in progress.
            if may_manage or c.status != "draft"
        ],
        may_manage=may_manage,
        may_read_amounts=await may(
            decider, subject, Action.READ, _CARDS, DataClass.RATE_TABLE
        ),
        default_increase_pct=settings.RATE_INDEXATION_DEFAULT_PCT,
    )
    return await filtered(decider, subject, _CARDS, value)


@router.get("/valid", response_model=None)
async def get_valid_rates(
    subject: CurrentSubject,
    decider: AccessDecider,
    start_date: Annotated[date, Query()],
    end_date: Annotated[date | None, Query()] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The rates valid on a date, or over a period.

    For a form that prices something: which card applies, until when, and
    whether the period crosses into a card with other rates.
    """
    await require(decider, subject, Action.READ, _CARDS, DataClass.MASTER_DATA)
    last = end_date or start_date
    stretches = await rates.valid_rates(db, start_date, last)
    items = []
    for stretch in stretches:
        rate_bands, scale_bands = _bands(stretch.card) if stretch.card else ([], [])
        items.append(
            ValidRateOut(
                start_date=stretch.start_date,
                end_date=stretch.end_date,
                card_id=stretch.card.id if stretch.card else None,
                card_name=stretch.card.name if stretch.card else None,
                card_valid_to=stretch.card.valid_to if stretch.card else None,
                rate_bands=rate_bands,
                scale_bands=scale_bands,
            )
        )
    value = ValidRatesOut(
        start_date=start_date,
        end_date=last,
        stretches=items,
        crosses_cards=len([s for s in stretches if s.card is not None]) > 1,
        rates_differ=rates.rates_differ(stretches),
        has_gap=any(s.card is None for s in stretches),
        summary=rates.valid_rates_summary(
            stretches,
            tell_difference=await may(
                decider, subject, Action.READ, _CARDS, DataClass.RATE_TABLE
            ),
        ),
    )
    return await filtered(decider, subject, _CARDS, value)


@router.get("/indexation-preview", response_model=None)
async def preview_indexation(
    subject: CurrentSubject,
    decider: AccessDecider,
    increase_pct: Annotated[Decimal, Query(ge=0, le=25, decimal_places=2)],
    copy_from: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    copy_from_id: UUID | None = None,
    valid_from: date | None = None,
    rounding: Rounding = "euro",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What a new rate card would contain: old rate, new rate and difference.

    The source is ``copy_from_id``, or the card of the year ``copy_from``, or
    the card valid just before ``valid_from``. Creates nothing.
    """
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    if copy_from_id is not None or copy_from is not None:
        source = await rates.get_card(db, copy_from_id or copy_from)  # type: ignore[arg-type]
    elif valid_from is not None:
        found = await rates.previous_card(db, valid_from)
        if found is None:
            raise DomainValidationError(
                "Er is geen eerdere tarievenkaart om van uit te gaan."
            )
        source = found
    else:
        raise DomainValidationError(
            "Geef de tarievenkaart om van uit te gaan, of de begindatum."
        )
    rates_ = await rate_indexation.preview_indexed_rates(
        db, source.id, increase_pct, rounding
    )
    value = IndexationPreviewOut(
        copy_from=source.year,
        copy_from_id=source.id,
        copy_from_name=source.name,
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


@router.get("/cards/{card}", response_model=None)
async def get_rate_card(
    card: CardRef,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require(decider, subject, Action.READ, _CARDS, DataClass.MASTER_DATA)
    found = await rates.get_card(db, _key(card))
    if found.status == "draft" and not await may(
        decider, subject, Action.MANAGE_RATES, _CARDS
    ):
        # A draft is the beheerder's work in progress; for anyone else it
        # does not exist yet.
        raise NotFoundError("Tarievenkaart", card)
    return await filtered(decider, subject, _CARDS, _card_out(found))


@router.post("/cards", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_rate_card(
    body: RateCardCreate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start a rate card as a draft, from any date, optionally as a copy.

    "Nieuwe tarievenkaart vanaf <datum>": ``valid_from`` with
    ``copy_previous`` and an increase gives an indexed copy of the card
    valid just before it. A draft prices nothing until it is activated.
    """
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    if body.valid_from is None and body.year is None:
        raise DomainValidationError("Geef de datum waarop de tarievenkaart ingaat.")
    valid_from = body.valid_from or date(body.year, 1, 1)  # type: ignore[arg-type]
    valid_to = body.valid_to
    if body.valid_from is None:
        valid_to = date(valid_from.year, 12, 31)
    source: rates.CardKey | None = body.copy_from_id or body.copy_from
    if body.increase_pct is not None and (source is not None or body.copy_previous):
        created = await rate_indexation.create_indexed_card(
            db,
            valid_from=valid_from,
            valid_to=valid_to,
            name=body.name,
            copy_from=source,
            increase_pct=body.increase_pct,
            rounding=body.rounding,
            actor=person,
        )
    else:
        created = await rates.create_card(
            db,
            valid_from=valid_from,
            valid_to=valid_to,
            name=body.name,
            copy_from=source,
            copy_previous=body.copy_previous and source is None,
            actor=person,
        )
    card = await _fresh_card(db, created.id)
    return await filtered(decider, subject, _CARDS, _card_out(card))


@router.patch("/cards/{card}", response_model=None)
async def update_rate_card(
    card: CardRef,
    body: RateCardUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Rename a card or change its end date."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    sent = body.model_fields_set
    updated = await rates.update_card(
        db,
        _key(card),
        actor=person,
        name=body.name,
        valid_to=body.valid_to,
        clear_valid_to="valid_to" in sent and body.valid_to is None,
        allow_closed_year=body.confirm_closed_year,
    )
    fresh = await _fresh_card(db, updated.id)
    return await filtered(decider, subject, _CARDS, _card_out(fresh))


@router.get("/cards/{card}/activation-preview", response_model=None)
async def preview_activation(
    card: CardRef,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What activating a draft card does, before it is done.

    Which card it ends, how many budget lines and how much inzet get another
    amount from its start date and by how much, and what it does to months
    that are already closed or delivered. Saves nothing.
    """
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    found, shortened, impact = await rates.activation_preview(db, _key(card))
    gaps = await rates.gaps_after_activation(db, found)
    value = ActivationPreviewOut(
        card=_card_out(found),
        gaps=[RateGapOut(**gap) for gap in gaps],
        shortened=ShortenedCardOut(**shortened) if shortened else None,
        impact=_impact_out(impact),
    )
    return await filtered(decider, subject, _CARDS, value)


async def _set_status(
    db: AsyncSession, card: str, new_status: str, person: Any, confirm: bool
) -> RateCard:
    changed = await rates.set_rate_card_status(
        db, _key(card), new_status, actor=person, allow_closed_year=confirm
    )
    return await _fresh_card(db, changed.id)


@router.post("/cards/{card}/activate", response_model=None)
async def activate_rate_card(
    card: CardRef,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    body: ClosedYearConfirmation | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Make a draft card price. The card valid until then ends the day before."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    confirm = bool(body and body.confirm_closed_year)
    fresh = await _set_status(db, card, "active", person, confirm)
    return await filtered(decider, subject, _CARDS, _card_out(fresh))


@router.post("/cards/{card}/close", response_model=None)
async def close_rate_card(
    card: CardRef,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Close a card: from then on a change in its period needs the override."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    fresh = await _set_status(db, card, "closed", person, False)
    return await filtered(decider, subject, _CARDS, _card_out(fresh))


@router.put("/cards/{card}/status", response_model=None)
async def set_rate_card_status(
    card: CardRef,
    body: RateCardStatusUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate, close or (with confirmation) reopen a rate card."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    fresh = await _set_status(db, card, body.status, person, body.confirm_closed_year)
    return await filtered(decider, subject, _CARDS, _card_out(fresh))


@router.put("/cards/{card}/bands/{category}", response_model=None)
async def set_rate_band(
    card: CardRef,
    category: Category,
    body: RateBandUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set the monthly rate per FTE of a category on a card."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    key = _key(card)
    await rates.set_rate_band(
        db,
        key,
        category,
        body.monthly_rate_cents,
        actor=person,
        allow_closed_year=body.confirm_closed_year,
    )
    fresh = await _fresh_card(db, key)
    return await filtered(decider, subject, _CARDS, _card_out(fresh))


@router.put("/cards/{card}/scales/{scale}", response_model=None)
async def set_scale_band(
    card: CardRef,
    scale: Scale,
    body: ScaleBandUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set the category a scale bills in on a card."""
    await require(decider, subject, Action.MANAGE_RATES, _CARDS)
    key = _key(card)
    await rates.set_scale_band(
        db,
        key,
        scale,
        body.category,
        actor=person,
        allow_closed_year=body.confirm_closed_year,
    )
    fresh = await _fresh_card(db, key)
    return await filtered(decider, subject, _CARDS, _card_out(fresh))
