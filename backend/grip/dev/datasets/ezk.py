"""Example dataset ``ezk``: the Ministerie van EZK voorbeeld.

A small directorate-general and the parent of NLDD voorbeeld. A parent has no
screen in grip yet, so this instance holds its people and the organisations,
and no assignments.

Load it with ``SEED_DATASET=ezk`` or ``just seed --dataset ezk``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.dev.datasets import chain
from grip.dev.seed import ExamplePerson, SeedResult, _people
from grip.models.role import BEHEERDER, LEZER

OWN = "ezk"

PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("babette.beheer", "Babette Beheer", None, functions=(BEHEERDER,)),
    ExamplePerson(
        "sabine.samenleving",
        "Sabine Samenleving",
        None,
        functions=(LEZER,),
        note="directeur-generaal Digitaliseringsbeleid Samenleving en Overheid",
    ),
    ExamplePerson(
        "mirjam.middelen",
        "Mirjam Middelen",
        None,
        functions=(LEZER,),
        note="controller",
    ),
)


async def fill(db: AsyncSession, settings: Settings) -> SeedResult:
    result = SeedResult(examples=PEOPLE)
    await _people(db, result, PEOPLE)
    rows = await chain.organisations(db, settings, (OWN, "nldd"), own=OWN)
    await db.flush()
    result.counts.update(people=len(PEOPLE), assignments=0, organisations=len(rows))
    return result
