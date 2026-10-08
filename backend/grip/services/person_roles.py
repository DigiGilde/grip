"""The roles of a person: which catalogue roles someone can be staffed in.

Read with ``roles_of_person`` (or ``roles_of_persons`` for several at once).
The links come from the person's skills in Wies, as proposals a beheerder
confirms, or are set by the beheerder by hand. A role is staffing data
(class C).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.integrations.wies.client import WiesColleague
from grip.models.catalogue_role import (
    ROLE_SOURCE_MANUAL,
    ROLE_SOURCE_WIES,
    CatalogueRole,
    PersonCatalogueRole,
)
from grip.models.person import Person
from grip.services.errors import DomainValidationError, NotFoundError

ADD_ROLE = "add_role"
DROP_ROLE = "drop_role"


@dataclass(frozen=True)
class PersonRole:
    """A role of a person, with where the link came from."""

    role: CatalogueRole
    # wies | manual
    source: str


@dataclass(frozen=True)
class RoleProposal:
    """A change to someone's roles that Wies gives rise to."""

    action: str  # add_role | drop_role
    person_id: uuid.UUID
    person_name: str
    role_id: uuid.UUID
    role_name: str
    reason: str

    @property
    def key(self) -> tuple[str, uuid.UUID, uuid.UUID]:
        return (self.action, self.person_id, self.role_id)


# --- reading ------------------------------------------------------------------


async def roles_of_persons(
    db: AsyncSession,
    person_ids: Iterable[uuid.UUID],
    *,
    include_inactive: bool = False,
) -> dict[uuid.UUID, list[CatalogueRole]]:
    """The catalogue roles of each person, by name. Persons without roles are absent."""
    ids = list(dict.fromkeys(person_ids))
    if not ids:
        return {}
    stmt = (
        select(PersonCatalogueRole.person_id, CatalogueRole)
        .join(CatalogueRole, CatalogueRole.id == PersonCatalogueRole.role_id)
        .where(PersonCatalogueRole.person_id.in_(ids))
        .order_by(func.lower(CatalogueRole.name))
    )
    if not include_inactive:
        stmt = stmt.where(CatalogueRole.is_active.is_(True))
    found: dict[uuid.UUID, list[CatalogueRole]] = defaultdict(list)
    for person_id, role in (await db.execute(stmt)).all():
        found[person_id].append(role)
    return dict(found)


async def roles_of_person(
    db: AsyncSession, person_id: uuid.UUID, *, include_inactive: bool = False
) -> list[CatalogueRole]:
    """The catalogue roles this person can be staffed in, by name.

    Empty when grip knows none. A caller that wants to propose a role for a
    person (the intended person on a budget line) takes the only one when
    there is exactly one, and leaves the choice to the user otherwise.
    """
    return (
        await roles_of_persons(db, [person_id], include_inactive=include_inactive)
    ).get(person_id, [])


async def person_role_links(db: AsyncSession, person_id: uuid.UUID) -> list[PersonRole]:
    """The roles of a person with the source of each link, for the person page."""
    rows = await db.execute(
        select(CatalogueRole, PersonCatalogueRole.source)
        .join(PersonCatalogueRole, PersonCatalogueRole.role_id == CatalogueRole.id)
        .where(PersonCatalogueRole.person_id == person_id)
        .order_by(func.lower(CatalogueRole.name))
    )
    return [PersonRole(role=role, source=source) for role, source in rows.all()]


# --- by hand ------------------------------------------------------------------


async def set_person_roles(
    db: AsyncSession,
    person_id: uuid.UUID,
    role_ids: Iterable[uuid.UUID],
    *,
    actor: Person | None,
) -> list[PersonRole]:
    """Make the roles of a person exactly this set.

    A role that is added becomes a manual link. A role that stays keeps its
    source. A role that is taken away is removed whatever its source; when
    Wies still has it, the next reconciliation proposes it again.
    """
    if await db.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    wanted = list(dict.fromkeys(role_ids))
    if wanted:
        known = set(
            (
                await db.execute(
                    select(CatalogueRole.id).where(CatalogueRole.id.in_(wanted))
                )
            )
            .scalars()
            .all()
        )
        missing = [r for r in wanted if r not in known]
        if missing:
            raise DomainValidationError("Een van de gekozen rollen bestaat niet.")
    current = {
        link.role_id: link
        for link in (
            await db.execute(
                select(PersonCatalogueRole).where(
                    PersonCatalogueRole.person_id == person_id
                )
            )
        )
        .scalars()
        .all()
    }
    added = [r for r in wanted if r not in current]
    removed = [r for r in current if r not in wanted]
    for role_id in added:
        db.add(
            PersonCatalogueRole(
                person_id=person_id, role_id=role_id, source=ROLE_SOURCE_MANUAL
            )
        )
    for role_id in removed:
        await db.delete(current[role_id])
    if added or removed:
        await db.flush()
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="person_roles",
            entity_id=person_id,
            old_value={"role_ids": sorted(str(r) for r in current)},
            new_value={"role_ids": sorted(str(r) for r in wanted)},
        )
    return await person_role_links(db, person_id)


# --- following Wies -----------------------------------------------------------


