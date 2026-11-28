"""Example dataset ``bzk``: the Ministerie van BZK voorbeeld.

The ministry is the delegated client on behalf of the GDI: it received the
commissioning of the programme MOZa from GDI voorbeeld, funds MOZa voorbeeld
with the programme budget and gives ODI voorbeeld the execution. Each of
those assignments runs between two example instances; the other side holds
its half in its own dataset (``grip.dev.datasets.chain``).

The ministry holds no rate card and staffs nobody. Its people are the MIN
personas of the personaboek.

Load it with ``SEED_DATASET=bzk`` or ``just seed --dataset bzk``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.dev.datasets import chain
from grip.dev.seed import RATES, SCALES, ExamplePerson, SeedResult, _people
from grip.models.role import AANVRAGER, BEHEERDER, LEZER, TEKENBEVOEGDE

OWN = "ministerie"

PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("berend.beheer", "Berend Beheer", None, functions=(BEHEERDER,)),
    ExamplePerson(
        "dorien.digitalisering",
        "Dorien Digitalisering",
        None,
        functions=(LEZER,),
        note="directeur-generaal; aanvaardt het opdrachtgeverschap van GDI",
    ),
    ExamplePerson(
        "tess.teken",
        "Tess Teken",
        None,
        functions=(TEKENBEVOEGDE,),
        note="directeur, budgethouder",
    ),
    ExamplePerson(
        "anouk.aanvraag",
        "Anouk Aanvraag",
        None,
        functions=(AANVRAGER,),
        note="opdrachtgever namens de directie",
    ),
    ExamplePerson("coen.controle", "Coen Controle", None, functions=(LEZER,)),
    ExamplePerson(
        "astrid.administratie", "Astrid Administratie", None, functions=(LEZER,)
    ),
    ExamplePerson("ivo.informatie", "Ivo Informatie", None, functions=(LEZER,)),
)


async def fill(db: AsyncSession, settings: Settings) -> SeedResult:
    result = SeedResult(examples=PEOPLE)
    beheerder = await _people(db, result, PEOPLE)
    rows = await chain.organisations(
        db, settings, (OWN, "programma", "gdi", "odi"), own=OWN
    )
    dorien = result.people["dorien.digitalisering"]
    anouk = result.people["anouk.aanvraag"]
    tess = result.people["tess.teken"]
    book = chain.rate_book(RATES, SCALES)

    delegation, _lines = await chain.as_contractor(
        db,
        settings,
        chain.SHARED["delegation"],
        own=rows[OWN],
        client=rows["gdi"],
        owner=dorien,
        manager=None,
        actor=beheerder,
    )
    result.relate("dorien.digitalisering", f"eigenaar van {delegation.name}")
    given = {}
    for key, contractor in (("programme", "programma"), ("execution", "odi")):
        given[key] = await chain.as_client(
            db,
            settings,
            chain.SHARED[key],
            own=rows[OWN],
            contractor=rows[contractor],
            owner=anouk,
            signer=tess,
            signer_function="Directeur, budgethouder (fictief)",
            book=book,
        )
        result.relate("anouk.aanvraag", f"eigenaar van {given[key].name}")
    await db.flush()
    result.assignments = {"delegation": delegation, **given}
    result.counts.update(
        people=len(PEOPLE),
        assignments=len(result.assignments),
        organisations=len(rows),
    )
    return result
