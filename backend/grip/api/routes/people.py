"""Persons: who is on the team, scale history, hire and functions.

A list shows, per person, only what the asker may see of that person. Who
someone is comes from the person itself; the billing scale and the cost side
of hire can also follow from an assignment the asker manages, and then only
for people staffed on it in the period on screen. The route enumerates those
assignments; whether they grant anything is the decider's call.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import (
    Action,
    Context,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    permitted_classes,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.reference_support import may, period_or_today
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.person import Person
from grip.models.person_details import Hire, PersonScale
from grip.schema.people import (
    FunctionGrantOut,
    HireCreate,
    HireOut,
    HireWithdrawal,
    PersonCreate,
    PersonOut,
    PersonUpdate,
    ScaleCreate,
    ScaleOut,
    StartDateUpdate,
)
from grip.services import rates, standing, team
from grip.services.errors import NotFoundError

router = APIRouter(prefix="/people", tags=["people"])

_PERSON_CLASSES = schema_classes(PersonOut)
# What an assignment can add to what the person resource already gives.
_VIA_ASSIGNMENT = frozenset(
    {DataClass.STAFFING_ROSTER, DataClass.PERSON_RATE, DataClass.PERSON_COST}
)


async def permitted_for_person(
    decider: Decider,
    subject: Subject,
    person_id: UUID,
    staffed_on: Iterable[UUID],
    context: Context,
    classes: frozenset[DataClass] = _PERSON_CLASSES,
) -> frozenset[DataClass]:
    """The classes the subject may read about a person, in the period shown."""
    permitted = set(
        await permitted_classes(
            decider, subject, Resource.person(person_id), classes, context
        )
    )
    missing = (classes & _VIA_ASSIGNMENT) - permitted
    for assignment_id in staffed_on:
        if not missing:
            break
        granted = await permitted_classes(
            decider,
            subject,
            Resource.allocation(assignment_id, person_id),
            missing,
            context,
        )
        permitted |= granted
        missing -= granted
    return frozenset(permitted)


def _current_hire(hires: list[Hire], day: date) -> Hire | None:
    current = [
        h
        for h in hires
        if h.valid_from <= day and (h.valid_to is None or h.valid_to >= day)
    ]
    return max(current, key=lambda h: h.valid_from) if current else None


async def _person_out(
    db: AsyncSession,
    person: Person,
    *,
    names: dict[UUID, str],
    functions: list[str],
    grants: list[team.FunctionGrant],
    sole_beheerder_id: UUID | None,
    staffing: team.CurrentStaffing | None,
    scales: list[PersonScale],
    hires: list[Hire],
    rate_book: calc.RateBook,
    day: date,
    standing_view: standing.StandingView | None = None,
) -> PersonOut:
    facts = team.rate_facts(rate_book, scales, person.id, day)
    hire = _current_hire(hires, day)
    margin: int | None = None
    if hire is not None:
        try:
            result = await rates.hire_margin(db, person.id, calc.Month.of(day))
        except calc.CalcError:
            result = None
        margin = result[2] if result is not None else None
    return PersonOut(
        id=person.id,
        name=person.name,
        email=person.email,
        is_active=person.is_active,
        uri=person.uri,
        stage=(standing_view.stage if standing_view else "colleague"),
        starts_on=(
            standing_view.start_date
            if standing_view and standing_view.is_prospective
            else None
        ),
        can_log_in=bool(person.email) and person.is_active,
        manager_id=person.manager_id,
        manager_name=names.get(person.manager_id) if person.manager_id else None,
        functions=functions,
        function_grants=[
            FunctionGrantOut(
                function=g.function, since=g.since, granted_by_name=g.granted_by_name
            )
            for g in grants
        ],
        is_sole_beheerder=sole_beheerder_id == person.id,
        is_hired=hire is not None,
        current_assignment_count=staffing.assignment_count if staffing else 0,
        current_fte_pct=staffing.fte_pct if staffing else Decimal(0),
        billing_scale=facts.billing_scale,
        rate_category=facts.category,
        monthly_rate_cents=facts.monthly_rate_cents,
        scales=[
            ScaleOut(
                id=s.id,
                valid_from=s.valid_from,
                valid_to=s.valid_to,
                billing_scale=s.billing_scale,
            )
            for s in scales
        ],
        cost_monthly_rate_cents=hire.cost_monthly_rate_cents if hire else None,
        margin_monthly_cents=margin,
        hires=[
            HireOut(
                id=h.id,
                supplier=h.supplier,
                cost_monthly_rate_cents=h.cost_monthly_rate_cents,
                valid_from=h.valid_from,
                valid_to=h.valid_to,
                contract_reference=h.contract_reference,
                notes=h.notes,
            )
            for h in hires
        ],
    )


async def _visible_persons(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    persons: list[Person],
    period: tuple[date, date],
) -> list[dict[str, Any]]:
    """Each person as the subject may see them; persons with nothing are left out."""
    context = Context(period=period)
    ids = [p.id for p in persons]
    all_names = {
        p.id: p.name for p in await team.list_persons(db, include_inactive=True)
    }
    functions = await team.functions_by_person(db)
    grants = await team.function_grants_by_person(db)
    sole_beheerder_id = await team.sole_beheerder_id(db)
    staffing = await team.staffing_by_person(db, period[0])
    scales = await team.scales_by_person(db, ids)
    hires = await team.hires_by_person(db, ids)
    staffed_on = await team.assignments_by_person(db, period)
    rate_book = await team.load_rates(db)
    standings = await standing.standings_by_person(db, ids)

    result: list[dict[str, Any]] = []
    for person in persons:
        permitted = await permitted_for_person(
            decider, subject, person.id, staffed_on.get(person.id, ()), context
        )
        if not permitted:
            continue
        value = await _person_out(
            db,
            person,
            names=all_names,
            functions=functions.get(person.id, []),
            grants=grants.get(person.id, []),
            sole_beheerder_id=sole_beheerder_id,
            staffing=staffing.get(person.id),
            scales=scales.get(person.id, []),
            hires=hires.get(person.id, []),
            rate_book=rate_book,
            day=period[0],
            standing_view=standings.get(person.id),
        )
        result.append(build_response(value, permitted))
    return result


async def _one(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    person_id: UUID,
    period: tuple[date, date],
) -> dict[str, Any]:
    person = await db.get(Person, person_id)
    visible = (
        await _visible_persons(db, decider, subject, [person], period)
        if person is not None
        else []
    )
    if not visible:
        # Someone the asker may see nothing of answers like someone who does
        # not exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Niet gevonden")
    return visible[0]


@router.get("", response_model=None)
async def list_people(
    subject: CurrentSubject,
    decider: AccessDecider,
    period_start: date | None = None,
    period_end: date | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The persons the asker may see, each with the fields allowed for them.

    The period bounds who counts as staffed on an assignment of the asker,
    and its first day is the day the scale, rate and hire are shown for.
    """
    period = period_or_today(period_start, period_end)
    persons = await team.list_persons(db, include_inactive=include_inactive)
    return {
        "items": await _visible_persons(db, decider, subject, persons, period),
        "may_manage": await may(
            decider, subject, Action.MANAGE_USERS, Resource.person()
        ),
        "period_start": period[0].isoformat(),
        "period_end": period[1].isoformat(),
    }


