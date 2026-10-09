"""Billability KPI per person: target, and realisation split in realised and forecast.

Class F: the beheerder sees everyone, a line manager the direct reports, a
person their own. The amounts come from the pricing service (R12 and R13).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import (
    Action,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    permitted_classes,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.reference_support import may
from grip.core import clock
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.person import Person
from grip.schema.kpi import KpiOut, KpiTargetUpdate
from grip.services import pricing, rates, team

router = APIRouter(prefix="/kpi", tags=["kpi"])

Year = Annotated[int, Path(ge=2000, le=2100)]
YearQuery = Annotated[int | None, Query(ge=2000, le=2100)]

_UNAVAILABLE = (
    "De KPI kan niet worden berekend: voor dit jaar ontbreekt een actieve "
    "tarievenkaart of een inzetschaal."
)


async def _kpi_out(db: AsyncSession, person: Person, year: int) -> KpiOut:
    try:
        overview = await pricing.kpi_overview(db, person.id, year)
    except calc.CalcError:
        return KpiOut(
            person_id=person.id,
            person_name=person.name,
            year=year,
            target_pct=None,
            target_cents=None,
            realised_cents=None,
            forecast_cents=None,
            realisation_cents=None,
            unavailable_reason=_UNAVAILABLE,
        )
    return KpiOut(
        person_id=person.id,
        person_name=person.name,
        year=year,
        target_pct=overview.target_pct,
        target_version=await rates.target_version(db, person.id, year),
        target_cents=overview.target_cents,
        realised_cents=overview.realised_cents,
        forecast_cents=overview.forecast_cents,
        realisation_cents=overview.realisation_cents,
        unavailable_reason=None,
    )


async def _visible(
    db: AsyncSession, decider: Decider, subject: Subject, person: Person, year: int
) -> dict[str, Any] | None:
    """The KPI of a person, or ``None`` when the subject may not see it."""
    permitted = await permitted_classes(
        decider, subject, Resource.person(person.id), schema_classes(KpiOut)
    )
    if DataClass.PERSON_KPI not in permitted:
        return None
    return build_response(await _kpi_out(db, person, year), permitted)


@router.get("", response_model=None)
async def list_kpi(
    subject: CurrentSubject,
    decider: AccessDecider,
    year: YearQuery = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The KPI of every person whose KPI the asker may see."""
    year = year or clock.today().year
    items: list[dict[str, Any]] = []
    for person in await team.list_persons(db):
        item = await _visible(db, decider, subject, person, year)
        if item is not None:
            items.append(item)
    return {
        "items": items,
        "year": year,
        "may_manage": await may(
            decider, subject, Action.MANAGE_USERS, Resource.person()
        ),
    }


@router.get("/{person_id}", response_model=None)
async def get_kpi(
    person_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    year: YearQuery = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    person = await db.get(Person, person_id)
    item = (
        await _visible(db, decider, subject, person, year or clock.today().year)
        if person is not None
        else None
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Niet gevonden")
    return item


@router.put("/{person_id}/{year}", response_model=None)
async def set_target(
    person_id: UUID,
    year: Year,
    body: KpiTargetUpdate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set the billability target of a person for a year."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    person = await team.get_person(db, person_id)
    await rates.set_billability_target(
        db,
        person_id,
        year,
        body.target_pct,
        actor=actor,
        allow_closed_year=body.confirm_closed_year,
    )
    item = await _visible(db, decider, subject, person, year)
    assert item is not None
    return item
