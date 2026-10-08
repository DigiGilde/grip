"""Queries for vacancies and form templates. No business rules here."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

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
