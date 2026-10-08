from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.models.assignment import Allocation, AssignmentRole
from grip.models.person import Person
from grip.models.role import PersonRole


def normalize_email(email: str) -> str:
    return email.strip().lower()


class PersonRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, person_id: UUID) -> Person | None:
        return await self.db.get(Person, person_id)

    async def get_by_oidc_subject(self, sub: str) -> Person | None:
        result = await self.db.execute(select(Person).where(Person.oidc_subject == sub))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Person | None:
        result = await self.db.execute(
            select(Person).where(func.lower(Person.email) == normalize_email(email))
        )
        return result.scalar_one_or_none()

    async def active_function_ids(
        self, person_id: UUID, on: date | None = None
    ) -> list[str]:
        """Functions the person holds on the given day (today by default)."""
        day = on or clock.today()
        result = await self.db.execute(
            select(PersonRole.role_id)
            .where(
                PersonRole.person_id == person_id,
                PersonRole.start_date <= day,
                or_(PersonRole.end_date.is_(None), PersonRole.end_date >= day),
            )
            .distinct()
            .order_by(PersonRole.role_id)
        )
        return list(result.scalars().all())

    async def relation_names(self, person_id: UUID) -> list[str]:
        """Which kinds of relation the person has to anything in the instance.

        Not a grant: every screen and route still decides per object. This
        only tells the navigation which sections can hold something for this
        person, so it does not offer a section that will always be empty.
        """
        checks = {
            "assignment_manager": exists().where(AssignmentRole.person_id == person_id),
            "line_manager": exists().where(
                Person.manager_id == person_id, Person.is_active.is_(True)
            ),
            "team_member": exists().where(Allocation.person_id == person_id),
        }
        row = (
            await self.db.execute(
                select(*(check.label(name) for name, check in checks.items()))
            )
        ).one()
        return [name for name in checks if getattr(row, name)]

    async def first_active_with_function(self, role_id: str) -> Person | None:
        day = clock.today()
        result = await self.db.execute(
            select(Person)
            .join(PersonRole, PersonRole.person_id == Person.id)
            .where(
                Person.is_active.is_(True),
                PersonRole.role_id == role_id,
                PersonRole.start_date <= day,
                or_(PersonRole.end_date.is_(None), PersonRole.end_date >= day),
            )
            .order_by(Person.created_at, Person.id)
            .limit(1)
        )
        return result.scalar_one_or_none()
