"""Example dataset ``nldd``: NLDD voorbeeld.

The Nederlandse Digitale Dienst, a service of the Ministerie van EZK voorbeeld
and the client of two of its own projects at DigiGilde voorbeeld: Fundament
and RegelRecht. NLDD is no contractor: no rate card, no staffing, no quotes of
its own. It holds the assignments it gave, on the quotes it signed; DigiGilde
holds the other half in the default dataset (``grip.dev.datasets.chain``).

Load it with ``SEED_DATASET=nldd`` or ``just seed --dataset nldd``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.dev.datasets import chain
from grip.dev.seed import RATES, SCALES, ExamplePerson, SeedResult, _people
from grip.models.role import AANVRAGER, BEHEERDER, LEZER, TEKENBEVOEGDE

OWN = "nldd"

PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("boris.beheer", "Boris Beheer", None, functions=(BEHEERDER,)),
    ExamplePerson(
        "daphne.dienst",
        "Daphne Dienst",
        None,
        functions=(TEKENBEVOEGDE, LEZER),
        note="directeur NLDD",
    ),
    ExamplePerson(
        "floor.fundament",
        "Floor Fundament",
        None,
        functions=(AANVRAGER,),
        note="trajectleider Fundament",
    ),
    ExamplePerson(
        "romy.recht",
        "Romy Recht",
        None,
        functions=(AANVRAGER,),
        note="trajectleider RegelRecht",
    ),
)

OWNERS = {"fundament": "floor.fundament", "regelrecht": "romy.recht"}


async def fill(db: AsyncSession, settings: Settings) -> SeedResult:
    result = SeedResult(examples=PEOPLE)
    await _people(db, result, PEOPLE)
    rows = await chain.organisations(db, settings, ("ezk", OWN, "digigilde"), own=OWN)
    book = chain.rate_book(RATES, SCALES)
    for key, owner in OWNERS.items():
        given = await chain.as_client(
            db,
            settings,
            chain.SHARED[key],
            own=rows[OWN],
            contractor=rows["digigilde"],
            owner=result.people[owner],
            signer=result.people["daphne.dienst"],
            signer_function="Directeur NLDD (fictief)",
            book=book,
        )
        result.assignments[key] = given
        result.relate(owner, f"eigenaar van {given.name}")
    await db.flush()
    result.counts.update(
        people=len(PEOPLE),
        assignments=len(result.assignments),
        organisations=len(rows),
    )
    return result
