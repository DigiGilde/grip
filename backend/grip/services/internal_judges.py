"""Who can be asked to judge something internal.

Advice and approval on a vacancy, the addressee of its request and the
review of a vacancy text are decisions inside the own organisation. A person
whose only rights in grip are those of the client side (asking for a quote,
signing one) is in the instance for that role alone: they are not offered
as adviser, approver or reviewer, and the server refuses them.

A colleague without any function, and anyone who also holds another
function, can be asked.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.models.person import Person
from grip.models.role import AANVRAGER, TEKENBEVOEGDE, PersonRole
from grip.services.errors import DomainValidationError

CLIENT_SIDE_FUNCTIONS = frozenset({AANVRAGER, TEKENBEVOEGDE})

REFUSAL = (
    "{name} heeft in grip alleen een recht namens een opdrachtgever en kan "
    "hier niet adviseren, akkoord geven of beoordelen. Kies een collega."
)


async def client_side_only(
    db: AsyncSession, person_ids: Iterable[UUID] | None = None
) -> set[UUID]:
    """The persons whose current functions are all client-side ones."""
    today = clock.today()
    query = select(PersonRole.person_id, PersonRole.role_id).where(
        PersonRole.start_date <= today,
        (PersonRole.end_date.is_(None)) | (PersonRole.end_date >= today),
    )
    if person_ids is not None:
        ids = list(person_ids)
        if not ids:
            return set()
        query = query.where(PersonRole.person_id.in_(ids))
    held: dict[UUID, set[str]] = {}
    for person_id, role_id in await db.execute(query):
        held.setdefault(person_id, set()).add(role_id)
    return {
        person_id
        for person_id, functions in held.items()
        if functions and functions <= CLIENT_SIDE_FUNCTIONS
    }


async def judge_options(db: AsyncSession) -> list[tuple[UUID, str]]:
    """Active persons with an account who can be asked, by name."""
    rows = (
        await db.execute(
            select(Person.id, Person.name)
            .where(Person.is_active.is_(True), Person.email.is_not(None))
            .order_by(Person.name, Person.id)
        )
    ).all()
    excluded = await client_side_only(db, [row[0] for row in rows])
    return [(row[0], row[1]) for row in rows if row[0] not in excluded]


async def require_internal(db: AsyncSession, person_id: UUID | None) -> None:
    """Refuse a person who holds only a client-side right."""
    if person_id is None:
        return
    if person_id in await client_side_only(db, [person_id]):
        person = await db.get(Person, person_id)
        raise DomainValidationError(
            REFUSAL.format(name=person.name if person else "Deze persoon")
        )
