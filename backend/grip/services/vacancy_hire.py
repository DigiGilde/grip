"""The hire on a vacancy: the moment a person enters grip.

Recruitment happens in the recruitment system. Grip keeps a reference to the
vacancy there and learns one thing from it: who was hired, and from when.
Recording that marks the vacancy as filled, creates the prospective colleague
(or takes an existing person), and proposes the inzet on the budget line the
vacancy hangs on.

Today the hire is recorded by hand, with the reference of the recruitment
system kept. When that system is connected it becomes the source of this
fact; the standing of the person already has a ``source`` for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.models.assignment import Allocation, BudgetLine
from grip.models.person import Person
from grip.models.vacancy import Vacancy
from grip.models.vacancy_hire import (
    DEFAULT_RECRUITMENT_SYSTEM,
    VacancyHire,
    VacancyRecruitmentRef,
)
from grip.services import assignments, rates, stale, standing
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.vacancies import service as vacancy_service


@dataclass(frozen=True)
class ProposedAllocation:
    """The inzet that follows from the hire, for the planner to confirm."""

    budget_line_id: UUID
    start_date: date
    end_date: date
    fte_pct: Decimal


@dataclass(frozen=True)
class HireResult:
    vacancy: Vacancy
    person: Person
    hire: VacancyHire
    proposed_allocation: ProposedAllocation | None
    allocation: Allocation | None


async def get_recruitment_ref(
    db: AsyncSession, vacancy_id: UUID
) -> VacancyRecruitmentRef | None:
    return await db.get(VacancyRecruitmentRef, vacancy_id)


async def set_recruitment_ref(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    reference: str,
    url: str | None,
    system: str | None,
    actor: Person | None,
) -> VacancyRecruitmentRef | None:
    """Store or clear where this vacancy lives in the recruitment system."""
    vacancy = await db.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise NotFoundError("Vacature", vacancy_id)
    await stale.check(db, vacancy, "deze vacature")
    stale.touch(vacancy)
    reference = reference.strip()
    row = await db.get(VacancyRecruitmentRef, vacancy_id)
    old = (
        {"system": row.system, "reference": row.reference, "url": row.url}
        if row
        else None
    )
    if not reference:
        if row is not None:
            await db.delete(row)
            await db.flush()
            record_audit(
                db,
                actor=actor,
                action=UPDATE,
                entity="vacancy_recruitment_ref",
                entity_id=vacancy_id,
                old_value=old,
                new_value=None,
            )
        return None
    link = (url or "").strip() or None
    if link and not link.startswith(("https://", "http://")):
        raise DomainValidationError("De link moet met https:// beginnen.")
    name = (system or "").strip().lower() or DEFAULT_RECRUITMENT_SYSTEM
    if row is None:
        row = VacancyRecruitmentRef(vacancy_id=vacancy_id)
        db.add(row)
    row.system, row.reference, row.url = name, reference, link
    await db.flush()
    new = {"system": row.system, "reference": row.reference, "url": row.url}
    if new != old:
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="vacancy_recruitment_ref",
            entity_id=vacancy_id,
            old_value=old,
            new_value=new,
        )
    return row


async def get_hire(db: AsyncSession, vacancy_id: UUID) -> VacancyHire | None:
    return await db.get(VacancyHire, vacancy_id)


def _proposal(line: BudgetLine | None, start: date) -> ProposedAllocation | None:
    if line is None or line.kind != "personnel" or line.end_date is None:
        return None
    begin = max(start, line.start_date) if line.start_date else start
    if begin > line.end_date:
        return None
    return ProposedAllocation(
        budget_line_id=line.id,
        start_date=begin,
        end_date=line.end_date,
        fte_pct=(Decimal(line.fte or 0) * Decimal(100)).quantize(Decimal("0.01")),
    )


async def record_hire(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    start_date: date,
    actor: Person | None,
    name: str | None = None,
    person_id: UUID | None = None,
    suborganization: str | None = None,
    create_allocation: bool = False,
    note: str | None = None,
) -> HireResult:
    """Record who was hired on this vacancy, and mark it filled.

    Give ``person_id`` when the role goes to someone grip already knows, or
    ``name`` for a new person: that creates the prospective colleague, who is
    planned from today and proposed to Wies.
    """
    vacancy = await db.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise NotFoundError("Vacature", vacancy_id)
    if await db.get(VacancyHire, vacancy_id) is not None:
        raise DomainValidationError("Op deze vacature is al iemand aangenomen.")
    if (person_id is None) == (not (name or "").strip()):
        raise DomainValidationError(
            "Kies een bestaande persoon of geef de naam van de nieuwe collega."
        )

    # The vacancy closes first: its own rules decide whether it may be filled.
    vacancy = await vacancy_service.fill_vacancy(db, vacancy_id, actor=actor, note=note)

    if person_id is not None:
        person = await db.get(Person, person_id)
        if person is None or not person.is_active:
            raise NotFoundError("Persoon", person_id)
    else:
        ref = await db.get(VacancyRecruitmentRef, vacancy_id)
        person = await standing.create_prospective_colleague(
            db,
            name=name or "",
            start_date=start_date,
            actor=actor,
            suborganization=suborganization,
            # Recorded here by a person; the reference of the recruitment
            # system rides along so that system can become the source later.
            source="grip",
            source_ref=f"{ref.system}:{ref.reference}" if ref else None,
            source_url=ref.url if ref else None,
        )
        # A new colleague has no inzetschaal yet, and inzet without one cannot
        # be priced: the assignment's figures would read "niet bekend" from
        # the day of the hire. The scale of the vacancy is the scale this
        # person is hired at; it holds from the start date until someone
        # records another.
        if vacancy.scale is not None:
            await rates.set_person_scale(
                db, person.id, start_date, vacancy.scale, actor=actor
            )

    hire = VacancyHire(
        vacancy_id=vacancy_id,
        person_id=person.id,
        start_date=start_date,
        recorded_by_id=actor.id if actor else None,
    )
    db.add(hire)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy_hire",
        entity_id=vacancy_id,
        new_value={"person_id": str(person.id), "start_date": start_date.isoformat()},
    )

    line = (
        await db.get(BudgetLine, vacancy.budget_line_id)
        if vacancy.budget_line_id
        else None
    )
    proposed = _proposal(line, start_date)
    allocation = None
    if create_allocation and proposed is not None:
        allocation = await assignments.add_allocation(
            db,
            proposed.budget_line_id,
            person.id,
            start_date=proposed.start_date,
            end_date=proposed.end_date,
            fte_pct=proposed.fte_pct,
            actor=actor,
        )
    return HireResult(
        vacancy=vacancy,
        person=person,
        hire=hire,
        proposed_allocation=proposed,
        allocation=allocation,
    )


async def hire_fell_through(
    db: AsyncSession, vacancy_id: UUID, *, actor: Person | None, reason: str
) -> None:
    """The recorded hire does not go through.

    For a prospective colleague: planning, the proposal to Wies and, after
    the retention period, the person record go. Someone grip already knew is
    only taken off this vacancy. The vacancy itself stays filled: its state
    machine has no way back, so the role is offered again with a new vacancy.
    """
    hire = await db.get(VacancyHire, vacancy_id)
    if hire is None:
        raise DomainValidationError("Op deze vacature is niemand aangenomen.")
    person_id = hire.person_id
    await db.delete(hire)
    await db.flush()
    if person_id is not None:
        view = await standing.get_standing(db, person_id)
        if view.is_prospective:
            await standing.withdraw_hire(db, person_id, actor=actor, reason=reason)
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy_hire",
        entity_id=vacancy_id,
        old_value={"hired": True},
        new_value={"hired": False, "reason": reason.strip()},
    )
