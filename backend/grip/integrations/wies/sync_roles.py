"""Take over the skills of Wies into the role catalogue, from the command line.

python -m grip.integrations.wies.sync_roles
"""

from __future__ import annotations

import asyncio
import sys

from grip.core.config import get_settings
from grip.core.database import async_session, close_db
from grip.services.catalogue_roles import run_wies_sync

_LABELS = {
    "seen": "rollen in Wies",
    "created": "toegevoegd",
    "adopted": "bestaande rol gekoppeld",
    "renamed": "hernoemd",
    "reactivated": "weer ingeschakeld",
    "unchanged": "ongewijzigd",
    "deactivated": "uitgeschakeld (nog in gebruik)",
    "deleted": "verwijderd (nergens in gebruik)",
    "conflicts": "naam botst met een andere rol",
}


async def _run() -> int:
    try:
        async with async_session() as db:
            run = await run_wies_sync(db, get_settings(), actor=None)
            await db.commit()
    finally:
        await close_db()
    if run.status != "completed":
        print(f"Mislukt: {run.error}", file=sys.stderr)
        return 1
    print("Rollen bijgewerkt uit Wies:")
    for key, label in _LABELS.items():
        print(f"  {label}: {run.result.get(key, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
