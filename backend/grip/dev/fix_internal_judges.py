"""Example data from before the rule on who judges something internal.

An earlier seed named a person who is in grip for a client-side right only
as the one a vacancy's request is addressed to and who approved it, and gave
client-side people an inzetschaal. This brings an example database in line
with the seed of today, and can be run any number of times:

- a fictional director is added when missing;
- every advice, approval and addressee on a vacancy that names a client-side
  only person names the director instead;
- the inzetschaal of a client-side only person who is staffed nowhere is
  removed.

Only persons with an address in the example domain are touched.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.dev.seed import EMAIL_DOMAIN
from grip.models.assignment import Allocation
from grip.models.person import Person
from grip.models.person_details import PersonScale
from grip.models.vacancy import Vacancy, VacancyDecision
from grip.services import internal_judges, rates

DIRECTOR_EMAIL = f"dana.directie@{EMAIL_DOMAIN}"
DIRECTOR_NAME = "Dana Directie"
DIRECTOR_SCALE = 16


async def _director(db: AsyncSession) -> tuple[Person, bool]:
    found = (
        await db.execute(
            select(Person).where(func.lower(Person.email) == DIRECTOR_EMAIL)
        )
    ).scalar_one_or_none()
    if found is not None:
        return found, False
    person = Person(name=DIRECTOR_NAME, email=DIRECTOR_EMAIL)
    db.add(person)
    await db.flush()
    record_audit(
        db,
        actor=None,
        action=CREATE,
        entity="person",
        entity_id=person.id,
        new_value={"email": DIRECTOR_EMAIL, "source": "seed"},
    )
    # From this year on: an earlier year's rate card may be closed.
    await rates.set_person_scale(
        db, person.id, date(clock.today().year, 1, 1), DIRECTOR_SCALE, actor=None
    )
    return person, True


async def fix(db: AsyncSession) -> dict[str, int]:
    """Apply the fix; returns what it changed."""
    changed = {"director": 0, "decisions": 0, "addressees": 0, "scales": 0}
    example_ids = set(
        (
            await db.execute(
                select(Person.id).where(
                    func.lower(Person.email).like(f"%@{EMAIL_DOMAIN}")
                )
            )
        ).scalars()
    )
    outside = await internal_judges.client_side_only(db, example_ids)
    if not outside:
        return changed

    director: Person | None = None

    async def the_director() -> Person:
        nonlocal director
        if director is None:
            director, made = await _director(db)
            changed["director"] += int(made)
        return director

    decisions = (
        (
            await db.execute(
                select(VacancyDecision).where(VacancyDecision.person_id.in_(outside))
            )
        )
        .scalars()
        .all()
    )
    for decision in decisions:
        person = await the_director()
        old = {"person_name": decision.person_name}
        decision.person_id = person.id
        decision.person_name = person.name
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="vacancy_decision",
            entity_id=decision.id,
            old_value=old,
            new_value={"person_name": person.name},
        )
        changed["decisions"] += 1

    # By id, or by name alone where an earlier seed stored only the name.
    outside_names = set(
        (await db.execute(select(Person.name).where(Person.id.in_(outside)))).scalars()
    )
    vacancies = (
        (
            await db.execute(
                select(Vacancy).where(
                    Vacancy.addressee_id.in_(outside)
                    | (
                        Vacancy.addressee_id.is_(None)
                        & Vacancy.addressee_name.in_(outside_names)
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for vacancy in vacancies:
        person = await the_director()
        old = {"addressee_name": vacancy.addressee_name}
        vacancy.addressee_id = person.id
        vacancy.addressee_name = person.name
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="vacancy",
            entity_id=vacancy.id,
            old_value=old,
            new_value={"addressee_name": person.name},
        )
        changed["addressees"] += 1

    staffed = set(
        (
            await db.execute(
                select(Allocation.person_id).where(Allocation.person_id.in_(outside))
            )
        ).scalars()
    )
    for person_id in outside - staffed:
        rows = (
            (
                await db.execute(
                    select(PersonScale).where(PersonScale.person_id == person_id)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            record_audit(
                db,
                actor=None,
                action=DELETE,
                entity="person_scale",
                entity_id=row.id,
                old_value={"billing_scale": row.billing_scale},
            )
            changed["scales"] += 1
        if rows:
            await db.execute(
                delete(PersonScale).where(PersonScale.person_id == person_id)
            )
    await db.flush()
    return changed


async def _run() -> int:
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            changed = await fix(db)
            await db.commit()
        print(
            f"{changed['decisions']} adviezen of akkoorden en "
            f"{changed['addressees']} geadresseerden omgezet naar {DIRECTOR_NAME}"
            f"{' (nieuw aangemaakt)' if changed['director'] else ''}; "
            f"{changed['scales']} inzetschalen van personen met alleen een recht "
            "namens een opdrachtgever verwijderd."
        )
    finally:
        await close_db()
    return 0


if __name__ == "__main__":
    import asyncio
    import sys

    sys.exit(asyncio.run(_run()))
