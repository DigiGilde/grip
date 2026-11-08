"""The parts of one vacancy and where each one stands."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, build_response, decide
from grip.access.deps import AccessDecider, CurrentSubject
from grip.api import vacancy_support
from grip.core import clock
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.schema.vacancy_parts import VacancyPartOut, VacancyPartsOut
from grip.services.vacancies import parts as vacancy_parts
from grip.tasks import engine
from grip.tasks.access import TaskAccess

router = APIRouter(tags=["vacancies"])


@router.get("/vacancies/{vacancy_id}/parts", response_model=None)
async def read_vacancy_parts(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The parts of a vacancy for this reader, in one order, each with its
    state. Who only reads the published text gets an empty list."""
    vacancy, assignment_id = await vacancy_support.load(
        db, decider, subject, vacancy_id
    )
    resource = vacancy_support.resource(vacancy, assignment_id)
    permitted = await vacancy_support.permitted(decider, subject, resource)
    if DataClass.STAFFING_COUNTS not in permitted:
        body = build_response(
            VacancyPartsOut(vacancy_id=vacancy_id, parts=[]), permitted
        )
        # build_response drops a list this reader may not see; the shape stays.
        body["parts"] = []
        return body
    can_edit = bool(await decide(decider, subject, Action.EDIT, resource))
    outcome = await engine.evaluate_vacancies(db, {vacancy_id})
    found = await vacancy_parts.parts_of(
        db,
        TaskAccess(db, decider, subject),
        vacancy,
        outcome.snapshots,
        can_edit=can_edit,
        sees_staffing=DataClass.STAFFING in permitted,
        today=clock.today(),
        instance_base_uri=settings.INSTANCE_BASE_URI,
    )
    return build_response(
        VacancyPartsOut(
            vacancy_id=vacancy_id,
            parts=[
                VacancyPartOut(
                    key=part.key,
                    label=part.label,
                    notice=part.notice,
                    state=part.state,
                )
                for part in found.parts
            ],
            tasks_link=found.tasks_link,
        ),
        permitted,
    )
