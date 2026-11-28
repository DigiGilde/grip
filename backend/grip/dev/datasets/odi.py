"""Example dataset ``odi``: ODI voorbeeld.

The agentschap and contract party of the programme: the Ministerie van BZK
voorbeeld gives ODI the execution of MOZa, and ODI has it done by DigiGilde
voorbeeld, a brand of ODI and its child instance. How that runs through grip
is a later step; here ODI holds the assignment it received, with a fixed
amount, and no rate card. BZK holds the other half in its own dataset
(``grip.dev.datasets.chain``).

Load it with ``SEED_DATASET=odi`` or ``just seed --dataset odi``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.dev.datasets import chain
from grip.dev.seed import ExamplePerson, SeedResult, _people
from grip.models.role import BEHEERDER, LEZER

OWN = "odi"

PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("benno.beheer", "Benno Beheer", None, functions=(BEHEERDER,)),
    ExamplePerson(
        "arjan.agentschap",
        "Arjan Agentschap",
        None,
        functions=(LEZER,),
        note="algemeen directeur",
    ),
    ExamplePerson(
        "dilara.digitaal",
        "Dilara Digitaal",
        None,
        functions=(LEZER,),
        note="directeur digitalisering",
    ),
    ExamplePerson(
        "bas.bedrijfsvoering",
        "Bas Bedrijfsvoering",
        None,
        functions=(LEZER,),
        note="directeur bedrijfsvoering",
    ),
    ExamplePerson(
        "bo.begroting", "Bo Begroting", None, functions=(LEZER,), note="controller"
    ),
)


async def fill(db: AsyncSession, settings: Settings) -> SeedResult:
    result = SeedResult(examples=PEOPLE)
    beheerder = await _people(db, result, PEOPLE)
    rows = await chain.organisations(
        db, settings, (OWN, "digigilde", "ministerie"), own=OWN
    )
    dilara = result.people["dilara.digitaal"]
    execution, _lines = await chain.as_contractor(
        db,
        settings,
        chain.SHARED["execution"],
        own=rows[OWN],
        client=rows["ministerie"],
        owner=dilara,
        manager=None,
        actor=beheerder,
    )
    result.relate("dilara.digitaal", f"eigenaar van {execution.name}")
    await db.flush()
    result.assignments = {"execution": execution}
    result.counts.update(people=len(PEOPLE), assignments=1, organisations=len(rows))
    return result
