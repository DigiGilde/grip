"""A role typed in as "po" becomes the role Product owner.

Before the catalogue knew the other names of a role, someone could type "po"
on a budget line and get a role of that name. The standard vacancy text for
Product owner carries "PO" as another name and hangs on that stray role. This
makes it one proper role, and can be run any number of times:

- when no role "Product owner" exists, the stray role is renamed, and the
  lines that carry its name follow;
- when it does exist, the stray role is merged into it, with its budget
  lines, people and standard texts.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.models.assignment import BudgetLine
from grip.models.catalogue_role import CatalogueRole
from grip.models.vacancy import Vacancy
from grip.services import catalogue_roles, stale

STRAY = "po"
PROPER = "Product owner"


async def _by_name(db: AsyncSession, name: str) -> CatalogueRole | None:
    return (
        await db.execute(
            select(CatalogueRole).where(func.lower(CatalogueRole.name) == name.lower())
        )
    ).scalar_one_or_none()


async def fix(db: AsyncSession) -> dict[str, int]:
    changed = {"renamed": 0, "merged": 0, "lines": 0, "vacancies": 0}
    stray = await _by_name(db, STRAY)
    proper = await _by_name(db, PROPER)
    if stray is not None and proper is None:
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="catalogue_role",
            entity_id=stray.id,
            old_value={"name": stray.name},
            new_value={"name": PROPER},
        )
        stray.name = PROPER
        stale.touch(stray)
        changed["renamed"] = 1
        proper = stray
    elif stray is not None and proper is not None:
        _, moved = await catalogue_roles.merge_roles(
            db, stray.id, proper.id, actor=None
        )
        changed["merged"] = 1
        changed["lines"] += moved
    if proper is None:
        return changed
    # Lines and vacancies that carry the typed name, with or without the role.
    stray_lines = func.lower(BudgetLine.role) == STRAY
    stray_titles = func.lower(Vacancy.function_title) == STRAY
    changed["lines"] += (
        await db.execute(
            select(func.count()).select_from(BudgetLine).where(stray_lines)
        )
    ).scalar_one()
    changed["vacancies"] = (
        await db.execute(select(func.count()).select_from(Vacancy).where(stray_titles))
    ).scalar_one()
    await db.execute(
        update(BudgetLine)
        .where(stray_lines)
        .values(role=proper.name, role_id=proper.id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        update(Vacancy)
        .where(stray_titles)
        .values(function_title=proper.name)
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    return changed


async def _run() -> int:
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            changed = await fix(db)
            await db.commit()
        if changed["renamed"]:
            how = f'De rol "{STRAY}" heet nu {PROPER}'
        elif changed["merged"]:
            how = f'De rol "{STRAY}" is samengevoegd met {PROPER}'
        else:
            how = f'Er is geen rol "{STRAY}"'
        print(
            f"{how}; {changed['lines']} begrotingsregels en "
            f"{changed['vacancies']} vacatures bijgewerkt."
        )
    finally:
        await close_db()
    return 0


if __name__ == "__main__":
    import asyncio
    import sys

    sys.exit(asyncio.run(_run()))
