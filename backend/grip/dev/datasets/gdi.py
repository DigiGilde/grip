"""Example dataset ``gdi``: GDI voorbeeld.

After the Programmeringsraad GDI: it approves the programme MOZa and leaves
the commissioning to the Ministerie van BZK voorbeeld. Grip has no concept of
an approved programme, so the approval is what grip does know: an assignment
from GDI to BZK, on a quote BZK issued and the chair signed. BZK holds the
other half in its own dataset (``grip.dev.datasets.chain``).

Load it with ``SEED_DATASET=gdi`` or ``just seed --dataset gdi``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.dev.datasets import chain
from grip.dev.seed import RATES, SCALES, ExamplePerson, SeedResult, _people
from grip.models.role import AANVRAGER, BEHEERDER, LEZER, TEKENBEVOEGDE

OWN = "gdi"

PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("britt.beheer", "Britt Beheer", None, functions=(BEHEERDER,)),
    ExamplePerson(
        "petra.programmering",
        "Petra Programmering",
        None,
        functions=(TEKENBEVOEGDE, LEZER),
        note="voorzitter van de Programmeringsraad GDI voorbeeld",
    ),
    ExamplePerson(
        "stef.stelsel",
        "Stef Stelsel",
        None,
        functions=(AANVRAGER,),
        note="secretaris van de Programmeringsraad GDI voorbeeld",
    ),
)


async def fill(db: AsyncSession, settings: Settings) -> SeedResult:
    result = SeedResult(examples=PEOPLE)
    await _people(db, result, PEOPLE)
    rows = await chain.organisations(db, settings, (OWN, "ministerie"), own=OWN)
    delegation = await chain.as_client(
        db,
        settings,
        chain.SHARED["delegation"],
        own=rows[OWN],
        contractor=rows["ministerie"],
        owner=result.people["stef.stelsel"],
        signer=result.people["petra.programmering"],
        signer_function="Voorzitter Programmeringsraad GDI (fictief)",
        book=chain.rate_book(RATES, SCALES),
    )
    result.relate("stef.stelsel", f"eigenaar van {delegation.name}")
    await db.flush()
    result.assignments = {"delegation": delegation}
    result.counts.update(people=len(PEOPLE), assignments=1, organisations=len(rows))
    return result
