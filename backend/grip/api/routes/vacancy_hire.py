"""The recruitment reference of a vacancy, and the hire that fills it.

Grip keeps no candidates: selection happens in the recruitment system. These
routes hold the link to the vacancy there and record the hire, which is the
moment a person enters grip. See docs/wies.md and ADR 0022.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import DataClass, build_response
from grip.access.deps import AccessDecider, CurrentSubject
from grip.api.routes.vacancies import _load_for_edit
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.person import Person
from grip.schema.vacancy_hire import (
    HireIn,
    HireOut,
    HireWithdrawalIn,
    ProposedAllocationOut,
    RecruitmentRefIn,
    RecruitmentRefOut,
    VacancyHireOut,
)
from grip.services import standing, vacancy_hire

router = APIRouter(prefix="/vacancies", tags=["vacancies"])

_CLASSES = frozenset({DataClass.STAFFING})


async def _response(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    proposed: vacancy_hire.ProposedAllocation | None = None,
    allocation_id: UUID | None = None,
) -> dict[str, Any]:
    ref = await vacancy_hire.get_recruitment_ref(db, vacancy_id)
    hire = await vacancy_hire.get_hire(db, vacancy_id)
    hire_out = None
    if hire is not None:
        person = await db.get(Person, hire.person_id) if hire.person_id else None
        view = await standing.get_standing(db, person.id) if person else None
        hire_out = HireOut(
            person_id=person.id if person else None,
            person_name=person.name if person else None,
            start_date=hire.start_date,
            stage=view.stage if view else None,
            proposed_allocation=ProposedAllocationOut(
                budget_line_id=proposed.budget_line_id,
                start_date=proposed.start_date,
                end_date=proposed.end_date,
                fte_pct=format(proposed.fte_pct.normalize(), "f"),
            )
            if proposed is not None and allocation_id is None
            else None,
            allocation_id=allocation_id,
        )
    return build_response(
        VacancyHireOut(
            vacancy_id=vacancy_id,
            recruitment_ref=RecruitmentRefOut(
                system=ref.system, reference=ref.reference, url=ref.url
            )
            if ref
            else None,
            hire=hire_out,
        ),
        _CLASSES,
    )


@router.get("/{vacancy_id}/hire", response_model=None)
async def get_hire(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The reference in the recruitment system and who was hired.

    For who may edit the vacancy: both name a system and a person that the
    open-roles view of every colleague has no business showing.
    """
    await _load_for_edit(db, decider, subject, vacancy_id)
    return await _response(db, vacancy_id)


@router.put("/{vacancy_id}/recruitment-ref", response_model=None)
async def set_recruitment_ref(
    vacancy_id: UUID,
    body: RecruitmentRefIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Store or clear where this vacancy lives in the recruitment system."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await vacancy_hire.set_recruitment_ref(
        db,
        vacancy_id,
        reference=body.reference,
        url=body.url,
        system=body.system,
        actor=person,
    )
    return await _response(db, vacancy_id)


@router.post(
    "/{vacancy_id}/hire", response_model=None, status_code=status.HTTP_201_CREATED
)
async def record_hire(
    vacancy_id: UUID,
    body: HireIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record who was hired: the vacancy is filled and the person is planned."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    result = await vacancy_hire.record_hire(
        db,
        vacancy_id,
        start_date=body.start_date,
        actor=person,
        name=body.name,
        person_id=body.person_id,
        suborganization=body.suborganization,
        create_allocation=body.create_allocation,
        note=body.note,
    )
    return await _response(
        db,
        vacancy_id,
        proposed=result.proposed_allocation,
        allocation_id=result.allocation.id if result.allocation else None,
    )


@router.post("/{vacancy_id}/hire/withdraw", response_model=None)
async def withdraw_hire(
    vacancy_id: UUID,
    body: HireWithdrawalIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The hire does not go through."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await vacancy_hire.hire_fell_through(
        db, vacancy_id, actor=person, reason=body.reason
    )
    return await _response(db, vacancy_id)


__all__ = ["router"]
