"""Run the sync with the public register from the command line.

python -m grip.integrations.organisations            fetch and apply
python -m grip.integrations.organisations --file X   apply a downloaded export
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from grip.core.database import async_session, close_db
from grip.integrations.organisations.source import REGISTRY_URL
from grip.services.organisations import run_registry_sync

_LABELS = {
    "seen": "in de export",
    "created": "toegevoegd",
    "updated": "bijgewerkt",
    "unchanged": "ongewijzigd",
    "adopted": "handmatig, nu uit het register",
    "closed": "afgesloten",
    "deleted": "verwijderd",
    "skipped_ended": "al opgeheven, niet toegevoegd",
    "excluded": "uitgesloten",
    "duplicate_identifiers": "dubbele kenmerken in de export",
}


async def _run(url: str, file: Path | None) -> int:
    content = file.read_bytes() if file else None
    try:
        async with async_session() as db:
            run = await run_registry_sync(db, actor=None, url=url, content=content)
            await db.commit()
    finally:
        await close_db()
    if run.status != "completed":
        print(f"Mislukt: {run.error}", file=sys.stderr)
        return 1
    print("Organisaties bijgewerkt uit het register:")
    for key, label in _LABELS.items():
        print(f"  {label}: {run.result.get(key, 0)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=REGISTRY_URL)
    parser.add_argument("--file", type=Path, help="een eerder gedownloade export")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.url, args.file)))


if __name__ == "__main__":
    main()
