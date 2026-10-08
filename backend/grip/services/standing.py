"""The standing of a person: prospective colleague, colleague, left.

A person enters grip at the moment of hire, often weeks before an account or
an address of the organisation exists. Planning needs that person from that
day. Candidates are not kept here: selection happens in the recruitment
system, and grip only receives who was hired.

Who is the source of what, and when it changes hands:

- Existence and name: grip, from the hire until Wies knows the person; Wies
  after that (``Person.identity_source``).
- Email: always from Wies. It attaches to the person through the person URI,
  never by creating a second person.
- Hired, with a start date; left: recorded here with its ``source``. Today
  that is grip, with the reference of the recruitment system kept. The
  recruitment system or the personnel administration can become the source
  later; only ``source`` changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.core.config import get_settings
from grip.models.assignment import Allocation
from grip.models.person import Person, person_uri
from grip.models.person_standing import (
    ColleagueProposal,
    PersonStanding,
    ProposalState,
    Stage,
    StandingSource,
)
from grip.repositories.person import normalize_email
from grip.services.errors import DomainValidationError, NotFoundError

IDENTITY_GRIP = "grip"
IDENTITY_WIES = "wies"

_ANONYMOUS_NAME = "Vervallen aanstelling"


@dataclass(frozen=True)
class StandingView:
    """What screens need to mark a person who has not started yet."""

    stage: str
    start_date: date | None
    end_date: date | None
    source: str

    @property
    def is_prospective(self) -> bool:
        return self.stage == Stage.prospective.value


_DEFAULT = StandingView(
    stage=Stage.colleague.value, start_date=None, end_date=None, source="grip"
)


def ensure_uri(person: Person) -> str:
    """The person's URI. Rows from before the column got one in the migration."""
    if not person.uri:
        person.uri = person_uri(person.id)
    return person.uri


async def _person(session: AsyncSession, person_id: UUID) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError("Persoon", person_id)
    return person


async def get_standing(session: AsyncSession, person_id: UUID) -> StandingView:
    """The standing of one person. Without a record: an ordinary colleague."""
    row = await session.get(PersonStanding, person_id)
    return _view(row)


def _view(row: PersonStanding | None) -> StandingView:
    if row is None:
        return _DEFAULT
    return StandingView(
        stage=row.stage,
        start_date=row.start_date,
        end_date=row.end_date,
        source=row.source,
    )


async def standings_by_person(
    session: AsyncSession, person_ids: list[UUID] | None = None
) -> dict[UUID, StandingView]:
    query = select(PersonStanding)
    if person_ids is not None:
        if not person_ids:
            return {}
        query = query.where(PersonStanding.person_id.in_(person_ids))
    rows = (await session.execute(query)).scalars().all()
    return {row.person_id: _view(row) for row in rows}


def _check_source(source: str) -> str:
    try:
        return StandingSource(source).value
    except ValueError as exc:
        raise DomainValidationError(f"Onbekende bron: {source}") from exc


async def create_prospective_colleague(
    session: AsyncSession,
    *,
    name: str,
    start_date: date,
    actor: Person | None,
    manager_id: UUID | None = None,
    suborganization: str | None = None,
    source: str = StandingSource.grip.value,
    source_ref: str | None = None,
    source_url: str | None = None,
    propose_to_wies: bool = True,
) -> Person:
    """Record a hire: a person with a start date and no email address yet.

    The person can be planned at once. A proposal for Wies is made alongside,
    so staff there can confirm the new colleague.
    """
    name = name.strip()
    if not name:
        raise DomainValidationError("Een naam is verplicht.")
    if start_date is None:
        raise DomainValidationError("Een startdatum is verplicht.")
    source = _check_source(source)

    person = Person(name=name, email=None, manager_id=manager_id, is_active=True)
    session.add(person)
    await session.flush()
    session.add(
        PersonStanding(
            person_id=person.id,
            stage=Stage.prospective.value,
            start_date=start_date,
            source=source,
            source_ref=(source_ref or "").strip() or None,
            source_url=(source_url or "").strip() or None,
            recorded_by_id=actor.id if actor else None,
        )
    )
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="person",
        entity_id=person.id,
        new_value={
            "name": person.name,
            "stage": Stage.prospective.value,
            "start_date": start_date.isoformat(),
            "source": source,
            "source_ref": source_ref,
        },
    )
    if propose_to_wies:
        await propose_to_wies_as_colleague(
            session, person.id, actor=actor, suborganization=suborganization
        )
    await session.flush()
    return person


async def set_start_date(
    session: AsyncSession,
    person_id: UUID,
    start_date: date,
    *,
    actor: Person | None,
) -> PersonStanding:
    """Move the start date of a prospective colleague."""
    row = await session.get(PersonStanding, person_id)
    if row is None or row.stage != Stage.prospective.value:
        raise DomainValidationError(
            "Alleen van een aanstaande collega kan de startdatum worden gewijzigd."
        )
    old = row.start_date
    row.start_date = start_date
    await session.flush()
    if old != start_date:
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="person_standing",
            entity_id=person_id,
            old_value={"start_date": old.isoformat() if old else None},
            new_value={"start_date": start_date.isoformat()},
        )
    return row