@router.get("/{person_id}", response_model=None)
async def get_person(
    person_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    period_start: date | None = None,
    period_end: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    period = period_or_today(period_start, period_end)
    return await _one(db, decider, subject, person_id, period)


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_person(
    body: PersonCreate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require(decider, subject, Action.MANAGE_USERS, Resource.person())
    person = await team.create_person(
        db,
        name=body.name,
        email=body.email,
        manager_id=body.manager_id,
        actor=actor,
        start_date=body.start_date,
        suborganization=body.suborganization,
        source_ref=body.source_ref,
        source_url=body.source_url,
    )
    return await _one(db, decider, subject, person.id, period_or_today(None, None))


@router.put("/{person_id}/start-date", response_model=None)
async def set_start_date(
    person_id: UUID,
    body: StartDateUpdate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Move the start date of a prospective colleague."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await standing.set_start_date(db, person_id, body.start_date, actor=actor)
    return await _one(db, decider, subject, person_id, period_or_today(None, None))


@router.post("/{person_id}/withdraw-hire", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_hire(
    person_id: UUID,
    body: HireWithdrawal,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> None:
    """A recorded hire falls through: planning, proposal and person go."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await standing.withdraw_hire(db, person_id, actor=actor, reason=body.reason)


@router.patch("/{person_id}", response_model=None)
async def update_person(
    person_id: UUID,
    body: PersonUpdate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    changes: dict[str, object] = {
        name: getattr(body, name) for name in body.model_fields_set
    }
    # Null means "remove" only for the line manager.
    for name in ("name", "email", "is_active"):
        if name in changes and changes[name] is None:
            del changes[name]
    await team.update_person(db, person_id, actor=actor, changes=changes)
    return await _one(db, decider, subject, person_id, period_or_today(None, None))


@router.get("/{person_id}/login", response_model=None)
async def login_state(
    person_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Whether the person's login is bound to an account of the provider.

    For the beheerder only, and only the fact: the subject is never shown.
    """
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    person = await team.get_person(db, person_id)
    return {"bound": person.oidc_subject is not None}


@router.delete("/{person_id}/login", response_model=None)
async def unbind_login(
    person_id: UUID,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Unbind the login, so the next login with the verified email binds again."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await team.unbind_login(db, person_id, actor=actor)
    return {"bound": False}


@router.post(
    "/{person_id}/scales", response_model=None, status_code=status.HTTP_201_CREATED
)
async def add_scale(
    person_id: UUID,
    body: ScaleCreate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record the billing scale of a person from a date on."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await rates.set_person_scale(
        db,
        person_id,
        body.valid_from,
        body.billing_scale,
        valid_to=body.valid_to,
        actor=actor,
        allow_closed_year=body.confirm_closed_year,
    )
    return await _one(db, decider, subject, person_id, period_or_today(None, None))


@router.post(
    "/{person_id}/hires", response_model=None, status_code=status.HTTP_201_CREATED
)
async def add_hire(
    person_id: UUID,
    body: HireCreate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record the cost side of a hired person for a period."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await rates.add_hire(
        db,
        person_id,
        supplier=body.supplier,
        cost_monthly_rate_cents=body.cost_monthly_rate_cents,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        contract_reference=body.contract_reference,
        notes=body.notes,
        actor=actor,
    )
    return await _one(db, decider, subject, person_id, period_or_today(None, None))


@router.delete("/{person_id}/hires/{hire_id}", response_model=None)
async def remove_hire(
    person_id: UUID,
    hire_id: UUID,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    hire = await db.get(Hire, hire_id)
    if hire is None or hire.person_id != person_id:
        raise NotFoundError("Inhuur", hire_id)
    await rates.remove_hire(db, hire_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{person_id}/functions/{function}", response_model=None)
async def grant_function(
    person_id: UUID,
    function: str,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Let a person hold a function from today."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await team.grant_function(db, person_id, function, actor=actor)
    return await _one(db, decider, subject, person_id, period_or_today(None, None))


@router.delete("/{person_id}/functions/{function}", response_model=None)
async def revoke_function(
    person_id: UUID,
    function: str,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """End a function a person holds."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    await team.revoke_function(db, person_id, function, actor=actor)
    return await _one(db, decider, subject, person_id, period_or_today(None, None))
