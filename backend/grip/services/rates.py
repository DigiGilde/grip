"""Rate cards, billing scales, targets and hire: master data with an audit trail."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.person import Person
from grip.models.person_details import BillabilityTarget, Hire, PersonScale
from grip.models.rates import (
    RATE_CARD_STATUSES,
    RATE_CATEGORIES,
    RateBand,
    RateCard,
    ScaleBand,
)
from grip.repositories.domain import PersonDetailRepository, RateRepository
from grip.services.errors import (
    ClosedYearError,
    DomainValidationError,
    NotFoundError,
)
from grip.services.guards import audit_fields, ensure_years_open, years_between
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    load_rate_book,
    to_calc_scale,
)

_SCALE_FIELDS = ("person_id", "valid_from", "valid_to", "billing_scale")
_HIRE_FIELDS = (
    "person_id",
    "supplier",
    "cost_monthly_rate_cents",
    "valid_from",
    "valid_to",
    "contract_reference",
)

# draft -> active -> closed. Reopening a closed card is a closed-card change.
_STATUS_ORDER = {"draft": 0, "active": 1, "closed": 2}

# A card is named by its id. A bare year still names the card that starts on
# 1 January of it, for callers from before a card had a validity.
CardKey = int | UUID

_MONTH_NAMES = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)


def date_text(day: date) -> str:
    return f"{day.day} {_MONTH_NAMES[day.month - 1]} {day.year}"


def default_card_name(valid_from: date, valid_to: date | None) -> str:
    """ "Tarieven 2026" for a calendar year, else "Tarieven vanaf 1 juli 2026"."""
    if (
        valid_from.month == 1
        and valid_to is not None
        and valid_to == date(valid_from.year, 12, 31)
    ):
        return f"Tarieven {valid_from.year}"
    return f"Tarieven vanaf {date_text(valid_from)}"


def check_validity(valid_from: date, valid_to: date | None) -> None:
    """A card is valid from a date to a date, any date."""
    if valid_to is not None and valid_to < valid_from:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")


def card_audit(card: RateCard) -> dict[str, Any]:
    return {
        "name": card.name,
        "valid_from": card.valid_from.isoformat(),
        "valid_to": card.valid_to.isoformat() if card.valid_to else None,
        "status": card.status,
    }


async def get_card(session: AsyncSession, key: CardKey) -> RateCard:
    card = await RateRepository(session).get_card(key)
    if card is None:
        raise NotFoundError("Tarievenkaart", key)
    return card


_card = get_card


async def _check_start_free(session: AsyncSession, valid_from: date) -> None:
    for card in await RateRepository(session).all_cards():
        if card.valid_from == valid_from:
            when = (
                str(valid_from.year)
                if card.spans_calendar_year
                else f"vanaf {date_text(valid_from)}"
            )
            raise DomainValidationError(f"Er is al een tarievenkaart voor {when}.")


async def previous_card(session: AsyncSession, valid_from: date) -> RateCard | None:
    """The card that prices the day before ``valid_from``, or else the last
    one that started before it."""
    before = [
        card
        for card in await RateRepository(session).pricing_cards()
        if card.valid_from < valid_from
    ]
    return before[-1] if before else None


def _copy_bands(card: RateCard, source: RateCard) -> None:
    for band in source.rate_bands:
        card.rate_bands.append(
            RateBand(category=band.category, monthly_rate_cents=band.monthly_rate_cents)
        )
    for scale in source.scale_bands:
        card.scale_bands.append(ScaleBand(scale=scale.scale, category=scale.category))


async def create_card(
    session: AsyncSession,
    *,
    valid_from: date,
    actor: Person | None,
    valid_to: date | None = None,
    name: str | None = None,
    copy_from: CardKey | None = None,
    copy_previous: bool = False,
    indexed_rates: dict[str, int] | None = None,
    audit_extra: dict[str, Any] | None = None,
) -> RateCard:
    """Start a rate card from a date, as a draft.

    With ``copy_from`` the rates and the scale mapping of that card are
    copied; with ``copy_previous`` those of the card valid just before the
    start. A draft prices nothing and may overlap the card it will follow;
    activating it is what ends that card (``set_rate_card_status``).
    """
    check_validity(valid_from, valid_to)
    await _check_start_free(session, valid_from)
    source = None
    if copy_from is not None:
        source = await get_card(session, copy_from)
    elif copy_previous:
        source = await previous_card(session, valid_from)
        if source is None:
            raise DomainValidationError(
                "Er is geen eerdere tarievenkaart om van uit te gaan."
            )
    card = RateCard(
        name=(name or "").strip() or default_card_name(valid_from, valid_to),
        valid_from=valid_from,
        valid_to=valid_to,
        status="draft",
    )
    if source is not None:
        _copy_bands(card, source)
        for band in card.rate_bands:
            if indexed_rates and band.category in indexed_rates:
                band.monthly_rate_cents = indexed_rates[band.category]
    session.add(card)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="rate_card",
        entity_id=card.id,
        new_value={
            **card_audit(card),
            "copied_from": str(source.id) if source else None,
            "copied_from_name": source.name if source else None,
            **(audit_extra or {}),
        },
    )
    return await get_card(session, card.id)


async def create_rate_card(
    session: AsyncSession,
    year: int,
    *,
    actor: Person | None,
    copy_from: CardKey | None = None,
) -> RateCard:
    """Create the card of a calendar year as a draft: 1 January to 31 December.

    The shape from before a card had a validity; ``create_card`` starts a
    card on any first of a month.
    """
    return await create_card(
        session,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
        actor=actor,
        copy_from=copy_from,
    )


async def _shorten_for(
    session: AsyncSession, card: RateCard, *, allow_closed_year: bool
) -> dict[str, Any] | None:
    """Make room for a card that is about to price: end the card before it.

    Returns what was shortened, for the audit row of the activation. Cards
    that price never overlap, so anything else in the way is a refusal.
    """
    shortened = None
    new_end = card.valid_to or date.max
    for other in await RateRepository(session).pricing_cards():
        if other.id == card.id:
            continue
        other_end = other.valid_to or date.max
        if other.valid_from > new_end or other_end < card.valid_from:
            continue
        if other.valid_from < card.valid_from:
            # The card valid until now: it ends the day before the new one.
            if other.status == "closed" and not allow_closed_year:
                raise ClosedYearError(other.valid_from.year, other.name)
            old_end = other.valid_to
            other.valid_to = card.valid_from - timedelta(days=1)
            shortened = {
                "id": str(other.id),
                "name": other.name,
                "old_valid_to": old_end.isoformat() if old_end else None,
                "new_valid_to": other.valid_to.isoformat(),
            }
            continue
        if other.valid_from == card.valid_from:
            raise DomainValidationError(
                f"Vanaf {date_text(card.valid_from)} geldt al de tarievenkaart "
                f"'{other.name}'. Pas die kaart aan, of kies een andere begindatum."
            )
        raise DomainValidationError(
            f"De tarievenkaart '{other.name}' gaat in op "
            f"{date_text(other.valid_from)}. Geef deze kaart een einddatum van "
            f"uiterlijk {date_text(other.valid_from - timedelta(days=1))}."
        )
    if shortened is not None:
        # Before the new card starts to price, or the two would overlap.
        await session.flush()
    return shortened


async def set_rate_card_status(
    session: AsyncSession,
    key: CardKey,
    status: str,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> RateCard:
    """Activate, close or (with the override) reopen a rate card.

    Activating a card ends the card valid until then on the day before, in
    the same transaction, and the one audit row says which card was
    shortened. From the start date every open month is priced by the new
    card. Closed months price from it too (their amount is computed, only
    the percentage is stored); what was already delivered stays as it is and
    the difference becomes a correction to deliver
    (``grip.services.price_changes``).
    """
    if status not in RATE_CARD_STATUSES:
        raise DomainValidationError(
            f"Onbekende status voor een tarievenkaart: {status}"
        )
    card = await get_card(session, key)
    if card.status == status:
        return card
    if _STATUS_ORDER[status] < _STATUS_ORDER[card.status]:
        if card.status == "closed":
            if not allow_closed_year:
                raise ClosedYearError(card.valid_from.year, card.name)
        elif status == "draft":
            raise DomainValidationError(
                "Een actieve tarievenkaart kan niet terug naar concept."
            )
    old = card.status
    shortened = None
    pending = None
    if old == "draft":
        # Imported here: that module prices, and pricing reads this one.
        from grip.services import price_changes

        pending = await price_changes.pending_corrections(session)
        shortened = await _shorten_for(
            session, card, allow_closed_year=allow_closed_year
        )
    card.status = status
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="rate_card",
        entity_id=card.id,
        old_value={"status": old},
        new_value={
            "status": status,
            "name": card.name,
            **({"shortened": shortened} if shortened else {}),
        },
    )
    if pending is not None:
        from grip.services import price_changes

        await price_changes.emit_new_corrections(
            session, pending, cause=f"tarievenkaart '{card.name}' is ingegaan"
        )
    return card


async def update_card(
    session: AsyncSession,
    key: CardKey,
    *,
    actor: Person | None,
    name: str | None = None,
    valid_to: date | None = None,
    clear_valid_to: bool = False,
    allow_closed_year: bool = False,
) -> RateCard:
    """Rename a card or change its end date. The start date is its identity
    in time and does not change; start a new card instead."""
    card = await get_card(session, key)
    if card.status == "closed" and not allow_closed_year:
        raise ClosedYearError(card.valid_from.year, card.name)
    old = card_audit(card)
    if name is not None and name.strip():
        card.name = name.strip()
    if clear_valid_to or valid_to is not None:
        new_end = None if clear_valid_to else valid_to
        check_validity(card.valid_from, new_end)
        if card.status != "draft":
            limit = new_end or date.max
            for other in await RateRepository(session).pricing_cards():
                if other.id != card.id and card.valid_from < other.valid_from <= limit:
                    raise DomainValidationError(
                        f"De tarievenkaart '{other.name}' gaat in op "
                        f"{date_text(other.valid_from)}; deze kaart kan niet later "
                        "eindigen."
                    )
        card.valid_to = new_end
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="rate_card",
        entity_id=card.id,
        old_value=old,
        new_value=card_audit(card),
    )
    return card


async def _changeable_card(
    session: AsyncSession, key: CardKey, allow_closed_year: bool
) -> tuple[RateCard, list[str]]:
    card = await get_card(session, key)
    if card.status == "closed":
        if not allow_closed_year:
            raise ClosedYearError(card.valid_from.year, card.name)
        return card, [card.name]
    return card, []


async def set_rate_band(
    session: AsyncSession,
    key: CardKey,
    category: str,
    monthly_rate_cents: int,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> RateBand:
    """Set the monthly rate of a category on a card (create or change)."""
    if category not in RATE_CATEGORIES:
        raise DomainValidationError(f"Onbekende tariefcategorie: {category}")
    if monthly_rate_cents < 0:
        raise DomainValidationError("Een maandtarief kan niet negatief zijn.")
    card, closed = await _changeable_card(session, key, allow_closed_year)
    band = next((b for b in card.rate_bands if b.category == category), None)
    old = None
    if band is None:
        band = RateBand(
            rate_card_id=card.id,
            category=category,
            monthly_rate_cents=monthly_rate_cents,
        )
        session.add(band)
    else:
        old = {"monthly_rate_cents": band.monthly_rate_cents}
        band.monthly_rate_cents = monthly_rate_cents
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE if old else CREATE,
        entity="rate_band",
        entity_id=f"{card.id}/{category}",
        old_value=old,
        new_value={
            "monthly_rate_cents": monthly_rate_cents,
            "card": card.name,
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return band


async def set_scale_band(
    session: AsyncSession,
    key: CardKey,
    scale: int,
    category: str,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> ScaleBand:
    """Set the category a scale bills in on a card (create or change)."""
    if category not in RATE_CATEGORIES:
        raise DomainValidationError(f"Onbekende tariefcategorie: {category}")
    card, closed = await _changeable_card(session, key, allow_closed_year)
    band = next((b for b in card.scale_bands if b.scale == scale), None)
    old = None
    if band is None:
        band = ScaleBand(rate_card_id=card.id, scale=scale, category=category)
        session.add(band)
    else:
        old = {"category": band.category}
        band.category = category
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE if old else CREATE,
        entity="scale_band",
        entity_id=f"{card.id}/{scale}",
        old_value=old,
        new_value={
            "category": category,
            "card": card.name,
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return band


async def set_person_scale(
    session: AsyncSession,
    person_id: UUID,
    valid_from: date,
    billing_scale: int,
    *,
    actor: Person | None,
    valid_to: date | None = None,
    allow_closed_year: bool = False,
) -> PersonScale:
    """Record the billing scale of a person from a date on.

    An open-ended earlier period is ended on the day before ``valid_from``.
    Periods may not overlap.
    """
    if valid_to is not None and valid_to < valid_from:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    if await session.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    closed = await ensure_years_open(
        session,
        years_between(valid_from, valid_to or valid_from),
        allow_closed_year=allow_closed_year,
    )
    existing = await PersonDetailRepository(session).scales([person_id])
    for scale in existing:
        if scale.valid_from < valid_from and scale.valid_to is None:
            old = audit_fields(scale, _SCALE_FIELDS)
            scale.valid_to = valid_from - timedelta(days=1)
            record_audit(
                session,
                actor=actor,
                action=UPDATE,
                entity="person_scale",
                entity_id=scale.id,
                old_value=old,
                new_value=audit_fields(scale, _SCALE_FIELDS),
            )
    for scale in existing:
        ends = scale.valid_to or date.max
        new_ends = valid_to or date.max
        if scale.valid_from <= new_ends and ends >= valid_from:
            raise DomainValidationError(
                "Deze periode overlapt met een bestaande inzetschaal van de persoon."
            )
    scale = PersonScale(
        person_id=person_id,
        valid_from=valid_from,
        valid_to=valid_to,
        billing_scale=billing_scale,
    )
    session.add(scale)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="person_scale",
        entity_id=scale.id,
        new_value={
            **audit_fields(scale, _SCALE_FIELDS),
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return scale


async def set_billability_target(
    session: AsyncSession,
    person_id: UUID,
    year: int,
    target_pct: Decimal,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> BillabilityTarget:
    if not Decimal(0) <= target_pct <= Decimal(100):
        raise DomainValidationError("Een target ligt tussen 0 en 100 procent.")
    await ensure_years_open(session, [year], allow_closed_year=allow_closed_year)
    target = await PersonDetailRepository(session).target(person_id, year)
    old = None
    if target is None:
        target = BillabilityTarget(
            person_id=person_id, year=year, target_pct=target_pct
        )
        session.add(target)
    else:
        old = {"target_pct": str(target.target_pct)}
        target.target_pct = target_pct
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE if old else CREATE,
        entity="billability_target",
        entity_id=target.id,
        old_value=old,
        new_value={
            "person_id": str(person_id),
            "year": year,
            "target_pct": str(target_pct),
        },
    )
    return target


async def add_hire(
    session: AsyncSession,
    person_id: UUID,
    *,
    supplier: str,
    cost_monthly_rate_cents: int,
    valid_from: date,
    actor: Person | None,
    valid_to: date | None = None,
    contract_reference: str | None = None,
    notes: str | None = None,
) -> Hire:
    """Record the cost side of a hired person (data class E)."""
    if valid_to is not None and valid_to < valid_from:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    if cost_monthly_rate_cents < 0:
        raise DomainValidationError("Een kostprijs kan niet negatief zijn.")
    if await session.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    hire = Hire(
        person_id=person_id,
        supplier=supplier,
        cost_monthly_rate_cents=cost_monthly_rate_cents,
        valid_from=valid_from,
        valid_to=valid_to,
        contract_reference=contract_reference,
        notes=notes,
    )
    session.add(hire)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="hire",
        entity_id=hire.id,
        new_value=audit_fields(hire, _HIRE_FIELDS),
    )
    return hire


async def remove_hire(
    session: AsyncSession, hire_id: UUID, *, actor: Person | None
) -> None:
    hire = await session.get(Hire, hire_id)
    if hire is None:
        raise NotFoundError("Inhuur", hire_id)
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="hire",
        entity_id=hire.id,
        old_value=audit_fields(hire, _HIRE_FIELDS),
    )
    await session.delete(hire)
    await session.flush()


async def hire_margin(
    session: AsyncSession,
    person_id: UUID,
    month: calc.Month,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> tuple[int, int, int] | None:
    """Billing rate, cost rate and margin per FTE for a month, in cents.

    None when the person is not hired in that month. The billing rate comes
    from the calculation module (R1); the margin is the difference.
    """
    result = await session.execute(
        select(Hire).where(
            Hire.person_id == person_id,
            Hire.valid_from <= month.last_day,
        )
    )
    hires = [
        h
        for h in result.scalars()
        if h.valid_to is None or h.valid_to >= month.first_day
    ]
    if not hires:
        return None
    hire = max(hires, key=lambda h: h.valid_from)
    scales = tuple(
        to_calc_scale(s)
        for s in await PersonDetailRepository(session).scales([person_id])
    )
    rates = await load_rate_book(session, include_draft=options.include_draft)
    billing = calc.person_monthly_rate(rates, scales, str(person_id), month)
    return billing, hire.cost_monthly_rate_cents, billing - hire.cost_monthly_rate_cents
