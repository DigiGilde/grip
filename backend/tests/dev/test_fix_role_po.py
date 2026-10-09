"""The data fix that makes a role typed in as "po" the role Product owner."""

from __future__ import annotations

from sqlalchemy import select

from grip.dev import fix_role_po
from grip.models.catalogue_role import CatalogueRole


async def _names(db) -> list[str]:
    return sorted((await db.execute(select(CatalogueRole.name))).scalars().all())


async def test_a_stray_role_is_renamed_and_a_second_run_changes_nothing(
    db_session,
) -> None:
    db = db_session
    db.add(CatalogueRole(name="po", source="manual"))
    await db.flush()

    first = await fix_role_po.fix(db)
    assert first["renamed"] == 1
    assert "Product owner" in await _names(db)
    assert "po" not in await _names(db)

    again = await fix_role_po.fix(db)
    assert again == {"renamed": 0, "merged": 0, "lines": 0, "vacancies": 0}


async def test_a_stray_role_next_to_the_proper_one_is_merged(db_session) -> None:
    db = db_session
    db.add_all(
        [
            CatalogueRole(name="po", source="manual"),
            CatalogueRole(name="Product owner", source="manual"),
        ]
    )
    await db.flush()

    changed = await fix_role_po.fix(db)
    assert changed["merged"] == 1
    assert [name for name in await _names(db) if name.lower() == "po"] == []
    assert (await _names(db)).count("Product owner") == 1


async def test_nothing_happens_without_a_stray_role(db_session) -> None:
    assert await fix_role_po.fix(db_session) == {
        "renamed": 0,
        "merged": 0,
        "lines": 0,
        "vacancies": 0,
    }
