"""Read models for the client side of an instance.

An instance is also opdrachtgever: it asks a contractor for a quote,
receives quotes and follows the assignment. This module answers the
questions the screens for that side ask. It only reads; requests, decisions
and pulls go through the domain services and the federation bridge.

"This instance is the client" is told from the organisation an assignment
names as client: the one whose instance URI is the base URI of this
instance. A received request is the mirror image: an assignment whose URI
was minted by another instance and that names another organisation as
client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.federation import terms
from grip.federation.bridge.organisations import reference
from grip.federation.models import (
    PEER_ROLE_CHILD,
    PEER_ROLE_CORPUS,
    PEER_ROLE_COUNTERPART,
    PEER_ROLE_PARENT,
    FederationOutbox,
    Peer,
)
from grip.federation.peers import find_peer_for_organisation, normalize_uri
from grip.models.assignment import Assignment
from grip.models.audit_log import AuditLog
from grip.models.organisation import Organisation
from grip.models.quote import Quote, QuoteAcceptance, QuoteRejection

SERVICE_OPDRACHTVERKEER = "grip-opdrachtverkeer"
SERVICE_CORPUS_CONTEXT = "corpus-context"

# A parent or a child instance is also a counterpart: an assignment can run
# between them.
_CONTRACTOR_ROLES = (PEER_ROLE_COUNTERPART, PEER_ROLE_PARENT, PEER_ROLE_CHILD)

# Outbox operations a user wants to see the delivery of, per subject.
_REQUEST_OPERATION = "sendAssignmentRequest"
_DECISION_OPERATIONS = ("sendAcceptance", "sendRejection")


@dataclass(frozen=True)
class Delivery:
    """Whether a message to the other side has arrived."""

    operation: str
    # pending | sent | rejected | dead
    status: str
    queued_at: datetime
    sent_at: datetime | None
    attempts: int
    last_error: str | None


@dataclass(frozen=True)
class QuoteRef:
    id: UUID
    status: str
    issued_at: datetime
    total_cents: int


@dataclass(frozen=True)
class ClientAssignment:
    assignment: Assignment
    contractor_name: str | None
    # The newest quote of the contractor, when one came in.
    latest_quote: QuoteRef | None
    request_delivery: Delivery | None


@dataclass(frozen=True)
class ReceivedRequest:
    assignment: Assignment
    client_name: str | None
    quote_count: int


@dataclass(frozen=True)
class ReceivedQuote:
    quote: Quote
    assignment: Assignment
    contractor_name: str | None
    acceptance: QuoteAcceptance | None
    rejection: QuoteRejection | None
    deliveries: list[Delivery] = field(default_factory=list)


def own_base(settings: Settings | None = None) -> str:
    return normalize_uri((settings or get_settings()).INSTANCE_BASE_URI)


async def own_organisation_ids(
    db: AsyncSession, settings: Settings | None = None
) -> set[UUID]:
    """The organisation rows that stand for this instance. Usually one."""
    wanted = own_base(settings)
    rows = (
        await db.execute(
            select(Organisation.id, Organisation.instance_uri).where(
                Organisation.instance_uri.is_not(None)
            )
        )
    ).all()
    return {row.id for row in rows if normalize_uri(row.instance_uri or "") == wanted}


async def _organisation_names(
    db: AsyncSession, ids: set[UUID | None]
) -> dict[UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = (
        await db.execute(
            select(Organisation.id, Organisation.name).where(
                Organisation.id.in_(wanted)
            )
        )
    ).all()
    return {row.id: row.name for row in rows}


def _delivery(row: FederationOutbox) -> Delivery:
    return Delivery(
        operation=row.operation,
        status=row.status,
        queued_at=row.created_at,
        sent_at=row.sent_at,
        attempts=row.attempts,
        last_error=row.last_error,
    )


async def _request_deliveries(db: AsyncSession, uris: list[str]) -> dict[str, Delivery]:
    """Per assignment URI the newest delivery of its request."""
    if not uris:
        return {}
    key = terms.term("assignment_uri")
    rows = (
        (
            await db.execute(
                select(FederationOutbox)
                .where(
                    FederationOutbox.operation == _REQUEST_OPERATION,
                    FederationOutbox.payload[key].astext.in_(uris),
                )
                .order_by(FederationOutbox.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {row.payload[key]: _delivery(row) for row in rows}


async def quote_deliveries(db: AsyncSession, quote_id: UUID) -> list[Delivery]:
    """The decisions on a quote that were queued for the contractor."""
    key = terms.term("quote_id")
    rows = (
        (
            await db.execute(
                select(FederationOutbox)
                .where(
                    FederationOutbox.operation.in_(_DECISION_OPERATIONS),
                    FederationOutbox.payload[key].astext == str(quote_id),
                )
                .order_by(FederationOutbox.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [_delivery(row) for row in rows]


async def _latest_quotes(
    db: AsyncSession, assignment_ids: list[UUID]
) -> dict[UUID, QuoteRef]:
    if not assignment_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.assignment_id.in_(assignment_ids))
                .order_by(Quote.issued_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        row.assignment_id: QuoteRef(
            id=row.id,
            status=row.status,
            issued_at=row.issued_at,
            total_cents=row.total_cents,
        )
        for row in rows
    }


async def client_assignments(
    db: AsyncSession, settings: Settings | None = None
) -> list[ClientAssignment]:
    """The assignments this instance is the client of, newest first."""
    own_ids = await own_organisation_ids(db, settings)
    if not own_ids:
        return []
    rows = (
        (
            await db.execute(
                select(Assignment)
                .where(Assignment.client_organisation_id.in_(own_ids))
                .order_by(Assignment.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    names = await _organisation_names(
        db, {row.contractor_organisation_id for row in rows}
    )
    quotes = await _latest_quotes(db, [row.id for row in rows])
    deliveries = await _request_deliveries(db, [row.uri for row in rows])
    return [
        ClientAssignment(
            assignment=row,
            contractor_name=names.get(row.contractor_organisation_id)
            if row.contractor_organisation_id
            else None,
            latest_quote=quotes.get(row.id),
            request_delivery=deliveries.get(row.uri),
        )
        for row in rows
    ]


async def client_assignment(
    db: AsyncSession, assignment_id: UUID, settings: Settings | None = None
) -> ClientAssignment | None:
    """One assignment this instance is the client of; None for any other."""
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.client_organisation_id is None:
        return None
    if assignment.client_organisation_id not in await own_organisation_ids(
        db, settings
    ):
        return None
    names = await _organisation_names(db, {assignment.contractor_organisation_id})
    quotes = await _latest_quotes(db, [assignment.id])
    deliveries = await _request_deliveries(db, [assignment.uri])
    return ClientAssignment(
        assignment=assignment,
        contractor_name=names.get(assignment.contractor_organisation_id)
        if assignment.contractor_organisation_id
        else None,
        latest_quote=quotes.get(assignment.id),
        request_delivery=deliveries.get(assignment.uri),
    )


async def quotes_of(db: AsyncSession, assignment_id: UUID) -> list[QuoteRef]:
    rows = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.assignment_id == assignment_id)
                .order_by(Quote.issued_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        QuoteRef(
            id=row.id,
            status=row.status,
            issued_at=row.issued_at,
            total_cents=row.total_cents,
        )
        for row in rows
    ]


async def received_requests(
    db: AsyncSession, settings: Settings | None = None
) -> list[ReceivedRequest]:
    """Requests that clients sent to this instance, newest first.

    A request stays in this list after it became an assignment in progress:
    the list is where the contractor sees what came in and what became of it.
    """
    base = own_base(settings)
    own_ids = await own_organisation_ids(db, settings)
    query = select(Assignment).where(
        Assignment.traffic_form == "federated",
        Assignment.client_organisation_id.is_not(None),
        ~Assignment.uri.startswith(f"{base}/", autoescape=True),
    )
    if own_ids:
        query = query.where(
            or_(
                Assignment.contractor_organisation_id.is_(None),
                Assignment.contractor_organisation_id.in_(own_ids),
            ),
            Assignment.client_organisation_id.not_in(own_ids),
        )
    rows = (
        (await db.execute(query.order_by(Assignment.created_at.desc()))).scalars().all()
    )
    names = await _organisation_names(db, {row.client_organisation_id for row in rows})
    counts: dict[UUID, int] = {}
    if rows:
        for (assignment_id,) in (
            await db.execute(
                select(Quote.assignment_id).where(
                    Quote.assignment_id.in_([row.id for row in rows])
                )
            )
        ).all():
            counts[assignment_id] = counts.get(assignment_id, 0) + 1
    return [
        ReceivedRequest(
            assignment=row,
            client_name=names.get(row.client_organisation_id)
            if row.client_organisation_id
            else None,
            quote_count=counts.get(row.id, 0),
        )
        for row in rows
    ]


async def _decisions(
    db: AsyncSession, quote_ids: list[UUID]
) -> tuple[dict[UUID, QuoteAcceptance], dict[UUID, QuoteRejection]]:
    if not quote_ids:
        return {}, {}
    acceptances = (
        (
            await db.execute(
                select(QuoteAcceptance).where(QuoteAcceptance.quote_id.in_(quote_ids))
            )
        )
        .scalars()
        .all()
    )
    rejections = (
        (
            await db.execute(
                select(QuoteRejection).where(QuoteRejection.quote_id.in_(quote_ids))
            )
        )
        .scalars()
        .all()
    )
    return (
        {row.quote_id: row for row in acceptances},
        {row.quote_id: row for row in rejections},
    )


async def received_quotes(
    db: AsyncSession, settings: Settings | None = None
) -> list[ReceivedQuote]:
    """Quotes of contractors on assignments this instance is the client of."""
    own_ids = await own_organisation_ids(db, settings)
    if not own_ids:
        return []
    rows = (
        await db.execute(
            select(Quote, Assignment)
            .join(Assignment, Assignment.id == Quote.assignment_id)
            .where(Assignment.client_organisation_id.in_(own_ids))
            .order_by(Quote.issued_at.desc())
        )
    ).all()
    names = await _organisation_names(
        db, {assignment.contractor_organisation_id for _, assignment in rows}
    )
    acceptances, rejections = await _decisions(db, [quote.id for quote, _ in rows])
    return [
        ReceivedQuote(
            quote=quote,
            assignment=assignment,
            contractor_name=names.get(assignment.contractor_organisation_id)
            if assignment.contractor_organisation_id
            else None,
            acceptance=acceptances.get(quote.id),
            rejection=rejections.get(quote.id),
        )
        for quote, assignment in rows
    ]


async def received_quote(
    db: AsyncSession, quote_id: UUID, settings: Settings | None = None
) -> ReceivedQuote | None:
    """A received quote with its decision and delivery; None for any other."""
    quote = await db.get(Quote, quote_id)
    if quote is None:
        return None
    found = await client_assignment(db, quote.assignment_id, settings)
    if found is None:
        return None
    acceptances, rejections = await _decisions(db, [quote.id])
    return ReceivedQuote(
        quote=quote,
        assignment=found.assignment,
        contractor_name=found.contractor_name,
        acceptance=acceptances.get(quote.id),
        rejection=rejections.get(quote.id),
        deliveries=await quote_deliveries(db, quote.id),
    )


async def contractor_peer(db: AsyncSession, assignment: Assignment) -> Peer | None:
    """The grip instance of the contractor of an assignment, if it runs one."""
    if assignment.contractor_organisation_id is None:
        return None
    organisation = await db.get(Organisation, assignment.contractor_organisation_id)
    ref = reference(organisation)
    if ref is None:
        # Without a TOOI URI the instance URI can still name the peer.
        if organisation is None or not organisation.instance_uri:
            return None
        ref = {"instance_uri": organisation.instance_uri}
    return await find_peer_for_organisation(db, ref)


async def contractor_peers(db: AsyncSession) -> list[Peer]:
    """The instances a quote can be asked from."""
    rows = (
        (
            await db.execute(
                select(Peer)
                .where(Peer.is_active.is_(True), Peer.role.in_(_CONTRACTOR_ROLES))
                .order_by(Peer.name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def corpus_peers(db: AsyncSession) -> list[Peer]:
    rows = (
        (
            await db.execute(
                select(Peer)
                .where(Peer.is_active.is_(True), Peer.role == PEER_ROLE_CORPUS)
                .order_by(Peer.name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def has_grant(peer: Peer, service: str) -> bool:
    return bool((peer.grant_hashes or {}).get(service))


def remote_assignment_id(assignment: Assignment) -> str:
    """The id of an assignment as the contract's paths name it.

    The client mints the assignment URI; its last segment is the id both
    sides use in the path of a pull.
    """
    return assignment.uri.rstrip("/").rsplit("/", 1)[-1]


async def final_report(db: AsyncSession, assignment_id: UUID) -> dict[str, Any] | None:
    """The final report the contractor delivered, in code names, if any.

    The domain keeps a received report in the audit log of the assignment.
    """
    row = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity == "final_report_received",
                AuditLog.entity_id == str(assignment_id),
            )
            .order_by(AuditLog.occurred_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not row.new_value:
        return None
    report = row.new_value.get("report")
    if not isinstance(report, dict):
        return None
    return {**report, "received_at": row.occurred_at}


async def acceptance_date(db: AsyncSession, assignment_id: UUID) -> date | None:
    """The day the quote of an assignment was accepted, for a peildatum."""
    signed_at = (
        await db.execute(
            select(QuoteAcceptance.signed_at)
            .join(Quote, Quote.id == QuoteAcceptance.quote_id)
            .where(Quote.assignment_id == assignment_id)
            .order_by(QuoteAcceptance.signed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return signed_at.date() if signed_at is not None else None
