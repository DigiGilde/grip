"""Persons and the functions they hold: master data with an audit trail.

The reads here feed the team and KPI screens. They load in bulk, so a list of
persons costs a fixed number of queries rather than a few per person.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Allocation, BudgetLine
from grip.models.person import Person
from grip.models.person_details import Hire, PersonScale
from grip.models.role import BEHEERDER, FUNCTIONS, PersonRole
from grip.repositories.person import normalize_email
from grip.services import stale
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import audit_fields
from grip.services.pricing import load_rate_book, to_calc_scale

_PERSON_FIELDS = ("name", "email", "manager_id", "is_active")

Period = tuple[date, date]


async def get_person(session: AsyncSession, person_id: UUID) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError("Persoon", person_id)
    return person


async def list_persons(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[Person]:
    query = select(Person).order_by(func.lower(Person.name), Person.id)
    if not include_inactive:
        query = query.where(Person.is_active.is_(True))
    return list((await session.execute(query)).scalars())


async def _ensure_email_free(
    session: AsyncSession, email: str, *, except_id: UUID | None = None
) -> None:
    query = select(Person.id).where(func.lower(Person.email) == normalize_email(email))
    if except_id is not None:
        query = query.where(Person.id != except_id)
    if (await session.execute(query)).first() is not None:
        raise DomainValidationError("Er is al een persoon met dit e-mailadres.")


async def _ensure_manager(
    session: AsyncSession, manager_id: UUID, *, person_id: UUID | None
) -> None:
    """The manager exists and the reporting line does not become a loop."""
    seen: set[UUID] = set()
    current: UUID | None = manager_id
    while current is not None:
        if current == person_id:
            raise DomainValidationError(
                "Deze leidinggevende valt zelf onder deze persoon."
            )
        if current in seen:
            break
        seen.add(current)
        manager = await session.get(Person, current)
        if manager is None:
            raise NotFoundError("Leidinggevende", current)
        current = manager.manager_id


async def create_person(
    session: AsyncSession,
    *,
    name: str,
    email: str | None,
    actor: Person | None,
    manager_id: UUID | None = None,
    start_date: date | None = None,
    suborganization: str | None = None,
    source_ref: str | None = None,
    source_url: str | None = None,
) -> Person:
    """Create a person.

    With an email address: an ordinary person, who can log in. Without one:
    a prospective colleague, which needs the start date; the person is
    planned from today and logs in once the address has arrived from Wies.
    """
    name, email = name.strip(), (email or "").strip()
    if not name:
        raise DomainValidationError("Een naam is verplicht.")
    if manager_id is not None:
        await _ensure_manager(session, manager_id, person_id=None)
    if not email:
        if start_date is None:
            raise DomainValidationError(
                "Zonder e-mailadres is een startdatum nodig: de persoon wordt "
                "dan als aanstaande collega vastgelegd."
            )
        from grip.services import standing

        return await standing.create_prospective_colleague(
            session,
            name=name,
            start_date=start_date,
            actor=actor,
            manager_id=manager_id,
            suborganization=suborganization,
            source_ref=source_ref,
            source_url=source_url,
        )
    if "@" not in email:
        raise DomainValidationError("Dit is geen geldig e-mailadres.")
    await _ensure_email_free(session, email)
    person = Person(name=name, email=email, manager_id=manager_id)
    session.add(person)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="person",
        entity_id=person.id,
        new_value=audit_fields(person, _PERSON_FIELDS),
    )
    return person


async def update_person(
    session: AsyncSession,
    person_id: UUID,
    *,
    actor: Person | None,
    changes: dict[str, object],
) -> Person:
    """Change name, email, line manager or the active flag.

    ``changes`` holds only the fields to change; ``manager_id`` may be
    ``None`` to remove the line manager.
    """
    unknown = set(changes) - set(_PERSON_FIELDS)
    if unknown:
        raise DomainValidationError(f"Onbekende velden: {sorted(unknown)}")
    person = await get_person(session, person_id)
    old = audit_fields(person, _PERSON_FIELDS)
    await stale.check(session, person, "de gegevens van deze persoon")
    stale.touch(person)

    if "name" in changes:
        name = str(changes["name"]).strip()
        if not name:
            raise DomainValidationError("Een naam is verplicht.")
        person.name = name
    if "email" in changes:
        email = str(changes["email"]).strip()
        if "@" not in email:
            raise DomainValidationError("Dit is geen geldig e-mailadres.")
        await _ensure_email_free(session, email, except_id=person.id)
        person.email = email
        # An address typed in by hand makes a prospective colleague an
        # ordinary person; the start date stays on record.
        from grip.models.person_standing import PersonStanding, Stage

        row = await session.get(PersonStanding, person.id)
        if row is not None and row.stage == Stage.prospective.value:
            row.stage = Stage.colleague.value
    if "manager_id" in changes:
        manager_id = changes["manager_id"]
        if manager_id is not None:
            assert isinstance(manager_id, UUID)
            await _ensure_manager(session, manager_id, person_id=person.id)
        person.manager_id = manager_id  # type: ignore[assignment]
    if "is_active" in changes:
        active = bool(changes["is_active"])
        if not active and person.is_active:
            await _ensure_not_last_beheerder(session, person.id)
        person.is_active = active

    await session.flush()
    new = audit_fields(person, _PERSON_FIELDS)
    if new != old:
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="person",
            entity_id=person.id,
            old_value=old,
            new_value=new,
        )
    return person


# -- login --------------------------------------------------------------------


async def unbind_login(
    session: AsyncSession, person_id: UUID, *, actor: Person | None
) -> Person:
    """Forget which account of the identity provider this person logs in with.

    A person is bound to the provider's subject on the first login. When the
    provider is recreated or the person gets a new account there, the old
    binding refuses the login. After unbinding, the next login with the
    person's verified email binds again.

    The subject itself stays out of the audit row: that it was bound and by
    whom it was unbound is what matters.
    """
    person = await get_person(session, person_id)
    if person.oidc_subject is None:
        raise DomainValidationError("Deze persoon heeft nog niet ingelogd.")
    person.oidc_subject = None
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="person",
        entity_id=person.id,
        old_value={"login_bound": True},
        new_value={"login_bound": False},
    )
    return person


# -- functions ----------------------------------------------------------------


def _held_on(day: date):
    return (
        PersonRole.start_date <= day,
        or_(PersonRole.end_date.is_(None), PersonRole.end_date >= day),
    )


async def functions_by_person(
    session: AsyncSession, on: date | None = None
) -> dict[UUID, list[str]]:
    """The functions every person holds on a day (today by default)."""
    rows = await session.execute(
        select(PersonRole.person_id, PersonRole.role_id)
        .where(*_held_on(on or clock.today()))
        .distinct()
    )
    held: dict[UUID, set[str]] = defaultdict(set)
    for person_id, role_id in rows:
        held[person_id].add(role_id)
    return {person_id: sorted(roles) for person_id, roles in held.items()}


async def _ensure_not_last_beheerder(session: AsyncSession, person_id: UUID) -> None:
    """An instance without a beheerder cannot be managed any more."""
    today = clock.today()
    others = await session.execute(
        select(PersonRole.id)
        .join(Person, Person.id == PersonRole.person_id)
        .where(
            PersonRole.role_id == BEHEERDER,
            PersonRole.person_id != person_id,
            Person.is_active.is_(True),
            *_held_on(today),
        )
        .limit(1)
    )
    if others.first() is not None:
        return
    own = await session.execute(
        select(PersonRole.id)
        .where(
            PersonRole.role_id == BEHEERDER,
            PersonRole.person_id == person_id,
            *_held_on(today),
        )
        .limit(1)
    )
    if own.first() is not None:
        raise DomainValidationError(
            "Dit is de laatste beheerder. Wijs eerst een andere beheerder aan; "
            "zonder beheerder kan niemand de instantie nog beheren."
        )


async def grant_function(
    session: AsyncSession, person_id: UUID, function: str, *, actor: Person | None
) -> list[str]:
    """Let a person hold a function from today. Returns the functions held."""
    if function not in FUNCTIONS:
        raise DomainValidationError(f"Onbekend recht in grip: {function}")
    await get_person(session, person_id)
    today = clock.today()
    held = await session.execute(
        select(PersonRole.id)
        .where(
            PersonRole.person_id == person_id,
            PersonRole.role_id == function,
            *_held_on(today),
        )
        .limit(1)
    )
    if held.first() is None:
        session.add(
            PersonRole(
                person_id=person_id,
                role_id=function,
                start_date=today,
                granted_by_id=actor.id if actor is not None else None,
            )
        )
        await session.flush()
        record_audit(
            session,
            actor=actor,
            action=CREATE,
            entity="person_role",
            entity_id=f"{person_id}/{function}",
            new_value={"person_id": str(person_id), "function": function},
        )
    return (await functions_by_person(session)).get(person_id, [])


async def revoke_function(
    session: AsyncSession, person_id: UUID, function: str, *, actor: Person | None
) -> list[str]:
    """End a function a person holds. Returns the functions still held.

    The grant keeps its history: a grant from an earlier day ends yesterday,
    one made today is removed.
    """
    if function not in FUNCTIONS:
        raise DomainValidationError(f"Onbekend recht in grip: {function}")
    await get_person(session, person_id)
    if function == BEHEERDER:
        await _ensure_not_last_beheerder(session, person_id)
    today = clock.today()
    rows = (
        await session.execute(
            select(PersonRole).where(
                PersonRole.person_id == person_id,
                PersonRole.role_id == function,
                *_held_on(today),
            )
        )
    ).scalars()
    ended = False
    for grant in rows:
        ended = True
        if grant.start_date >= today:
            await session.delete(grant)
        else:
            grant.end_date = today - timedelta(days=1)
    if ended:
        await session.flush()
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="person_role",
            entity_id=f"{person_id}/{function}",
            old_value={"person_id": str(person_id), "function": function},
            new_value={"ended": today.isoformat()},
        )
    return (await functions_by_person(session)).get(person_id, [])


@dataclass(frozen=True)
class FunctionGrant:
    """A function a person holds today, with since when and who granted it."""

    function: str
    since: date
    # None: granted by the system when the instance was set up.
    granted_by_name: str | None


async def function_grants_by_person(
    session: AsyncSession, on: date | None = None
) -> dict[UUID, list[FunctionGrant]]:
    """Per person the functions held on a day, earliest grant per function."""
    granter = Person.__table__.alias("granter")
    rows = await session.execute(
        select(
            PersonRole.person_id,
            PersonRole.role_id,
            PersonRole.start_date,
            granter.c.name,
        )
        .outerjoin(granter, granter.c.id == PersonRole.granted_by_id)
        .where(*_held_on(on or clock.today()))
        .order_by(PersonRole.role_id, PersonRole.start_date)
    )
    result: dict[UUID, dict[str, FunctionGrant]] = defaultdict(dict)
    for person_id, role_id, start, granted_by in rows:
        result[person_id].setdefault(role_id, FunctionGrant(role_id, start, granted_by))
    return {person_id: list(grants.values()) for person_id, grants in result.items()}


async def sole_beheerder_id(session: AsyncSession) -> UUID | None:
    """The one active person who holds beheerder today, when there is only one."""
    rows = await session.execute(
        select(PersonRole.person_id)
        .join(Person, Person.id == PersonRole.person_id)
        .where(
            PersonRole.role_id == BEHEERDER,
            Person.is_active.is_(True),
            *_held_on(clock.today()),
        )
        .distinct()
        .limit(2)
    )
    holders = [row[0] for row in rows]
    return holders[0] if len(holders) == 1 else None


@dataclass(frozen=True)
class CurrentStaffing:
    """What a person is staffed on, on one day."""

    assignment_count: int
    fte_pct: Decimal


async def staffing_by_person(
    session: AsyncSession, day: date
) -> dict[UUID, CurrentStaffing]:
    rows = await session.execute(
        select(
            Allocation.person_id,
            func.count(func.distinct(BudgetLine.assignment_id)),
            func.coalesce(func.sum(Allocation.fte_pct), 0),
        )
        .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
        .where(Allocation.start_date <= day, Allocation.end_date >= day)
        .group_by(Allocation.person_id)
    )
    return {
        person_id: CurrentStaffing(count, Decimal(total))
        for person_id, count, total in rows
    }


# -- bulk reads for the team screen ---------------------------------------------


async def scales_by_person(
    session: AsyncSession, person_ids: list[UUID]
) -> dict[UUID, list[PersonScale]]:
    if not person_ids:
        return {}
    rows = await session.execute(
        select(PersonScale)
        .where(PersonScale.person_id.in_(person_ids))
        .order_by(PersonScale.valid_from)
    )
    result: dict[UUID, list[PersonScale]] = defaultdict(list)
    for scale in rows.scalars():
        result[scale.person_id].append(scale)
    return result


async def hires_by_person(
    session: AsyncSession, person_ids: list[UUID]
) -> dict[UUID, list[Hire]]:
    if not person_ids:
        return {}
    rows = await session.execute(
        select(Hire).where(Hire.person_id.in_(person_ids)).order_by(Hire.valid_from)
    )
    result: dict[UUID, list[Hire]] = defaultdict(list)
    for hire in rows.scalars():
        result[hire.person_id].append(hire)
    return result


async def assignments_by_person(
    session: AsyncSession, period: Period
) -> dict[UUID, set[UUID]]:
    """Per person, the assignments they are staffed on in the period."""
    rows = await session.execute(
        select(Allocation.person_id, BudgetLine.assignment_id)
        .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
        .where(Allocation.start_date <= period[1], Allocation.end_date >= period[0])
        .distinct()
    )
    result: dict[UUID, set[UUID]] = defaultdict(set)
    for person_id, assignment_id in rows:
        result[person_id].add(assignment_id)
    return result


@dataclass(frozen=True)
class RateFacts:
    """What a person bills at on a day; ``None`` where it cannot be derived."""

    billing_scale: int | None
    category: str | None
    monthly_rate_cents: int | None


def rate_facts(
    rates: calc.RateBook, scales: list[PersonScale], person_id: UUID, day: date
) -> RateFacts:
    """Scale, category and monthly rate (R1) of a person on a day.

    A missing scale, rate card or band gives ``None`` for what depends on it:
    the team screen shows a gap, it does not fail.
    """
    calc_scales = tuple(to_calc_scale(s) for s in scales)
    scale = calc.billing_scale(calc_scales, str(person_id), day, day)
    if scale is None:
        return RateFacts(None, None, None)
    try:
        category = rates.category_for_scale(day, scale)
    except calc.CalcError:
        return RateFacts(scale, None, None)
    try:
        rate = rates.monthly_rate_cents(day, category)
    except calc.CalcError:
        return RateFacts(scale, category, None)
    return RateFacts(scale, category, rate)


async def load_rates(session: AsyncSession) -> calc.RateBook:
    return await load_rate_book(session)
