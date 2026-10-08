"""Apply a shipped profile for quotes to this instance.

Usage: ``python -m grip.dev.quote_profile <name>``. Sets the sender, the
sections and the standard texts from ``grip/data/profiles/<name>.json``. The
contact person and the signatory stay as they are.
"""

from __future__ import annotations

import asyncio
import sys

from grip.core.database import async_session
from grip.services import quote_sender


async def main(name: str) -> None:
    async with async_session() as session:
        await quote_sender.apply_profile(session, name, actor=None)
        await session.commit()
    print(f"Profiel '{name}' overgenomen.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        names = ", ".join(quote_sender.profile_names()) or "geen"
        sys.exit(f"Geef de naam van een profiel. Beschikbaar: {names}")
    asyncio.run(main(sys.argv[1]))
