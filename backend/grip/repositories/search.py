"""Queries behind the search field. No access decisions here: they return
everything that matches, and the caller decides per hit what the reader sees."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.models.person import Person
from grip.models.vacancy import Vacancy


def like_pattern(words: str) -> str:
    """A pattern that matches the text anywhere; ``%`` and ``_`` stay plain."""
    escaped = words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def vacancies_titled(db: AsyncSession, words: str) -> list[Vacancy]:
    """Vacancies whose function title contains the text, in title order.

    Decisions and texts are loaded: the access rules need them.
    """
    result = await db.execute(
        select(Vacancy)
        .where(Vacancy.function_title.ilike(like_pattern(words), escape="\\"))
        .order_by(func.lower(Vacancy.function_title), Vacancy.id)
        .options(selectinload(Vacancy.decisions), selectinload(Vacancy.texts))
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def active_persons_named(db: AsyncSession, words: str) -> list[tuple[UUID, str]]:
    """The id and name of active persons whose name contains the text."""
    result = await db.execute(
        select(Person.id, Person.name)
        .where(
            Person.is_active.is_(True),
            Person.name.ilike(like_pattern(words), escape="\\"),
        )
        .order_by(func.lower(Person.name), Person.id)
    )
    return [(row[0], row[1]) for row in result]
