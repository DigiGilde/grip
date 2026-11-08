"""Billability KPI per person: target, and realisation split in realised and forecast.

Class F: the beheerder sees everyone, a line manager the direct reports, a
person their own. The amounts come from the pricing service (R12 and R13).
"""

from __future__ import annotations

from dataclasses import asdict
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
from grip.schema.kpi import KpiOut, KpiTargetUpdate, KpiTotalsOut
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
        gap_cents=overview.gap_cents,
        unavailable_reason=None,
    )


async def _visible(
    db: AsyncSession, decider: Decider, subject: Subject, person: Person, year: int
) -> tuple[KpiOut, set[DataClass]] | None:
    """The KPI of a person with the classes the subject may read, or ``None``."""
    permitted = await permitted_classes(
        decider, subject, Resource.person(person.id), schema_classes(KpiOut)
    )
    if DataClass.PERSON_KPI not in permitted:
        return None
    return await _kpi_out(db, person, year), permitted


@router.get("", response_model=None)
async def list_kpi(
    subject: CurrentSubject,
    decider: AccessDecider,
    year: YearQuery = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The KPI of every person whose KPI the asker may see, below target first."""
    year = year or clock.today().year
    visible: list[tuple[KpiOut, set[DataClass]]] = []
    for person in await team.list_persons(db):
        found = await _visible(db, decider, subject, person, year)
        if found is not None:
            visible.append(found)
    classes = {id(kpi): permitted for kpi, permitted in visible}
    ordered = pricing.below_target_first(kpi for kpi, _ in visible)
    return {
        "items": [build_response(kpi, classes[id(kpi)]) for kpi in ordered],
        "totals": build_response(
            KpiTotalsOut(**asdict(pricing.kpi_totals(ordered))), {DataClass.PERSON_KPI}
        )
        if ordered
        else None,
        "scope": "all"
        if await may(
            decider,
            subject,
            Action.READ,
            Resource.person(),
            DataClass.PERSON_KPI,
        )
        else "own",
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
    found = (
        await _visible(db, decider, subject, person, year or clock.today().year)
        if person is not None
        else None
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Niet gevonden")
    return build_response(*found)


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
    return build_response(*item)
