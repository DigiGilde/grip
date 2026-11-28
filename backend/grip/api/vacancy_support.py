"""What the vacancy routes share: the resource of a vacancy, the classes a
reader may see and the loading of a vacancy for one reader."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import (
    Action,
    DataClass,
    Decider,
    Resource,
    Subject,
    permitted_classes,
)
from grip.access.deps import require
from grip.access.vacancies import vacancy_resource
from grip.models.vacancy import (
    DecisionKind,
    TextKind,
    Vacancy,
    VacancyStatus,
    VacancyText,
)
from grip.repositories.vacancy import VacancyRepository
from grip.services.errors import NotFoundError
from grip.services.vacancies import service

_VIEWS = (DataClass.STAFFING, DataClass.STAFFING_COUNTS, DataClass.OPEN_ROLE)


def established(vacancy: Vacancy, kind: TextKind) -> VacancyText | None:
    """The version of a text that was established last, from the loaded texts."""
    candidates = [
        text
        for text in vacancy.texts
        if text.kind == kind.value and text.established_at is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda text: (text.established_at, text.created_at))


def is_open_role(vacancy: Vacancy) -> bool:
    return (
        vacancy.status == VacancyStatus.open.value
        and vacancy.published_at is not None
        and established(vacancy, TextKind.vacancy_text) is not None
    )


def resource(
    vacancy: Vacancy,
    assignment_id: UUID | None,
    *,
    decision_kind: DecisionKind | None = None,
) -> Resource:
    return vacancy_resource(
        vacancy.id,
        assignment_id=assignment_id,
        open_role=is_open_role(vacancy),
        named={decision.kind: decision.person_id for decision in vacancy.decisions},
        decision_kind=decision_kind.value if decision_kind else None,
        text_reviewers=getattr(vacancy, "text_reviewer_ids", ()),
    )


async def permitted(
    decider: Decider, subject: Subject, resource: Resource
) -> frozenset[DataClass]:
    return await permitted_classes(decider, subject, resource, _VIEWS)


async def assignment_of(
    db: AsyncSession, vacancy: Vacancy
) -> tuple[UUID | None, str | None]:
    if vacancy.budget_line_id is None:
        return None, None
    found = await VacancyRepository(db).assignments_of_budget_lines(
        [vacancy.budget_line_id]
    )
    return found.get(vacancy.budget_line_id, (None, None))


async def load(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    vacancy_id: UUID,
) -> tuple[Vacancy, UUID | None]:
    """The vacancy and its assignment, or 404 when the viewer may not see it."""
    try:
        vacancy = await service.get_vacancy(db, vacancy_id)
    except NotFoundError:
        vacancy = None
    if vacancy is None:
        # Same answer as for a vacancy the viewer may not see.
        await require(
            decider,
            subject,
            Action.READ,
            vacancy_resource(vacancy_id),
            DataClass.STAFFING,
            hide_existence=True,
        )
        raise NotFoundError("Vacature", vacancy_id)
    assignment_id, _name = await assignment_of(db, vacancy)
    await require(
        decider,
        subject,
        Action.READ,
        resource(vacancy, assignment_id),
        DataClass.OPEN_ROLE,
        hide_existence=True,
    )
    return vacancy, assignment_id
