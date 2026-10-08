"""Assignments: lifecycle, roles, budget lines and inzet.

Routes and the federation module call these functions; they never touch the
domain tables themselves (ADR 0015).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.core.config import get_settings
from grip.models.assignment import (
    ASSIGNMENT_KINDS,
    ASSIGNMENT_STATUSES,
    BUDGET_LINE_KINDS,
    ROLE_MANAGER,
    ROLE_OWNER,
    Allocation,
    Assignment,
    AssignmentRole,
    BudgetLine,
)
from grip.models.month_close import MonthCloseLine
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.rates import RATE_CATEGORIES
from grip.services import events, periods
from grip.services.errors import (
    DomainValidationError,
    IllegalTransitionError,
    NotFoundError,
)
from grip.services.guards import (
    audit_fields,
    audit_value,
    ensure_closed_months_unchanged,
    ensure_years_open,
    years_between,
)
from grip.services.phase import VERBALLY_AGREED, counterparty_status

# The lifecycle of an assignment. Every change of status goes through
# ``transition``; nothing else writes ``Assignment.status``.
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"requested", "quoted", "cancelled"}),
    "requested": frozenset({"quoted", "rejected", "cancelled"}),
    "quoted": frozenset({"verbally_agreed", "accepted", "rejected", "cancelled"}),
    # Optional step: the client said yes, the signature has to follow. Back
    # to quoted when the word is withdrawn or the quote has to change.
    "verbally_agreed": frozenset({"accepted", "quoted", "rejected", "cancelled"}),
    "accepted": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"completed", "cancelled"}),
    "completed": frozenset({"accounted", "in_progress"}),
    "accounted": frozenset(),
    "rejected": frozenset({"draft", "quoted", "cancelled"}),
    "cancelled": frozenset(),
}
# An internal assignment has no client to quote to: it goes straight from
# draft to accepted.
_INTERNAL_EXTRA: dict[str, frozenset[str]] = {"draft": frozenset({"accepted"})}

_ASSIGNMENT_FIELDS = (
    "uri",
    "name",
    "kind",
    "status",
    "client_organisation_id",
    "contractor_organisation_id",
    "parent_assignment_uri",
    "context_refs",
    "client_contact",
    "quote_date",
    "quoted_amount_cents",
    "start_date",
    "end_date",
)
_EDITABLE_ASSIGNMENT_FIELDS = frozenset(
    {
        "name",
        "kind",
        "client_organisation_id",
        "contractor_organisation_id",
        "parent_assignment_uri",
        "context_refs",
        "client_contact",
        "quoted_amount_cents",
        "start_date",
        "end_date",
        "notes",
    }
)
_LINE_FIELDS = (
    "assignment_id",
    "description",
    "kind",
    "position",
    "role",
    "fte",
    "rate_category",
    "period_source",
    "start_date",
    "end_date",
    "amount_cents",
    "year",
)
_ALLOCATION_FIELDS = (
    "person_id",
    "budget_line_id",
    "period_source",
    "start_date",
    "end_date",
    "fte_pct",
)


def mint_uri(segment: str, entity_id: UUID) -> str:
    """URI of something this instance creates: ``{base}/id/{segment}/{uuid}``."""
    base = get_settings().INSTANCE_BASE_URI.rstrip("/")
    return f"{base}/id/{segment}/{entity_id}"


def share_with_instance(assignment: Assignment, instance_uri: str) -> None:
    """Record that this assignment is shared with another grip instance.

    Not a setting: it follows from an exchange with that instance (a request
    received from it or sent to it, a quote offered to it or received from
    it). Sharing once is enough; a later exchange with the same instance
    leaves the moment as it was.
    """
    wanted = instance_uri.strip().rstrip("/")
    if not wanted:
        return
    current = (assignment.shared_with_instance_uri or "").rstrip("/")
    if current == wanted:
        return
    assignment.shared_with_instance_uri = wanted
    assignment.shared_at = datetime.now(UTC)


def is_shared_with(assignment: Assignment, instance_uri: str | None) -> bool:
    if not instance_uri or not assignment.shared_with_instance_uri:
        return False
    return assignment.shared_with_instance_uri.rstrip("/") == (
        instance_uri.strip().rstrip("/")
    )


def allowed_transitions(assignment: Assignment) -> frozenset[str]:
    allowed = TRANSITIONS[assignment.status]
    if assignment.kind == "internal":
        allowed = allowed | _INTERNAL_EXTRA.get(assignment.status, frozenset())
    return allowed


async def get_assignment(session: AsyncSession, assignment_id: UUID) -> Assignment:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", assignment_id)
    return assignment


async def _check_organisation(session: AsyncSession, org_id: UUID | None) -> None:
    if org_id is not None and await session.get(Organisation, org_id) is None:
        raise NotFoundError("Organisatie", org_id)


def _check_context_refs(context_refs: Iterable[str]) -> list[str]:
    refs = list(context_refs)
    for ref in refs:
        if not isinstance(ref, str) or not ref.startswith(("https://", "http://")):
            raise DomainValidationError(
                "Een verwijzing naar een node is een volledige URI."
            )
    return refs


async def upsert_organisation(
    session: AsyncSession,
    *,
    name: str,
    tooi_uri: str | None = None,
    unit_key: str | None = None,
    instance_uri: str | None = None,
) -> Organisation:
    """Find a counterparty by TOOI URI and unit key, or create it."""
    if tooi_uri is not None:
        stmt = select(Organisation).where(Organisation.tooi_uri == tooi_uri)
        stmt = stmt.where(
            Organisation.unit_key.is_(None)
            if unit_key is None
            else Organisation.unit_key == unit_key
        )
        found = (await session.execute(stmt)).scalar_one_or_none()
        if found is not None:
            if instance_uri and found.instance_uri is None:
                found.instance_uri = instance_uri
                await session.flush()
            return found
    organisation = Organisation(
        name=name, tooi_uri=tooi_uri, unit_key=unit_key, instance_uri=instance_uri
    )
    session.add(organisation)
    await session.flush()
    return organisation


async def create_assignment(
    session: AsyncSession,
    *,
    name: str,
    actor: Person | None,
    kind: str = "external",
    traffic_form: str | None = None,
    client_organisation_id: UUID | None = None,
    contractor_organisation_id: UUID | None = None,
    parent_assignment_uri: str | None = None,
    context_refs: Iterable[str] = (),
    client_contact: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    notes: str | None = None,
    owner_id: UUID | None = None,
    uri: str | None = None,
) -> Assignment:
    """Create an assignment in status draft.

    The actor becomes the owner unless ``owner_id`` names someone else. The
    URI is minted here unless the assignment came from another instance.

    ``traffic_form`` is accepted and ignored, for callers that still pass
    it: how a quote reaches the client is chosen when a quote is offered,
    not when the assignment is created.
    """
    if kind not in ASSIGNMENT_KINDS:
        raise DomainValidationError(f"Onbekend soort opdracht: {kind}")
    if start_date and end_date and end_date < start_date:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    await _check_organisation(session, client_organisation_id)
    await _check_organisation(session, contractor_organisation_id)

    assignment_id = uuid.uuid4()
    assignment = Assignment(
        id=assignment_id,
        uri=uri or mint_uri("opdracht", assignment_id),
        name=name,
        kind=kind,
        status="draft",
        client_organisation_id=client_organisation_id,
        contractor_organisation_id=contractor_organisation_id,
        parent_assignment_uri=parent_assignment_uri,
        context_refs=_check_context_refs(context_refs),
        client_contact=client_contact,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
    )
    session.add(assignment)
    await session.flush()
    owner = owner_id or (actor.id if actor is not None else None)
    if owner is not None:
        session.add(
            AssignmentRole(
                assignment_id=assignment.id, person_id=owner, role=ROLE_OWNER
            )
        )
        await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="assignment",
        entity_id=assignment.id,
        new_value=audit_fields(assignment, _ASSIGNMENT_FIELDS),
    )
    return assignment


async def update_assignment(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
    **changes: Any,
) -> Assignment:
    """Change descriptive fields. Status changes go through ``transition``.

    A change of the period moves the budget lines that follow the assignment,
    and the inzet that follows those lines. It is refused as a whole when
    that would change anything inside a closed month. The audit row of the
    assignment lists what moved.
    """
    # No longer a property of an assignment; ignored when still sent.
    changes.pop("traffic_form", None)
    unknown = set(changes) - _EDITABLE_ASSIGNMENT_FIELDS
    if unknown:
        raise DomainValidationError(
            f"Deze velden zijn niet te wijzigen: {', '.join(sorted(unknown))}"
        )
    assignment = await get_assignment(session, assignment_id)
    if "kind" in changes and changes["kind"] not in ASSIGNMENT_KINDS:
        raise DomainValidationError(f"Onbekend soort opdracht: {changes['kind']}")
    if "context_refs" in changes:
        changes["context_refs"] = _check_context_refs(changes["context_refs"])
    for key in ("client_organisation_id", "contractor_organisation_id"):
        if key in changes:
            await _check_organisation(session, changes[key])
    start = changes.get("start_date", assignment.start_date)
    end = changes.get("end_date", assignment.end_date)
    if start and end and end < start:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    moved: dict[str, Any] = {}
    new_period = (start, end) if start and end else (None, None)
    if new_period != periods.assignment_period(assignment):
        moved = await periods.follow_assignment(
            session, assignment, new_period, allow_closed_year=allow_closed_year
        )
    old = {k: audit_value(getattr(assignment, k)) for k in changes}
    for key, value in changes.items():
        setattr(assignment, key, value)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="assignment",
        entity_id=assignment.id,
        old_value=old,
        new_value={**{k: audit_value(v) for k, v in changes.items()}, **moved},
    )
    if moved:
        # Lines that just got a period can now hold the reservation of their
        # intended person. Imported here: that module builds on this one.
        from grip.services import budget_intent

        await budget_intent.reserve_waiting(
            session, assignment.id, actor=actor, allow_closed_year=allow_closed_year
        )
    return assignment


# Statuses in which an external assignment involves another party, so that
# party has to be known by then. Creating an assignment needs only a name.
_NEEDS_COUNTERPARTY = frozenset({"requested", "quoted", VERBALLY_AGREED, "accepted"})
# Statuses from which the budget has to be priceable: every personnel line
# has a period by then.
_NEEDS_PERIOD = frozenset({"quoted", VERBALLY_AGREED, "accepted", "in_progress"})


def _check_ready_for(
    assignment: Assignment, target: str, reason: str | None, *, enforce: bool = True
) -> None:
    """What an assignment must have before it can move to ``target``.

    Validation lives here, at the step that needs the data, so an assignment
    can be created with next to nothing and filled in along the way.
    """
    if target == VERBALLY_AGREED and not (reason and reason.strip()):
        raise DomainValidationError(
            "Noteer bij een mondeling akkoord wie akkoord gaf en wanneer."
        )
    if not enforce:
        return
    if (
        target in _NEEDS_COUNTERPARTY
        and assignment.kind == "external"
        and assignment.client_organisation_id is None
        and assignment.contractor_organisation_id is None
    ):
        raise DomainValidationError(
            "Kies eerst de opdrachtgever. Een externe opdracht kan pas verder "
            "als bekend is voor wie ze is."
        )
    if target == "in_progress" and assignment.start_date is None:
        raise DomainValidationError(
            "Vul eerst de begindatum in. Een opdracht in uitvoering heeft een "
            "periode nodig."
        )


async def transition(
    session: AsyncSession,
    assignment_id: UUID,
    target: str,
    *,
    actor: Person | None,
    reason: str | None = None,
    origin: str = "local",
    enforce_readiness: bool = True,
) -> Assignment:
    """Move an assignment to another status, if the lifecycle allows it.

    A step also checks that the assignment has what the new status needs (a
    client, a start date). ``enforce_readiness=False`` skips that for records
    taken over from an older administration, which never had those fields;
    the note of a verbal agreement is required either way.
    """
    if target not in ASSIGNMENT_STATUSES:
        raise DomainValidationError(f"Onbekende status: {target}")
    assignment = await get_assignment(session, assignment_id)
    if target not in allowed_transitions(assignment):
        raise IllegalTransitionError(assignment.status, target)
    _check_ready_for(assignment, target, reason, enforce=enforce_readiness)
    if (
        enforce_readiness
        and target in _NEEDS_PERIOD
        and await periods.lines_without_period(session, assignment.id)
    ):
        raise DomainValidationError(
            "Vul eerst de periode van de opdracht in: er zijn begrotingsregels "
            "die de opdracht volgen en nog geen periode hebben."
        )
    old = assignment.status
    assignment.status = target
    if target == VERBALLY_AGREED:
        assert reason is not None
        assignment.verbal_agreement_note = reason.strip()
        assignment.verbal_agreement_at = datetime.now(UTC)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="assignment",
        entity_id=assignment.id,
        old_value={"status": old},
        new_value={"status": target, **({"reason": reason} if reason else {})},
    )
    # Another instance never learns of a verbal agreement: the event carries
    # the status as the counterparty sees it, and a change it cannot see is
    # no event.
    seen_old = counterparty_status(old)
    seen_new = counterparty_status(target)
    if seen_old != seen_new:
        await events.emit(
            session,
            events.ASSIGNMENT_STATUS_CHANGED,
            {
                "assignment_id": str(assignment.id),
                "assignment_uri": assignment.uri,
                "old_status": seen_old,
                "new_status": seen_new,
                "reason": reason if target != VERBALLY_AGREED else None,
                "origin": origin,
            },
        )
    return assignment


async def create_assignment_request(
    session: AsyncSession,
    *,
    name: str,
    contractor_organisation_id: UUID,
    actor: Person | None,
    client_organisation_id: UUID | None = None,
    description: str | None = None,
    context_refs: Iterable[str] = (),
    parent_assignment_uri: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    traffic_form: str | None = None,
) -> tuple[Assignment, UUID]:
    """Client side: ask a contractor for a quote.

    Creates the assignment in status requested and emits
    ``assignment_request.created``. Returns the assignment and the id of the
    request, which is also the id of the message.
    """
    assignment = await create_assignment(
        session,
        name=name,
        actor=actor,
        kind="external",
        client_organisation_id=client_organisation_id,
        contractor_organisation_id=contractor_organisation_id,
        parent_assignment_uri=parent_assignment_uri,
        context_refs=context_refs,
        start_date=start_date,
        end_date=end_date,
        notes=description,
    )
    # Asking a contractor for a quote is an exchange: from here on the
    # assignment is shared with the contractor's instance, if it has one.
    contractor = await session.get(Organisation, contractor_organisation_id)
    if contractor is not None and contractor.instance_uri:
        share_with_instance(assignment, contractor.instance_uri)
        await session.flush()
    await transition(session, assignment.id, "requested", actor=actor)
    request_id = uuid.uuid4()
    await events.emit(
        session,
        events.ASSIGNMENT_REQUEST_CREATED,
        {
            "request_id": str(request_id),
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "name": assignment.name,
            "description": description,
            "client_organisation_id": audit_value(client_organisation_id),
            "contractor_organisation_id": str(contractor_organisation_id),
            "context_refs": list(assignment.context_refs),
            "parent_assignment_uri": parent_assignment_uri,
            "start_date": audit_value(start_date),
            "end_date": audit_value(end_date),
            "origin": "local",
        },
    )
    return assignment, request_id


async def receive_assignment_request(
    session: AsyncSession,
    *,
    uri: str,
    name: str,
    client_organisation_id: UUID,
    contractor_organisation_id: UUID | None = None,
    description: str | None = None,
    context_refs: Iterable[str] = (),
    parent_assignment_uri: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Assignment:
    """Contractor side: record a request that came in from a client.

    Idempotent on the assignment URI. Emits no request event: the request
    did not start here.
    """
    result = await session.execute(select(Assignment).where(Assignment.uri == uri))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    assignment = await create_assignment(
        session,
        name=name,
        actor=None,
        kind="external",
        client_organisation_id=client_organisation_id,
        contractor_organisation_id=contractor_organisation_id,
        parent_assignment_uri=parent_assignment_uri,
        context_refs=context_refs,
        start_date=start_date,
        end_date=end_date,
        notes=description,
        uri=uri,
    )
    # A request that came in from a client's instance is shared with that
    # instance from the start.
    client = await session.get(Organisation, client_organisation_id)
    if client is not None and client.instance_uri:
        share_with_instance(assignment, client.instance_uri)
        await session.flush()
    return await transition(
        session, assignment.id, "requested", actor=None, origin="remote"
    )


async def issue_final_report(
    session: AsyncSession,
    assignment_id: UUID,
    report: dict[str, Any],
    *,
    actor: Person | None,
) -> Assignment:
    """Issue the final report of a completed assignment.

    The report is the caller's JSON (delivered, not delivered, costs). It is
    kept in the audit log and handed to the event handlers.
    """
    assignment = await get_assignment(session, assignment_id)
    if assignment.status not in ("completed", "accounted"):
        raise DomainValidationError(
            "Een eindrapport kan pas worden uitgegeven als de opdracht is afgerond."
        )
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="final_report",
        entity_id=assignment.id,
        new_value=audit_value(report),
    )
    await events.emit(
        session,
        events.FINAL_REPORT_ISSUED,
        {
            "assignment_id": str(assignment.id),
            "assignment_uri": assignment.uri,
            "report": audit_value(report),
            "origin": "local",
        },
    )
    return assignment


# -- roles --------------------------------------------------------------------

_OWNER_REQUIRED = (
    "Een opdracht heeft altijd een eigenaar. Wijs eerst een andere eigenaar aan."
)


def _role_change_basis(
    actor: Person | None, person_id: UUID, as_beheerder: bool
) -> dict[str, Any]:
    """What the audit row says about a role change made on the function alone."""
    if not as_beheerder:
        return {}
    basis: dict[str, Any] = {"basis": "function:beheerder"}
    if actor is not None and actor.id == person_id:
        basis["self_assignment"] = True
    return basis


async def set_assignment_role(
    session: AsyncSession,
    assignment_id: UUID,
    person_id: UUID,
    role: str,
    *,
    actor: Person | None,
    as_beheerder: bool = False,
) -> AssignmentRole:
    """Make a person owner or manager of an assignment.

    There is one owner: naming a new owner turns the previous one into a
    manager. The owner cannot be made manager directly, because that would
    leave the assignment without an owner.

    ``as_beheerder`` says the actor has no role on the assignment and acts on
    the function alone; the audit row records that, and whether the actor
    named themselves.
    """
    if role not in (ROLE_OWNER, ROLE_MANAGER):
        raise DomainValidationError(f"Onbekende rol op een opdracht: {role}")
    await get_assignment(session, assignment_id)
    if await session.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    result = await session.execute(
        select(AssignmentRole).where(AssignmentRole.assignment_id == assignment_id)
    )
    roles = list(result.scalars())
    current = next((r for r in roles if r.person_id == person_id), None)
    old = {"role": current.role} if current is not None else None
    if current is not None and current.role == ROLE_OWNER and role == ROLE_MANAGER:
        raise DomainValidationError(_OWNER_REQUIRED)
    if role == ROLE_OWNER:
        for other in roles:
            if other.role == ROLE_OWNER and other.person_id != person_id:
                other.role = ROLE_MANAGER
        await session.flush()
    if current is None:
        current = AssignmentRole(
            assignment_id=assignment_id, person_id=person_id, role=role
        )
        session.add(current)
    else:
        current.role = role
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE if old else CREATE,
        entity="assignment_role",
        entity_id=current.id,
        old_value=old,
        new_value={
            "assignment_id": str(assignment_id),
            "person_id": str(person_id),
            "role": role,
            **_role_change_basis(actor, person_id, as_beheerder),
        },
    )
    return current


async def remove_assignment_role(
    session: AsyncSession,
    assignment_id: UUID,
    person_id: UUID,
    *,
    actor: Person | None,
    as_beheerder: bool = False,
) -> None:
    """Take a manager off an assignment. The owner can only be replaced."""
    result = await session.execute(
        select(AssignmentRole).where(
            AssignmentRole.assignment_id == assignment_id,
            AssignmentRole.person_id == person_id,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Rol op de opdracht", person_id)
    if role.role == ROLE_OWNER:
        raise DomainValidationError(_OWNER_REQUIRED)
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="assignment_role",
        entity_id=role.id,
        old_value={
            "assignment_id": str(assignment_id),
            "person_id": str(person_id),
            "role": role.role,
        },
        new_value=_role_change_basis(actor, person_id, as_beheerder) or None,
    )
    await session.delete(role)
    await session.flush()


# -- budget lines -------------------------------------------------------------


def _validate_line(values: dict[str, Any]) -> None:
    kind = values.get("kind")
    if kind not in BUDGET_LINE_KINDS:
        raise DomainValidationError(f"Onbekend soort begrotingsregel: {kind}")
    if kind == "personnel":
        # A line that follows the assignment has its dates once the
        # assignment has a period (grip.services.periods).
        follows = values.get("period_source") == periods.FOLLOWS_ASSIGNMENT
        needed = ("fte", "rate_category") + (
            () if follows else ("start_date", "end_date")
        )
        if [f for f in needed if values.get(f) is None]:
            raise DomainValidationError(
                "Een personeelsregel heeft FTE en categorie nodig, en een begin- en "
                "einddatum als ze een eigen periode heeft."
            )
        if values.get("amount_cents") is not None or values.get("year") is not None:
            raise DomainValidationError(
                "Een personeelsregel heeft geen vast bedrag of jaar."
            )
        if values["rate_category"] not in RATE_CATEGORIES:
            raise DomainValidationError(
                f"Onbekende tariefcategorie: {values['rate_category']}"
            )
        if Decimal(values["fte"]) <= 0:
            raise DomainValidationError("De omvang in FTE is groter dan nul.")
        if (
            values.get("start_date") is not None
            and values.get("end_date") is not None
            and values["end_date"] < values["start_date"]
        ):
            raise DomainValidationError("De einddatum ligt voor de begindatum.")
    else:
        if values.get("amount_cents") is None or values.get("year") is None:
            raise DomainValidationError(
                "Een vaste regel heeft een bedrag en een jaar nodig."
            )
        if values["amount_cents"] < 0:
            raise DomainValidationError("Een bedrag kan niet negatief zijn.")
        if values.get("fte") is not None or values.get("rate_category") is not None:
            raise DomainValidationError("Een vaste regel heeft geen FTE of categorie.")


def _ensure_year_in_period(assignment: Assignment, values: dict[str, Any]) -> None:
    """A fixed amount belongs to a year the assignment runs in.

    Outside the period it would stand in the budget, the quote and the letter
    as money for a year in which nothing is delivered.
    """
    if values.get("kind") != "fixed" or values.get("year") is None:
        return
    if assignment.start_date is None or assignment.end_date is None:
        return
    first, last = assignment.start_date.year, assignment.end_date.year
    if first <= values["year"] <= last:
        return
    running = str(first) if first == last else f"{first} t/m {last}"
    raise DomainValidationError(
        f"Het jaar {values['year']} valt buiten de looptijd van de opdracht "
        f"({running}). Kies een jaar binnen de looptijd."
    )


def _line_years(values: dict[str, Any]) -> set[int]:
    if values.get("kind") == "fixed":
        return {values["year"]} if values.get("year") is not None else set()
    return years_between(values.get("start_date"), values.get("end_date"))


async def add_budget_line(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    description: str,
    kind: str,
    actor: Person | None,
    position: int | None = None,
    role: str | None = None,
    fte: Decimal | None = None,
    rate_category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    amount_cents: int | None = None,
    year: int | None = None,
    period_source: str | None = None,
    allow_closed_year: bool = False,
) -> BudgetLine:
    """Add a budget line.

    A personnel line follows the period of the assignment unless it is given
    dates of its own (``period_source`` "own", or dates that differ from the
    assignment's). While the assignment has no period a following line has
    no dates and is not priced.
    """
    assignment = await get_assignment(session, assignment_id)
    if kind == "personnel":
        period_source, start_date, end_date = periods.line_period(
            assignment, period_source, start_date, end_date
        )
    else:
        period_source = periods.OWN
    values: dict[str, Any] = {
        "kind": kind,
        "fte": fte,
        "rate_category": rate_category,
        "period_source": period_source,
        "start_date": start_date,
        "end_date": end_date,
        "amount_cents": amount_cents,
        "year": year,
    }
    _validate_line(values)
    _ensure_year_in_period(assignment, values)
    closed = await ensure_years_open(
        session, _line_years(values), allow_closed_year=allow_closed_year
    )
    if position is None:
        result = await session.execute(
            select(BudgetLine.position).where(BudgetLine.assignment_id == assignment_id)
        )
        position = max([p for p in result.scalars()], default=0) + 1
    line = BudgetLine(
        assignment_id=assignment_id,
        description=description,
        position=position,
        role=role,
        **values,
    )
    session.add(line)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="budget_line",
        entity_id=line.id,
        new_value={
            **audit_fields(line, _LINE_FIELDS),
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return line


async def get_budget_line(session: AsyncSession, line_id: UUID) -> BudgetLine:
    line = await session.get(BudgetLine, line_id)
    if line is None:
        raise NotFoundError("Begrotingsregel", line_id)
    return line


async def update_budget_line(
    session: AsyncSession,
    line_id: UUID,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
    **changes: Any,
) -> BudgetLine:
    allowed = set(_LINE_FIELDS) - {"assignment_id", "kind"}
    unknown = set(changes) - allowed
    if unknown:
        raise DomainValidationError(
            f"Deze velden zijn niet te wijzigen: {', '.join(sorted(unknown))}"
        )
    line = await get_budget_line(session, line_id)
    before = {f: getattr(line, f) for f in _LINE_FIELDS}
    if line.kind == "personnel" and {"period_source", "start_date", "end_date"} & set(
        changes
    ):
        # Dates sent without a source make the period the line's own; a
        # source sent without dates keeps the dates the line has.
        source = changes.get("period_source")
        dated = "start_date" in changes or "end_date" in changes
        start = changes.get("start_date", line.start_date)
        end = changes.get("end_date", line.end_date)
        if source is None and not dated:
            source = line.period_source
        assignment = await get_assignment(session, line.assignment_id)
        source, start, end = periods.line_period(assignment, source, start, end)
        changes = {
            **changes,
            "period_source": source,
            "start_date": start,
            "end_date": end,
        }
    after = {**before, **changes}
    _validate_line(after)
    if after.get("year") != before.get("year"):
        _ensure_year_in_period(await get_assignment(session, line.assignment_id), after)
    closed = await ensure_years_open(
        session,
        _line_years(before) | _line_years(after),
        allow_closed_year=allow_closed_year,
    )
    if (after["start_date"], after["end_date"]) != (
        before["start_date"],
        before["end_date"],
    ):
        # Inzet that follows the line moves with it, or the change is refused.
        await periods.follow_line(
            session,
            line,
            (after["start_date"], after["end_date"]),
            allow_closed_year=allow_closed_year,
        )
    old = {k: audit_value(before[k]) for k in changes}
    for key, value in changes.items():
        setattr(line, key, value)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="budget_line",
        entity_id=line.id,
        old_value=old,
        new_value={
            **{k: audit_value(v) for k, v in changes.items()},
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return line


async def delete_budget_line(
    session: AsyncSession,
    line_id: UUID,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> None:
    line = await get_budget_line(session, line_id)
    result = await session.execute(
        select(Allocation.id).where(Allocation.budget_line_id == line_id).limit(1)
    )
    if result.first() is not None:
        raise DomainValidationError(
            "Op deze begrotingsregel staat nog inzet. Verwijder eerst de inzet."
        )
    values = {f: getattr(line, f) for f in _LINE_FIELDS}
    closed = await ensure_years_open(
        session, _line_years(values), allow_closed_year=allow_closed_year
    )
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="budget_line",
        entity_id=line.id,
        old_value=audit_value(values),
        new_value={"closed_year_override": closed} if closed else None,
    )
    await session.delete(line)
    await session.flush()


# -- allocations --------------------------------------------------------------


def _validate_allocation(start_date: date, end_date: date, fte_pct: Decimal) -> None:
    if end_date < start_date:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    if not Decimal(0) < Decimal(fte_pct) <= Decimal(100):
        raise DomainValidationError(
            "Het percentage ligt boven 0 en is hoogstens 100 procent."
        )


async def add_allocation(
    session: AsyncSession,
    budget_line_id: UUID,
    person_id: UUID,
    *,
    fte_pct: Decimal,
    actor: Person | None,
    start_date: date | None = None,
    end_date: date | None = None,
    period_source: str | None = None,
    allow_closed_year: bool = False,
) -> Allocation:
    """Put a person on a personnel budget line.

    The inzet follows the period of the line unless it is given dates of its
    own (``period_source`` "own", or dates that differ from the line's).
    """
    line = await get_budget_line(session, budget_line_id)
    if line.kind != "personnel":
        raise DomainValidationError("Inzet kan alleen op een personeelsregel.")
    if await session.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    period_source, start_date, end_date = periods.allocation_period(
        line, period_source, start_date, end_date
    )
    _validate_allocation(start_date, end_date, fte_pct)
    closed = await ensure_years_open(
        session,
        years_between(start_date, end_date),
        allow_closed_year=allow_closed_year,
    )
    await ensure_closed_months_unchanged(
        session,
        line.assignment_id,
        old_period=None,
        new_period=(start_date, end_date),
    )
    allocation = Allocation(
        person_id=person_id,
        budget_line_id=budget_line_id,
        period_source=period_source,
        start_date=start_date,
        end_date=end_date,
        fte_pct=fte_pct,
    )
    session.add(allocation)
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=CREATE,
        entity="allocation",
        entity_id=allocation.id,
        new_value={
            **audit_fields(allocation, _ALLOCATION_FIELDS),
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return allocation


async def get_allocation(session: AsyncSession, allocation_id: UUID) -> Allocation:
    allocation = await session.get(Allocation, allocation_id)
    if allocation is None:
        raise NotFoundError("Inzet", allocation_id)
    return allocation


async def update_allocation(
    session: AsyncSession,
    allocation_id: UUID,
    *,
    actor: Person | None,
    start_date: date | None = None,
    end_date: date | None = None,
    fte_pct: Decimal | None = None,
    period_source: str | None = None,
    allow_closed_year: bool = False,
) -> Allocation:
    """Change inzet.

    Dates sent without a source give the inzet a period of its own (unless
    they equal the line's); ``period_source`` "line" makes it follow the
    line again.
    """
    allocation = await get_allocation(session, allocation_id)
    line = await get_budget_line(session, allocation.budget_line_id)
    new_source = allocation.period_source
    new_start = start_date or allocation.start_date
    new_end = end_date or allocation.end_date
    if period_source is not None or start_date is not None or end_date is not None:
        new_source, new_start, new_end = periods.allocation_period(
            line,
            period_source,
            None if period_source == periods.FOLLOWS_LINE else new_start,
            None if period_source == periods.FOLLOWS_LINE else new_end,
        )
    new_pct = fte_pct if fte_pct is not None else allocation.fte_pct
    _validate_allocation(new_start, new_end, new_pct)
    closed = await ensure_years_open(
        session,
        years_between(allocation.start_date, allocation.end_date)
        | years_between(new_start, new_end),
        allow_closed_year=allow_closed_year,
    )
    await ensure_closed_months_unchanged(
        session,
        line.assignment_id,
        old_period=(allocation.start_date, allocation.end_date),
        new_period=(new_start, new_end),
    )
    old = audit_fields(allocation, _ALLOCATION_FIELDS)
    allocation.period_source = new_source
    allocation.start_date = new_start
    allocation.end_date = new_end
    allocation.fte_pct = new_pct
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="allocation",
        entity_id=allocation.id,
        old_value=old,
        new_value={
            **audit_fields(allocation, _ALLOCATION_FIELDS),
            **({"closed_year_override": closed} if closed else {}),
        },
    )
    return allocation


async def delete_allocation(
    session: AsyncSession,
    allocation_id: UUID,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> None:
    allocation = await get_allocation(session, allocation_id)
    line = await get_budget_line(session, allocation.budget_line_id)
    closed = await ensure_years_open(
        session,
        years_between(allocation.start_date, allocation.end_date),
        allow_closed_year=allow_closed_year,
    )
    await ensure_closed_months_unchanged(
        session,
        line.assignment_id,
        old_period=(allocation.start_date, allocation.end_date),
        new_period=None,
    )
    in_trail = await session.execute(
        select(MonthCloseLine.id)
        .where(MonthCloseLine.allocation_id == allocation_id)
        .limit(1)
    )
    if in_trail.first() is not None:
        # Also a reopened close keeps its lines, as the trail of what was
        # established. Ending the allocation keeps that trail intact.
        raise DomainValidationError(
            "Deze inzet komt voor in een maandafsluiting en kan niet worden "
            "verwijderd. Pas de einddatum aan."
        )
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity="allocation",
        entity_id=allocation.id,
        old_value=audit_fields(allocation, _ALLOCATION_FIELDS),
        new_value={"closed_year_override": closed} if closed else None,
    )
    await session.delete(allocation)
    await session.flush()
