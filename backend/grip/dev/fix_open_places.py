"""Open places an earlier version wrote for a fact become the fact again.

Before a draft kept the facts of its vacancy by key, a fact that was unknown
when the standard text was taken was written out as an open place
(``[vul aan: de schaal van de vacature]``). It stayed open when the scale was
filled in on the request afterwards. This puts the key back, so the text
follows the vacancy from here on. It can be run any number of times:

- only drafts are touched; a settled text says what it said;
- only the exact passages written then are replaced; an open place a person
  typed over, and any other text, is left as it is;
- the standard texts and the shared sections get the same treatment.

With ``--check`` nothing is written and the count is what would change.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.models.vacancy import TextKind, VacancyText
from grip.services.vacancies import library


async def fix(db: AsyncSession) -> dict[str, int]:
    changed = {"places": 0, "versions": 0, "vacancies": 0, "standard": 0}
    drafts = await db.scalars(
        select(VacancyText).where(
            VacancyText.kind == TextKind.vacancy_text.value,
            VacancyText.established_at.is_(None),
            VacancyText.body.contains(library.OPEN_MARK),
        )
    )
    vacancies = set()
    for text in drafts:
        body, places = library.rekey(text.body)
        if not places:
            continue
        text.body = body
        changed["places"] += places
        changed["versions"] += 1
        vacancies.add(text.vacancy_id)
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="vacancy_text",
            entity_id=text.id,
            new_value={"open_places_to_facts": places},
            vacancy_id=text.vacancy_id,
        )
    changed["vacancies"] = len(vacancies)
    changed["standard"] = await library.rekey_library(db)
    await db.flush()
    return changed


async def _run(check: bool) -> int:
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            changed = await fix(db)
            if check:
                await db.rollback()
            else:
                await db.commit()
        counted = (
            f"{changed['places']} open plekken in {changed['versions']} concepten "
            f"van {changed['vacancies']} vacatures"
        )
        outcome = (
            "zouden weer een gegeven van de vacature worden"
            if check
            else "zijn weer een gegeven van de vacature"
        )
        print(f"{counted} {outcome}; {changed['standard']} in de standaardteksten.")
    finally:
        await close_db()
    return 0


if __name__ == "__main__":
    import asyncio
    import sys

    sys.exit(asyncio.run(_run("--check" in sys.argv[1:])))
