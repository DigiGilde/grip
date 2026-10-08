"""Load the reference file of the Functiegebouw Rijk into this instance.

Run with ``just load-function-framework``. Upserts on the identifier of the
source, removes nothing, and leaves rows a beheerder changed as they are.
``--file PATH`` loads another file in the same format.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from grip.core.database import async_session, close_db
from grip.services import function_framework as framework


async def _run(path: Path | None) -> int:
    data = framework.read_reference(path)
    info = framework.reference_info(data)
    async with async_session() as db:
        result = await framework.reload_reference(db, actor=None, data=data)
        await db.commit()
    await close_db()
    print(
        f"{info.name}, gelezen op {info.read_on.isoformat()} van {info.source_url}: "
        f"{info.families} families, {info.groups} groepen in het bestand."
    )
    print(
        f"Families: {result.families_created} nieuw, {result.families_updated} "
        f"bijgewerkt. Groepen: {result.groups_created} nieuw, "
        f"{result.groups_updated} bijgewerkt, {result.groups_kept} met de hand "
        "gewijzigd en zo gelaten."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(_run(args.file))


if __name__ == "__main__":
    raise SystemExit(main())