async def mark_left(
    session: AsyncSession,
    person_id: UUID,
    end_date: date,
    *,
    actor: Person | None,
    source: str = StandingSource.grip.value,
) -> PersonStanding:
    await _person(session, person_id)
    source = _check_source(source)
    row = await session.get(PersonStanding, person_id)
    old_stage = row.stage if row else Stage.colleague.value
    if row is None:
        row = PersonStanding(person_id=person_id, stage=Stage.left.value, source=source)
        session.add(row)
    row.stage = Stage.left.value
    row.end_date = end_date
    row.source = source
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="person_standing",
        entity_id=person_id,
        old_value={"stage": old_stage},
        new_value={"stage": Stage.left.value, "end_date": end_date.isoformat()},
    )
    return row


# -- the proposal to Wies -------------------------------------------------------


async def propose_to_wies_as_colleague(
    session: AsyncSession,
    person_id: UUID,
    *,
    actor: Person | None,
    suborganization: str | None = None,
) -> ColleagueProposal:
    """Make or reopen the proposal "new colleague" for Wies."""
    person = await _person(session, person_id)
    ensure_uri(person)
    merk = (suborganization or "").strip() or (
        get_settings().WIES_DEFAULT_SUBORGANIZATION.strip() or None
    )
    proposal = await session.get(ColleagueProposal, person_id)
    if proposal is None:
        proposal = ColleagueProposal(
            person_id=person_id,
            suborganization=merk,
            state=ProposalState.open.value,
        )
        session.add(proposal)
    else:
        if merk:
            proposal.suborganization = merk
        if proposal.state in (
            ProposalState.withdrawn.value,
            ProposalState.declined.value,
        ):
            proposal.state = ProposalState.open.value
            proposal.withdrawn_reason = None
            proposal.decided_at = None
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="colleague_proposal",
        entity_id=person_id,
        new_value={
            "state": proposal.state,
            "suborganization": proposal.suborganization,
        },
    )
    return proposal


async def withdraw_hire(
    session: AsyncSession,
    person_id: UUID,
    *,
    actor: Person | None,
    reason: str,
    today: date | None = None,
) -> Person:
    """A recorded hire falls through.

    The planning of the person goes, the person can no longer be picked, the
    proposal to Wies is withdrawn so Wies removes its record, and the person
    record itself is removed after the retention period.
    """
    reason = reason.strip()
    if not reason:
        raise DomainValidationError("Een reden is verplicht.")
    person = await _person(session, person_id)
    row = await session.get(PersonStanding, person_id)
    if row is None or row.stage != Stage.prospective.value:
        raise DomainValidationError(
            "Alleen een aanstelling die nog niet is begonnen kan vervallen."
        )
    if person.oidc_subject is not None:
        raise DomainValidationError(
            "Deze persoon heeft al ingelogd en is dus al begonnen."
        )

    # Planning goes through the service layer, so closed months and closed
    # years are respected and each removal is audited.
    from grip.services import assignments as assignment_service

    allocation_ids = list(
        (
            await session.execute(
                select(Allocation.id).where(Allocation.person_id == person_id)
            )
        ).scalars()
    )
    for allocation_id in allocation_ids:
        await assignment_service.delete_allocation(session, allocation_id, actor=actor)

    day = today or date.today()
    row.stage = Stage.left.value
    row.end_date = None
    row.remove_after = day + timedelta(days=get_settings().PROSPECTIVE_RETENTION_DAYS)
    person.is_active = False

    proposal = await session.get(ColleagueProposal, person_id)
    if proposal is not None:
        proposal.state = ProposalState.withdrawn.value
        proposal.withdrawn_reason = reason
        proposal.decided_at = datetime.now(UTC)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="person_standing",
        entity_id=person_id,
        old_value={"stage": Stage.prospective.value},
        new_value={
            "stage": "withdrawn",
            "reason": reason,
            "remove_after": row.remove_after.isoformat(),
            "allocations_removed": len(allocation_ids),
        },
    )
    return person