def _wies_roles(
    colleague: WiesColleague,
    by_wies_id: dict[str, CatalogueRole],
    by_name: dict[str, CatalogueRole],
) -> dict[uuid.UUID, CatalogueRole]:
    """The catalogue roles the skills of a colleague stand for.

    On the public id of the skill; on its name for an answer of Wies that
    carries no ids. A skill the catalogue does not hold is left out: fetch
    the roles from Wies first.
    """
    found: dict[uuid.UUID, CatalogueRole] = {}
    if colleague.skill_ids:
        for skill_id in colleague.skill_ids:
            role = by_wies_id.get(skill_id)
            if role is not None:
                found[role.id] = role
        return found
    for name in colleague.skills:
        role = by_name.get(" ".join(name.split()).lower())
        if role is not None:
            found[role.id] = role
    return found


def propose_role_changes(
    colleagues: Iterable[WiesColleague],
    persons: Iterable[Person],
    roles: Iterable[CatalogueRole],
    links: Iterable[PersonCatalogueRole],
) -> list[RoleProposal]:
    """What Wies suggests changing in the roles of grip's persons.

    - A skill of the colleague in Wies that the person does not have as a
      role here: add it.
    - A role that came from Wies and that the colleague no longer has there:
      drop it.
    - A role set by hand is never proposed for dropping, and a role the
      person already has by hand is not proposed again.

    Only for active persons Wies knows by their address.
    """
    roles = list(roles)
    by_wies_id = {r.wies_public_id: r for r in roles if r.wies_public_id}
    by_name = {r.name.lower(): r for r in roles}
    role_by_id = {r.id: r for r in roles}
    by_email = {c.email: c for c in colleagues}
    links_by_person: dict[uuid.UUID, dict[uuid.UUID, PersonCatalogueRole]] = (
        defaultdict(dict)
    )
    for link in links:
        links_by_person[link.person_id][link.role_id] = link

    proposals: list[RoleProposal] = []
    for person in persons:
        email = (person.email or "").strip().lower()
        colleague = by_email.get(email) if email else None
        if colleague is None or not person.is_active:
            continue
        in_wies = _wies_roles(colleague, by_wies_id, by_name)
        held = links_by_person.get(person.id, {})
        for role_id, role in in_wies.items():
            if role_id not in held and role.is_active:
                proposals.append(
                    RoleProposal(
                        action=ADD_ROLE,
                        person_id=person.id,
                        person_name=person.name,
                        role_id=role_id,
                        role_name=role.name,
                        reason="Heeft deze rol in Wies.",
                    )
                )
        for role_id, link in held.items():
            if link.source == ROLE_SOURCE_WIES and role_id not in in_wies:
                role = role_by_id.get(role_id)
                proposals.append(
                    RoleProposal(
                        action=DROP_ROLE,
                        person_id=person.id,
                        person_name=person.name,
                        role_id=role_id,
                        role_name=role.name if role else "",
                        reason="Heeft deze rol in Wies niet meer.",
                    )
                )
    return sorted(
        proposals, key=lambda p: (p.person_name.lower(), p.action, p.role_name.lower())
    )


async def current_role_proposals(
    db: AsyncSession, colleagues: Iterable[WiesColleague]
) -> list[RoleProposal]:
    persons = (await db.execute(select(Person))).scalars().all()
    roles = (await db.execute(select(CatalogueRole))).scalars().all()
    links = (await db.execute(select(PersonCatalogueRole))).scalars().all()
    return propose_role_changes(colleagues, persons, roles, links)


async def apply_role_proposals(
    db: AsyncSession,
    confirmed: Iterable[tuple[str, uuid.UUID, uuid.UUID]],
    proposals: Iterable[RoleProposal],
    *,
    actor: Person | None,
) -> list[tuple[tuple[str, uuid.UUID, uuid.UUID], bool]]:
    """Apply the confirmed changes that Wies still gives rise to.

    Returns each confirmed (action, person, role) with whether it was applied.
    Dropping only ever removes a link that came from Wies.
    """
    current = {p.key: p for p in proposals}
    outcome: list[tuple[tuple[str, uuid.UUID, uuid.UUID], bool]] = []
    for key in confirmed:
        proposal = current.get(key)
        if proposal is None:
            outcome.append((key, False))
            continue
        action, person_id, role_id = key
        if action == ADD_ROLE:
            exists = (
                await db.execute(
                    select(PersonCatalogueRole.id).where(
                        PersonCatalogueRole.person_id == person_id,
                        PersonCatalogueRole.role_id == role_id,
                    )
                )
            ).first()
            if exists is None:
                db.add(
                    PersonCatalogueRole(
                        person_id=person_id, role_id=role_id, source=ROLE_SOURCE_WIES
                    )
                )
        else:
            await db.execute(
                delete(PersonCatalogueRole).where(
                    PersonCatalogueRole.person_id == person_id,
                    PersonCatalogueRole.role_id == role_id,
                    PersonCatalogueRole.source == ROLE_SOURCE_WIES,
                )
            )
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="person_roles",
            entity_id=person_id,
            new_value={
                "action": action,
                "role_id": str(role_id),
                "role": proposal.role_name,
                "source": "wies",
            },
        )
        outcome.append((key, True))
    await db.flush()
    return outcome
