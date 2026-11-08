"""Search across assignments, vacancies and people.

The answer holds only what the reader may open, and says nothing about how
much more there is: no total, no count. A person is found by the same
decision that puts them in the list of people, so a link from a hit works.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from grip.access import Action, Context, DataClass, Resource, build_response
from grip.access.deps import AccessDecider
from grip.api.assignment_support import DbSession, RequestAccess
from grip.api.reference_support import period_or_today
from grip.api.routes.people import permitted_for_person
from grip.api.vacancy_support import resource as vacancy_resource
from grip.models.vacancy import Vacancy
from grip.schema.search import (
    SearchAssignmentOut,
    SearchPersonOut,
    SearchVacancyOut,
)
from grip.services import search, team

router = APIRouter(prefix="/search", tags=["search"])

_MIN_LENGTH = 2


@router.get("", response_model=None)
async def search_everything(
    access: RequestAccess,
    decider: AccessDecider,
    db: DbSession,
    q: str = Query(min_length=_MIN_LENGTH, max_length=100),
) -> dict[str, Any]:
    """Assignments, vacancies and people whose name contains ``q``.

    At most twenty of each kind, taken after the access decision.
    """
    words = q.strip()
    if len(words) < _MIN_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Zoek op minstens twee tekens.",
        )

    async def assignment_allowed(assignment_id: UUID) -> bool:
        return await access.may(
            Action.READ,
            Resource.assignment(assignment_id),
            DataClass.ASSIGNMENT_BASIC,
        )

    async def vacancy_allowed(vacancy: Vacancy, assignment_id: UUID | None) -> bool:
        return await access.may(
            Action.READ,
            vacancy_resource(vacancy, assignment_id),
            DataClass.OPEN_ROLE,
        )

    period = period_or_today(None, None)
    context = Context(period=period)
    staffed_on = await team.assignments_by_person(db, period)

    async def person_allowed(person_id: UUID) -> bool:
        permitted = await permitted_for_person(
            decider,
            access.subject,
            person_id,
            staffed_on.get(person_id, ()),
            context,
        )
        return DataClass.STAFFING_ROSTER in permitted

    only_ids = (
        None
        if await access.may(
            Action.READ, Resource.assignment(), DataClass.ASSIGNMENT_BASIC
        )
        else await access.own_assignment_ids()
    )
    return {
        "q": words,
        "assignments": [
            build_response(
                SearchAssignmentOut(
                    id=row.assignment.id,
                    name=row.assignment.name,
                    client_name=row.client_name,
                    phase=row.phase.value,
                ),
                {DataClass.ASSIGNMENT_BASIC},
            )
            for row in await search.assignments(
                db, words, only_ids=only_ids, allowed=assignment_allowed
            )
        ],
        "vacancies": [
            build_response(
                SearchVacancyOut(id=vacancy.id, title=vacancy.function_title),
                {DataClass.OPEN_ROLE},
            )
            for vacancy in await search.vacancies(db, words, allowed=vacancy_allowed)
        ],
        "people": [
            build_response(
                SearchPersonOut(id=person_id, name=name),
                {DataClass.STAFFING_ROSTER},
            )
            for person_id, name in await search.people(
                db, words, allowed=person_allowed
            )
        ],
    }