async def purge_withdrawn(session: AsyncSession, *, today: date | None = None) -> int:
    """Remove the person records of hires that fell through, once due.

    The row is deleted when nothing refers to it. Where something does (an
    audit trail keeps only the id, but another table may hold a reference),
    the name is replaced and every identifying field is cleared.
    """
    day = today or date.today()
    due = list(
        (
            await session.execute(
                select(PersonStanding.person_id).where(
                    PersonStanding.remove_after.is_not(None),
                    PersonStanding.remove_after <= day,
                )
            )
        ).scalars()
    )
    removed = 0
    for person_id in due:
        try:
            async with session.begin_nested():
                await session.execute(delete(Person).where(Person.id == person_id))
        except IntegrityError:
            person = await session.get(Person, person_id)
            row = await session.get(PersonStanding, person_id)
            if person is None or row is None:
                continue
            person.name = _ANONYMOUS_NAME
            person.email = None
            person.wies_public_id = None
            person.manager_id = None
            row.remove_after = None
            row.source_ref = None
            row.source_url = None
            await session.execute(
                delete(ColleagueProposal).where(
                    ColleagueProposal.person_id == person_id
                )
            )
            await session.flush()
        else:
            session.expire_all()
        record_audit(
            session,
            actor=None,
            action=DELETE,
            entity="person",
            entity_id=person_id,
            new_value={"reason": "retention_after_withdrawn_hire"},
        )
        removed += 1
    return removed


@dataclass(frozen=True)
class OutgoingProposal:
    person_uri: str
    name: str
    suborganization: str | None
    start_date: date | None
    # open or withdrawn, as Wies needs to hear it. A proposal Wies confirmed
    # stays "open" towards Wies: it is the same request, already granted.
    state: str


async def outgoing_proposals(session: AsyncSession) -> list[OutgoingProposal]:
    """What Wies fetches: the new colleagues grip proposes, and withdrawals."""
    rows = (
        await session.execute(
            select(ColleagueProposal, Person, PersonStanding)
            .join(Person, Person.id == ColleagueProposal.person_id)
            .outerjoin(
                PersonStanding, PersonStanding.person_id == ColleagueProposal.person_id
            )
            .order_by(func.lower(Person.name), Person.id)
        )
    ).all()
    result: list[OutgoingProposal] = []
    for proposal, person, standing in rows:
        withdrawn = proposal.state == ProposalState.withdrawn.value
        result.append(
            OutgoingProposal(
                person_uri=ensure_uri(person),
                # A withdrawn hire is announced by its key only.
                name="" if withdrawn else person.name,
                suborganization=None if withdrawn else proposal.suborganization,
                start_date=None
                if withdrawn or standing is None
                else standing.start_date,
                state=ProposalState.withdrawn.value
                if withdrawn
                else ProposalState.open.value,
            )
        )
    return result


async def record_wies_answer(
    session: AsyncSession,
    *,
    person_uri: str,
    state: str,
    wies_public_id: str | None,
    actor: Person | None,
) -> bool:
    """Store what Wies decided on a proposal. Returns whether anything changed."""
    if state not in (ProposalState.confirmed.value, ProposalState.declined.value):
        return False
    person = (
        await session.execute(select(Person).where(Person.uri == person_uri))
    ).scalar_one_or_none()
    if person is None:
        return False
    proposal = await session.get(ColleagueProposal, person.id)
    if proposal is None or proposal.state == ProposalState.withdrawn.value:
        return False
    changed = False
    if proposal.state != state:
        old = proposal.state
        proposal.state = state
        proposal.decided_at = datetime.now(UTC)
        changed = True
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity="colleague_proposal",
            entity_id=person.id,
            old_value={"state": old},
            new_value={"state": state, "source": "wies"},
        )
    if (
        state == ProposalState.confirmed.value
        and wies_public_id
        and person.wies_public_id != wies_public_id
    ):
        person.wies_public_id = wies_public_id
        changed = True
    await session.flush()
    return changed


async def attach_identity_from_wies(
    session: AsyncSession,
    person_id: UUID,
    *,
    email: str,
    name: str | None,
    wies_public_id: str | None,
    actor: Person | None,
) -> Person:
    """The address arrives from Wies and attaches to the person grip has.

    From here Wies is the source of who this person is, and the person can
    log in: the first login binds on the verified address.
    """
    person = await _person(session, person_id)
    address = normalize_email(email)
    if "@" not in address:
        raise DomainValidationError("Dit is geen geldig e-mailadres.")
    other = (
        await session.execute(
            select(Person.id).where(
                func.lower(Person.email) == address, Person.id != person_id
            )
        )
    ).first()
    if other is not None:
        raise DomainValidationError(
            "Er is al een andere persoon met dit e-mailadres. Voeg de twee eerst samen."
        )
    old = {
        "email": person.email,
        "name": person.name,
        "identity_source": person.identity_source,
    }
    person.email = address
    if name and name.strip():
        person.name = name.strip()
    if wies_public_id:
        person.wies_public_id = wies_public_id
    person.identity_source = IDENTITY_WIES

    row = await session.get(PersonStanding, person_id)
    if row is not None and row.stage == Stage.prospective.value:
        row.stage = Stage.colleague.value
    proposal = await session.get(ColleagueProposal, person_id)
    if proposal is not None and proposal.state == ProposalState.open.value:
        proposal.state = ProposalState.confirmed.value
        proposal.decided_at = datetime.now(UTC)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="person",
        entity_id=person.id,
        old_value=old,
        new_value={
            "email": person.email,
            "name": person.name,
            "identity_source": IDENTITY_WIES,
            "source": "wies",
        },
    )
    return person
