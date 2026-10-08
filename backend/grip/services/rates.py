"""Rate cards, billing scales, targets and hire: master data with an audit trail."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
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
from grip.services.errors import DomainValidationError, NotFoundError
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

# draft -> active -> closed. Reopening a closed card is a closed-year change.
_STATUS_ORDER = {"draft": 0, "active": 1, "closed": 2}


async def _card(session: AsyncSession, year: int) -> RateCard:
    card = await RateRepository(session).get_card(year)
    if card is None:
        raise NotFoundError("Tarievenkaart", year)
    return card


async def create_rate_card(
    session: AsyncSession,
    year: int,
    *,
    actor: Person | None,
    copy_from: int | None = None,
) -> RateCard:
    """Create the rate card of a year as a draft.

    With ``copy_from`` the rates and the scale mapping of that year are
    copied: a new year starts as a draft copy of the previous one.
    """
    repo = RateRepository(session)
    if await repo.get_card(year) is not None:
        raise DomainValidationError(f"Er is al een tarievenkaart voor {year}.")
    card = RateCard(year=year, status="draft")
    session.add(card)
    if copy_from is not None:
        source = await _card(session, copy_from)
        for band in source.rate_bands:
            session.add(
                RateBand(
                    year=year,
                    category=band.category,
                    monthly_rate_cents=band.monthly_rate_cents,
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
        new_value={"year": year, "status": "draft", "copied_from": copy_from},
    )
    card = await repo.get_card(year)
    assert card is not None
    return card


async def set_rate_card_status(
    session: AsyncSession,
    year: int,
    status: str,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> RateCard:
    if status not in RATE_CARD_STATUSES:
        raise DomainValidationError(
            f"Onbekende status voor een tarievenkaart: {status}"
        )
    card = await _card(session, year)
    if card.status == status:
        return card
    if _STATUS_ORDER[status] < _STATUS_ORDER[card.status]:
        if card.status == "closed":
            await ensure_years_open(
                session, [year], allow_closed_year=allow_closed_year
            )
        elif status == "draft":
            raise DomainValidationError(
                "Een actieve tarievenkaart kan niet terug naar concept."
            )
    old = card.status
    card.status = status
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="rate_card",
        entity_id=str(year),
        old_value={"status": old},
        new_value={"status": status},
    )
    return card


async def set_rate_band(
    session: AsyncSession,
    year: int,
    category: str,
    monthly_rate_cents: int,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> RateBand:
    """Set the monthly rate of a category in a year (create or change)."""
    if category not in RATE_CATEGORIES:
        raise DomainValidationError(f"Onbekende tariefcategorie: {category}")
    if monthly_rate_cents < 0:
        raise DomainValidationError("Een maandtarief kan niet negatief zijn.")
    card = await _card(session, year)
    closed = await ensure_years_open(
        session, [year], allow_closed_year=allow_closed_year
    )
    band = next((b for b in card.rate_bands if b.category == category), None)
    old = None
    if band is None:
        band = RateBand(
            year=year, category=category, monthly_rate_cents=monthly_rate_cents
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
        entity_id=f"{year}/{category}",
        old_value=old,
        new_value={
            "monthly_rate_cents": monthly_rate_cents,
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return band


async def set_scale_band(
    session: AsyncSession,
    year: int,
    scale: int,
    category: str,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> ScaleBand:
    """Set the category a scale bills in for a year (create or change)."""
    if category not in RATE_CATEGORIES:
        raise DomainValidationError(f"Onbekende tariefcategorie: {category}")
    card = await _card(session, year)
    closed = await ensure_years_open(
        session, [year], allow_closed_year=allow_closed_year
    )
    band = next((b for b in card.scale_bands if b.scale == scale), None)
    old = None
    if band is None:
        band = ScaleBand(year=year, scale=scale, category=category)
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
        entity_id=f"{year}/{scale}",
        old_value=old,
        new_value={
            "category": category,
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
