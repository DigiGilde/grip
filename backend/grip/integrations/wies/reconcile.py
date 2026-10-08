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
from grip.integrations.wies.client import WiesColleague, WiesProposalAnswer
from grip.models.person import Person
from grip.models.person_standing import ColleagueProposal, PersonStanding
from grip.schema.integrations_wies import (
    AppliedChange,
    OutgoingProposalState,
    PersonProposal,
)
from grip.services import standing
from grip.services.errors import DomainValidationError

ADD = "add"
DEACTIVATE = "deactivate"
REACTIVATE = "reactivate"
RENAME = "rename"
LINK = "link"

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
    - A person grip has without an address (a prospective colleague) whom
      Wies knows with one: link. Recognised by the person URI Wies holds; or,
      when Wies has no URI for that colleague, suggested on an equal name so
      the beheerder can prevent a second person for the same human.

    A colleague outside the merken of this instance is never proposed for
    addition, and is not a reason to deactivate someone either. A person
    without an address is never proposed for deactivation: Wies cannot know
    them by address yet.
    """
    scope = _Scope(suborganizations)
    colleagues = list(colleagues)
    persons = list(persons)
    by_email = {c.email: c for c in colleagues if c.email}
    by_uri = {c.grip_person_uri: c for c in colleagues if c.grip_person_uri}
    proposals: list[PersonProposal] = []
    known: set[str] = set()
    linked: set[str] = set()
    without_address: list[Person] = []

    for person in persons:
        email = (person.email or "").strip().lower()
        if not email:
            colleague = by_uri.get(person.uri) if person.uri else None
            if colleague is not None and colleague.email:
                linked.add(colleague.email)
                proposals.append(
                    PersonProposal(
                        action=LINK,
                        email=colleague.email,
                        name=colleague.name or person.name,
                        match="uri",
                        person_id=person.id,
                        current_name=person.name,
                        reason=(
                            "Wies heeft het e-mailadres van deze aanstaande collega."
                        ),
                        suborganization=colleague.suborganization,
                        skills=list(colleague.skills),
                    )
                )
            elif person.is_active is not False:
                without_address.append(person)
            continue
        known.add(email)
        if email.endswith(_IGNORED_SUFFIXES):
            continue
        colleague = by_email.get(email)

        def describe(
            action: str,
            reason: str,
            *,
            name: str | None = None,
            person: Person = person,
            email: str = email,
            colleague: WiesColleague | None = colleague,
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

    by_name: dict[str, list[Person]] = {}
    for person in without_address:
        by_name.setdefault(person.name.strip().lower(), []).append(person)

    for colleague in by_email.values():
        if (
            colleague.email in known
            or colleague.email in linked
            or not colleague.active
            or not scope.includes(colleague)
        ):
            continue
        same_name = by_name.get(colleague.name.strip().lower(), [])
        if not colleague.grip_person_uri and len(same_name) == 1:
            person = same_name[0]
            proposals.append(
                PersonProposal(
                    action=LINK,
                    email=colleague.email,
                    name=colleague.name,
                    match="name",
                    person_id=person.id,
                    current_name=person.name,
                    reason=(
                        "Grip heeft een aanstaande collega met dezelfde naam. "
                        "Is dit dezelfde persoon, koppel dan; anders toevoegen."
                    ),
                    suborganization=colleague.suborganization,
                    skills=list(colleague.skills),
                )
            )
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

    order = {LINK: 0, ADD: 1, REACTIVATE: 2, RENAME: 3, DEACTIVATE: 4}
    return sorted(proposals, key=lambda p: (order[p.action], p.name.lower(), p.email))


async def load_persons(db: AsyncSession) -> list[Person]:
    return list(
        (await db.execute(select(Person).order_by(Person.name))).scalars().all()
    )


async def apply_confirmed(
    db: AsyncSession,
    confirmed: Iterable[tuple],
    proposals: Iterable[PersonProposal],
    *,
    actor: Person,
    colleagues: Iterable[WiesColleague] | None = None,
) -> list[AppliedChange]:
    """Apply the confirmed changes that are still proposed.

    ``confirmed`` holds (action, email) pairs. A pair that Wies no longer gives
    rise to is reported as not applied; so is deactivating yourself.
    """
    proposals = list(proposals)
    current = {(p.action, p.email): p for p in proposals}
    colleagues_by_email = {c.email: c for c in colleagues or () if c.email}
    all_persons = await load_persons(db)
    persons = {p.email.strip().lower(): p for p in all_persons if p.email}
    persons_by_id = {p.id: p for p in all_persons}
    applied: list[AppliedChange] = []
    # An address that was linked in this run is not also added.
    linked_now: set[str] = set()

    for item in confirmed:
        action, raw_email = item[0], item[1]
        wanted_person_id = item[2] if len(item) > 2 else None
        email = raw_email.strip().lower()
        proposal = current.get((action, email))
        if action == LINK and proposal is not None:
            target = persons_by_id.get(proposal.person_id)
            if wanted_person_id is not None and wanted_person_id != proposal.person_id:
                proposal = None
            elif target is None:
                proposal = None
            else:
                colleague = colleagues_by_email.get(email)
                try:
                    await standing.attach_identity_from_wies(
                        db,
                        target.id,
                        email=email,
                        name=proposal.name,
                        wies_public_id=(colleague.public_id or None)
                        if colleague
                        else None,
                        actor=actor,
                    )
                except DomainValidationError as exc:
                    applied.append(
                        AppliedChange(
                            action=action,
                            email=email,
                            person_id=target.id,
                            applied=False,
                            reason=str(exc),
                        )
                    )
                    continue
                persons[email] = target
                linked_now.add(email)
                applied.append(
                    AppliedChange(
                        action=action, email=email, person_id=target.id, applied=True
                    )
                )
                continue
        if action == ADD and email in linked_now:
            applied.append(
                AppliedChange(
                    action=action,
                    email=email,
                    applied=False,
                    reason="Dit adres is zojuist aan een bestaande persoon gekoppeld.",
                )
            )
            continue
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
            colleague = colleagues_by_email.get(email)
            person = Person(
                name=proposal.name,
                email=email,
                is_active=True,
                identity_source="wies",
                wies_public_id=(colleague.public_id or None) if colleague else None,
            )
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


async def record_answers(
    db: AsyncSession, answers: Iterable[WiesProposalAnswer], *, actor: Person | None
) -> int:
    """Store what staff of Wies decided on the colleagues grip proposed."""
    changed = 0
    for answer in answers:
        if await standing.record_wies_answer(
            db,
            person_uri=answer.person_uri,
            state=answer.state,
            wies_public_id=answer.public_id,
            actor=actor,
        ):
            changed += 1
    return changed


async def outgoing_states(db: AsyncSession) -> list[OutgoingProposalState]:
    """The new colleagues grip proposed to Wies, with the state grip knows."""
    rows = (
        await db.execute(
            select(ColleagueProposal, Person, PersonStanding)
            .join(Person, Person.id == ColleagueProposal.person_id)
            .outerjoin(
                PersonStanding, PersonStanding.person_id == ColleagueProposal.person_id
            )
            .order_by(Person.name)
        )
    ).all()
    return [
        OutgoingProposalState(
            person_id=person.id,
            name=person.name,
            suborganization=proposal.suborganization,
            start_date=row.start_date if row else None,
            state=proposal.state,
        )
        for proposal, person, row in rows
    ]
