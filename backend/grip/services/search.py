"""Search across assignments, vacancies and people.

Every kind is searched first, then the caller decides per hit whether the
reader may see it, and only then is the list cut. A cut before the decision
would let the hits of other people push out what this reader may see, and
the length of an answer would say something about what is hidden.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.vacancy import Vacancy
from grip.repositories import search as repository
from grip.repositories.vacancy import VacancyRepository
from grip.services import assignment_views as views
from grip.services.vacancies import service as vacancy_service

# The most hits of one kind in an answer.
LIMIT = 20


async def _first_allowed[T](
    candidates: Iterable[T], allowed: Callable[[T], Awaitable[bool]]
) -> list[T]:
    kept: list[T] = []
    for candidate in candidates:
        if await allowed(candidate):
            kept.append(candidate)
            if len(kept) == LIMIT:
                break
    return kept


async def assignments(
    db: AsyncSession,
    words: str,
    *,
    only_ids: Iterable[UUID] | None,
    allowed: Callable[[UUID], Awaitable[bool]],
) -> list[views.AssignmentRow]:
    """Assignments whose name or client matches, that ``allowed`` lets through."""
    index = await views.assignment_index(db, only_ids=only_ids, search=words)
    kept = await _first_allowed((assignment_id for assignment_id, _ in index), allowed)
    return await views.assignment_rows(db, only_ids=kept)


async def vacancies(
    db: AsyncSession,
    words: str,
    *,
    allowed: Callable[[Vacancy, UUID | None], Awaitable[bool]],
) -> list[Vacancy]:
    """Vacancies whose function title matches, that ``allowed`` lets through.

    ``allowed`` gets the vacancy, carrying the people asked to review one of
    its texts, and the assignment of its budget line.
    """
    found = await repository.vacancies_titled(db, words)
    reviewers = await vacancy_service.text_reviewers(db, (v.id for v in found))
    for vacancy in found:
        vacancy.text_reviewer_ids = reviewers[vacancy.id]  # type: ignore[attr-defined]
    of_lines = await VacancyRepository(db).assignments_of_budget_lines(
        v.budget_line_id for v in found if v.budget_line_id is not None
    )

    async def _allowed(vacancy: Vacancy) -> bool:
        line_id = vacancy.budget_line_id
        of_line = of_lines.get(line_id) if line_id is not None else None
        return await allowed(vacancy, of_line[0] if of_line else None)

    return await _first_allowed(found, _allowed)


async def people(
    db: AsyncSession,
    words: str,
    *,
    allowed: Callable[[UUID], Awaitable[bool]],
) -> list[tuple[UUID, str]]:
    """The id and name of active persons whose name matches, that ``allowed``
    lets through."""
    found = await repository.active_persons_named(db, words)

    async def _allowed(person: tuple[UUID, str]) -> bool:
        return await allowed(person[0])

    return await _first_allowed(found, _allowed)
