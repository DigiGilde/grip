"""Compare the colleagues of Wies with grip's persons.

Login to grip is by pre-provisioned person, so this comparison is how people
get access. It only proposes: nothing is created or deactivated until a
beheerder confirms the change, and a confirmed change is applied only when
Wies still gives rise to it at that moment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.integrations.wies.client import WiesColleague
from grip.models.person import Person
from grip.schema.integrations_wies import AppliedChange, PersonProposal

ADD = "add"
DEACTIVATE = "deactivate"
REACTIVATE = "reactivate"
RENAME = "rename"

# Addresses that are never people in Wies: the stand-in of local development.
_IGNORED_SUFFIXES = (".invalid",)


@dataclass(frozen=True)
class _Scope:
    """Which merken of Wies this instance takes its people from. Empty: all."""

    suborganizations: frozenset[str]

    def includes(self, colleague: WiesColleague) -> bool:
        if not self.suborganizations:
            return True
        return (
            colleague.suborganization or ""
        ).strip().lower() in self.suborganizations


def parse_scope(value: str) -> frozenset[str]:
    return frozenset(part.strip().lower() for part in value.split(",") if part.strip())


def propose(
    colleagues: Iterable[WiesColleague],
    persons: Iterable[Person],
    *,
    suborganizations: frozenset[str] = frozenset(),
) -> list[PersonProposal]:
    """What a beheerder may want to change, given Wies and grip as they are.

    - A colleague with an active account in Wies, within the merken of this
      instance, who is no person in grip: add.
    - A person in grip whom Wies knows without an active account: deactivate.
    - A person in grip whom Wies does not know at all: deactivate, with that
      reason. Wies may simply not hold everyone, so this one deserves a look.
    - An inactive person in grip with an active account in Wies: reactivate.
    - A different name in Wies: rename, because Wies is the source of people.

    A colleague outside the merken of this instance is never proposed for
    addition, and is not a reason to deactivate someone either.
    """
    scope = _Scope(suborganizations)
    by_email = {c.email: c for c in colleagues}
    proposals: list[PersonProposal] = []
    known: set[str] = set()

    for person in persons:
        email = person.email.strip().lower()
        known.add(email)
        if email.endswith(_IGNORED_SUFFIXES):
            continue
        colleague = by_email.get(email)

        def describe(
            action: str, reason: str, *, name: str | None = None
        ) -> PersonProposal:
            return PersonProposal(
                action=action,
                email=email,
                name=name or person.name,
                person_id=person.id,
                current_name=person.name,
                reason=reason,
                suborganization=colleague.suborganization if colleague else None,
                skills=list(colleague.skills) if colleague else [],
            )

        if colleague is None:
            if person.is_active:
                proposals.append(describe(DEACTIVATE, "Niet bekend in Wies."))
            continue
        if person.is_active and not colleague.active:
            proposals.append(
                describe(DEACTIVATE, "Heeft in Wies geen actief account meer.")
            )
            continue
        if not person.is_active and colleague.active and scope.includes(colleague):
            proposals.append(
                describe(REACTIVATE, "Heeft in Wies weer een actief account.")
            )
        if colleague.name and colleague.name != person.name:
            proposals.append(
                describe(RENAME, "De naam in Wies is anders.", name=colleague.name)
            )

    for colleague in by_email.values():
        if (
            colleague.email in known
            or not colleague.active
            or not scope.includes(colleague)
        ):
            continue
        proposals.append(
            PersonProposal(
                action=ADD,
                email=colleague.email,
                name=colleague.name,
                reason="Collega in Wies, nog geen persoon in grip.",
                suborganization=colleague.suborganization,
                skills=list(colleague.skills),
            )
        )

    order = {ADD: 0, REACTIVATE: 1, RENAME: 2, DEACTIVATE: 3}
    return sorted(proposals, key=lambda p: (order[p.action], p.name.lower(), p.email))


async def load_persons(db: AsyncSession) -> list[Person]:
    return list(
        (await db.execute(select(Person).order_by(Person.name))).scalars().all()
    )


async def apply_confirmed(
    db: AsyncSession,
    confirmed: Iterable[tuple[str, str]],
    proposals: Iterable[PersonProposal],
    *,
    actor: Person,
) -> list[AppliedChange]:
    """Apply the confirmed changes that are still proposed.

    ``confirmed`` holds (action, email) pairs. A pair that Wies no longer gives
    rise to is reported as not applied; so is deactivating yourself.
    """
    current = {(p.action, p.email): p for p in proposals}
    persons = {p.email.strip().lower(): p for p in await load_persons(db)}
    applied: list[AppliedChange] = []

    for action, raw_email in confirmed:
        email = raw_email.strip().lower()
        proposal = current.get((action, email))
        if proposal is None:
            applied.append(
                AppliedChange(
                    action=action,
                    email=email,
                    applied=False,
                    reason="Wordt niet (meer) voorgesteld op grond van Wies.",
                )
            )
            continue

        person = persons.get(email)
        if action == ADD:
            if person is not None:
                applied.append(
                    AppliedChange(
                        action=action,
                        email=email,
                        person_id=person.id,
                        applied=False,
                        reason="Deze persoon bestaat al.",
                    )
                )
                continue
            person = Person(name=proposal.name, email=email, is_active=True)
            db.add(person)
            await db.flush()
            persons[email] = person
            record_audit(
                db,
                actor=actor,
                action=CREATE,
                entity="person",
                entity_id=person.id,
                new_value={"name": person.name, "email": email, "source": "wies"},
            )
        elif person is None:
            applied.append(
                AppliedChange(
                    action=action,
                    email=email,
                    applied=False,
                    reason="Deze persoon bestaat niet in grip.",
                )
            )
            continue
        elif action == DEACTIVATE:
            if person.id == actor.id:
                applied.append(
                    AppliedChange(
                        action=action,
                        email=email,
                        person_id=person.id,
                        applied=False,
                        reason="Je kunt jezelf niet deactiveren.",
                    )
                )
                continue
            person.is_active = False
            record_audit(
                db,
                actor=actor,
                action=UPDATE,
                entity="person",
                entity_id=person.id,
                old_value={"is_active": True},
                new_value={"is_active": False, "source": "wies"},
            )
        elif action == REACTIVATE:
            person.is_active = True
            record_audit(
                db,
                actor=actor,
                action=UPDATE,
                entity="person",
                entity_id=person.id,
                old_value={"is_active": False},
                new_value={"is_active": True, "source": "wies"},
            )
        elif action == RENAME:
            old_name = person.name
            person.name = proposal.name
            record_audit(
                db,
                actor=actor,
                action=UPDATE,
                entity="person",
                entity_id=person.id,
                old_value={"name": old_name},
                new_value={"name": person.name, "source": "wies"},
            )
        applied.append(
            AppliedChange(action=action, email=email, person_id=person.id, applied=True)
        )

    await db.flush()
    return applied
