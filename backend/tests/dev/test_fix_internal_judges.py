"""The data fix for example databases seeded before the rule on who judges
something internal. All names are fictional."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from grip.dev import fix_internal_judges
from grip.dev.seed import EMAIL_DOMAIN
from grip.models.person_details import PersonScale
from grip.models.vacancy import Vacancy, VacancyDecision
from grip.services import rates


async def test_it_moves_decisions_to_a_director_and_is_idempotent(
    db_session, create_person
) -> None:
    db = db_session
    owner = await create_person(f"eigenaar@{EMAIL_DOMAIN}", name="Fictieve Eigenaar")
    signatory = await create_person(
        f"tekenaar@{EMAIL_DOMAIN}",
        name="Fictieve Tekenaar",
        functions=["tekenbevoegde"],
    )
    await rates.set_person_scale(db, signatory.id, date(2025, 1, 1), 15, actor=None)
    vacancy = Vacancy(
        function_title="Developer",
        fte=Decimal("1"),
        declarable=False,
        requester_id=owner.id,
        status="requested",
        addressee_id=signatory.id,
        addressee_name=signatory.name,
    )
    db.add(vacancy)
    await db.flush()
    decision = VacancyDecision(
        vacancy_id=vacancy.id,
        kind="approval",
        person_id=signatory.id,
        person_name=signatory.name,
        agreed=True,
    )
    db.add(decision)
    await db.flush()

    first = await fix_internal_judges.fix(db)
    assert first == {"director": 1, "decisions": 1, "addressees": 1, "scales": 1}
    await db.refresh(decision)
    await db.refresh(vacancy)
    assert decision.person_name == fix_internal_judges.DIRECTOR_NAME
    assert vacancy.addressee_name == fix_internal_judges.DIRECTOR_NAME
    assert decision.person_id == vacancy.addressee_id != signatory.id
    scales = (
        await db.execute(
            select(PersonScale).where(PersonScale.person_id == signatory.id)
        )
    ).all()
    assert scales == []

    again = await fix_internal_judges.fix(db)
    assert again == {"director": 0, "decisions": 0, "addressees": 0, "scales": 0}
