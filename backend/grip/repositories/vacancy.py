"""Queries for vacancies and form templates. No business rules here."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from grip.models.assignment import Assignment, BudgetLine
from grip.models.person import Person
from grip.models.vacancy import (
    FormTemplate,
    Vacancy,
    VacancyDecision,
    VacancyStep,
    VacancyText,
)


class VacancyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, vacancy_id: UUID) -> Vacancy | None:
        result = await self.db.execute(
            select(Vacancy)
            .where(Vacancy.id == vacancy_id)
            .options(
                selectinload(Vacancy.steps),
                selectinload(Vacancy.decisions),
                selectinload(Vacancy.texts),
                selectinload(Vacancy.requester),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list(
        self, *, status: str | None = None, budget_line_id: UUID | None = None
    ) -> list[Vacancy]:
        query = select(Vacancy).order_by(Vacancy.created_at.desc())
        if status is not None:
            query = query.where(Vacancy.status == status)
        if budget_line_id is not None:
            query = query.where(Vacancy.budget_line_id == budget_line_id)
        result = await self.db.execute(query)
        return list(result.scalars())

    async def list_full(self, *, status: str | None = None) -> list[Vacancy]:
        """Vacancies with steps, decisions, texts and requester loaded."""
        query = (
            select(Vacancy)
            .order_by(Vacancy.created_at.desc(), Vacancy.id)
            .options(
                selectinload(Vacancy.steps),
                selectinload(Vacancy.decisions),
                selectinload(Vacancy.texts),
                selectinload(Vacancy.requester),
            )
            .execution_options(populate_existing=True)
        )
        if status is not None:
            query = query.where(Vacancy.status == status)
        result = await self.db.execute(query)
        return list(result.scalars())

    async def assignments_of_budget_lines(
        self, budget_line_ids: Iterable[UUID]
    ) -> dict[UUID, tuple[UUID, str]]:
        """Per budget line: the id and the name of its assignment."""
        ids = list(budget_line_ids)
        if not ids:
            return {}
        result = await self.db.execute(
            select(BudgetLine.id, Assignment.id, Assignment.name)
            .join(Assignment, Assignment.id == BudgetLine.assignment_id)
            .where(BudgetLine.id.in_(ids))
        )
        return {line_id: (a_id, name) for line_id, a_id, name in result.all()}

    async def personnel_lines(self) -> list[tuple[BudgetLine, Assignment]]:
        """Every personnel budget line with its assignment and allocations."""
        result = await self.db.execute(
            select(BudgetLine, Assignment)
            .join(Assignment, Assignment.id == BudgetLine.assignment_id)
            .where(BudgetLine.kind == "personnel", BudgetLine.fte.is_not(None))
            .options(selectinload(BudgetLine.allocations))
            .order_by(Assignment.name, BudgetLine.position, BudgetLine.id)
        )
        return [(line, assignment) for line, assignment in result.all()]

    async def budget_lines_with_vacancy(self, statuses: Iterable[str]) -> set[UUID]:
        """Budget lines that already have a vacancy in one of the statuses."""
        result = await self.db.execute(
            select(Vacancy.budget_line_id).where(
                Vacancy.budget_line_id.is_not(None),
                Vacancy.status.in_(list(statuses)),
            )
        )
        return {line_id for line_id in result.scalars() if line_id is not None}

    async def person_names_by_id(self, person_ids: Iterable[UUID]) -> dict[UUID, str]:
        ids = list({pid for pid in person_ids if pid is not None})
        if not ids:
            return {}
        result = await self.db.execute(
            select(Person.id, Person.name).where(Person.id.in_(ids))
        )
        return {pid: name for pid, name in result.all()}

    async def active_person(self, person_id: UUID) -> Person | None:
        result = await self.db.execute(
            select(Person).where(Person.id == person_id, Person.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def person_by_email(self, email: str) -> Person | None:
        result = await self.db.execute(
            select(Person).where(
                func.lower(Person.email) == email.strip().lower(),
                Person.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def steps(self, vacancy_id: UUID) -> list[VacancyStep]:
        result = await self.db.execute(
            select(VacancyStep)
            .where(VacancyStep.vacancy_id == vacancy_id)
            .order_by(VacancyStep.position)
        )
        return list(result.scalars())

    async def decision(self, vacancy_id: UUID, kind: str) -> VacancyDecision | None:
        result = await self.db.execute(
            select(VacancyDecision).where(
                VacancyDecision.vacancy_id == vacancy_id, VacancyDecision.kind == kind
            )
        )
        return result.scalar_one_or_none()

    async def decisions(self, vacancy_id: UUID) -> list[VacancyDecision]:
        result = await self.db.execute(
            select(VacancyDecision).where(VacancyDecision.vacancy_id == vacancy_id)
        )
        return list(result.scalars())

    async def text(self, text_id: UUID) -> VacancyText | None:
        return await self.db.get(VacancyText, text_id)

    async def texts(self, vacancy_id: UUID, kind: str) -> list[VacancyText]:
        """All versions of one kind of text, oldest first."""
        result = await self.db.execute(
            select(VacancyText)
            .where(VacancyText.vacancy_id == vacancy_id, VacancyText.kind == kind)
            .order_by(VacancyText.created_at, VacancyText.id)
        )
        return list(result.scalars())

    async def established_text(self, vacancy_id: UUID, kind: str) -> VacancyText | None:
        """The version that was established last, if any."""
        result = await self.db.execute(
            select(VacancyText)
            .where(
                VacancyText.vacancy_id == vacancy_id,
                VacancyText.kind == kind,
                VacancyText.established_at.is_not(None),
            )
            .order_by(VacancyText.established_at.desc(), VacancyText.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def example_texts(
        self, *, exclude_vacancy_id: UUID, kind: str, limit: int
    ) -> list[str]:
        """Established texts of other published vacancies, newest first."""
        result = await self.db.execute(
            select(VacancyText.body)
            .join(Vacancy, Vacancy.id == VacancyText.vacancy_id)
            .where(
                VacancyText.kind == kind,
                VacancyText.established_at.is_not(None),
                Vacancy.published_at.is_not(None),
                Vacancy.id != exclude_vacancy_id,
            )
            .order_by(VacancyText.established_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def person_names(self) -> list[str]:
        """Names of everyone known to this instance, for the name check."""
        result = await self.db.execute(select(Person.name))
        return [name for name in result.scalars() if name]


class FormTemplateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, template_id: UUID) -> FormTemplate | None:
        result = await self.db.execute(
            select(FormTemplate)
            .where(FormTemplate.id == template_id)
            .options(undefer(FormTemplate.content))
        )
        return result.scalar_one_or_none()

    async def active(self, kind: str) -> FormTemplate | None:
        result = await self.db.execute(
            select(FormTemplate)
            .where(FormTemplate.kind == kind, FormTemplate.is_active.is_(True))
            .options(undefer(FormTemplate.content))
        )
        return result.scalar_one_or_none()

    async def list(self, kind: str) -> list[FormTemplate]:
        """Templates without their file contents."""
        result = await self.db.execute(
            select(FormTemplate)
            .where(FormTemplate.kind == kind)
            .order_by(FormTemplate.created_at.desc())
        )
        return list(result.scalars())

    async def deactivate_all(self, kind: str) -> None:
        await self.db.execute(
            update(FormTemplate)
            .where(FormTemplate.kind == kind, FormTemplate.is_active.is_(True))
            .values(is_active=False)
        )
