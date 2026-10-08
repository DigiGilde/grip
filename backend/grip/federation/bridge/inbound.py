"""What a received message does in the domain.

Every handler gets the message in code names, after the route validated it
against the contract (and, for an acceptance from another instance, verified
its signature). A handler asks the access model whether this peer may do
this, calls the service layer with ``origin="remote"`` so the change is not
sent back out, and returns a small result that is kept with the message.

Refusals are problems: 404 when the peer has no relation with the thing (the
same answer as when it does not exist), 409 when the message contradicts
what is recorded here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, Resource
from grip.core.audit import CREATE, record_audit
from grip.federation import terms
from grip.federation.bridge.access import peer_access
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.models import Peer
from grip.federation.problems import FederationProblem
from grip.federation.registry import InboundMessage
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository
from grip.repositories.vacancy import VacancyRepository
from grip.services import assignments, quotes
from grip.services.canonical import canonical_of_received
from grip.services.errors import (
    DomainError,
    NotFoundError,
    QuoteAlreadyDecidedError,
    QuoteHashMismatchError,
)


def _not_found() -> FederationProblem:
    return FederationProblem(
        404, "Niet gevonden", "Niet gevonden, of er is geen relatie mee."
    )


def _conflict(detail: str) -> FederationProblem:
    return FederationProblem(409, "Past niet bij wat hier is vastgelegd", detail)


def _refuse(error: DomainError) -> FederationProblem:
    """A domain error as an answer to the sender, without internals."""
    if isinstance(error, NotFoundError):
        return _not_found()
    if isinstance(error, (QuoteAlreadyDecidedError, QuoteHashMismatchError)):
        return _conflict(str(error))
    return FederationProblem(400, "Bericht geweigerd", str(error))


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


async def receive_assignment_request(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    """A client asks this instance for a quote."""
    body = message.payload
    access = peer_access(db, peer)
    if not (await access.may(Action.REQUEST_ASSIGNMENT, Resource.assignment())).allowed:
        raise FederationProblem(
            403, "Geen toegang", "Deze peer mag hier geen opdracht aanvragen."
        )
    client = await from_reference(db, body["client"])
    contractor = await own_organisation(db)
    period = body.get("desired_period") or {}
    try:
        assignment = await assignments.receive_assignment_request(
            db,
            uri=body["assignment_uri"],
            name=body["name"],
            client_organisation_id=client.id,
            contractor_organisation_id=contractor.id,
            description=body.get("description"),
            context_refs=body.get("context_refs") or [],
            parent_assignment_uri=body.get("parent_assignment_uri"),
            start_date=_date(period.get("start_date")),
            end_date=_date(period.get("end_date")),
        )
    except DomainError as error:
        raise _refuse(error) from error
    return {"assignment_id": str(assignment.id), "request_id": body["id"]}


async def receive_quote(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    """A contractor sends a quote, on request or on its own initiative."""
    body = message.payload
    access = peer_access(db, peer)
    repository = AssignmentRepository(db)
    assignment = await repository.get_by_uri(body["assignment_uri"])
    if assignment is None:
        # A quote on the contractor's own initiative: there is no assignment
        # on this side yet. It starts here, with this instance as client.
        decision = await access.may(Action.ISSUE_QUOTE, Resource.quote(None, None))
        if not decision.allowed:
            raise _not_found()
        contractor = await from_reference(db, body["contractor"])
        client = await own_organisation(db)
        try:
            assignment = await assignments.create_assignment(
                db,
                name=body["snapshot"]["name"],
                actor=None,
                kind="external",
                client_organisation_id=client.id,
                contractor_organisation_id=contractor.id,
                parent_assignment_uri=body.get("parent_assignment_uri"),
                context_refs=body["snapshot"].get("context_refs") or [],
                uri=body["assignment_uri"],
            )
        except DomainError as error:
            raise _refuse(error) from error
        # A quote received from an instance is an exchange with it.
        assignments.share_with_instance(assignment, peer.base_uri)
    else:
        decision = await access.may(
            Action.ISSUE_QUOTE, Resource.quote(None, assignment.id)
        )
        if not decision.allowed:
            raise _not_found()
        assignments.share_with_instance(assignment, peer.base_uri)
    try:
        quote = await quotes.receive_quote(
            db,
            assignment.id,
            quote_id=UUID(body["id"]),
            uri=body["uri"],
            # The content is kept exactly as it came in, so both instances
            # hold the same bytes. The domain refuses a quote whose stated
            # hash is not the hash of those bytes.
            canonical=canonical_of_received(
                message.contract_payload[terms.term("snapshot")]
            ),
            claimed_hash=body["snapshot_hash"],
            issued_at=datetime.fromisoformat(body["issued_at"]),
            request_id=UUID(body["request_id"]) if body.get("request_id") else None,
        )
    except DomainError as error:
        raise _refuse(error) from error
    return {"assignment_id": str(assignment.id), "quote_id": str(quote.id)}


async def _own_quote(db: AsyncSession, peer: Peer, body: dict[str, Any]) -> Quote:
    """The quote a decision is about, if this peer is the client of it."""
    quote = await db.get(Quote, UUID(body["quote_id"]))
    if quote is None:
        raise _not_found()
    decision = await peer_access(db, peer).may(
        Action.ACCEPT_QUOTE, Resource.quote(quote.id, quote.assignment_id)
    )
    if not decision.allowed:
        raise _not_found()
    assignment = await AssignmentRepository(db).get(quote.assignment_id)
    if assignment is None or not assignments.is_shared_with(assignment, peer.base_uri):
        # The quote was never offered to this instance: a decision on it
        # cannot come from there.
        raise _not_found()
    if body["quote_hash"] != quote.snapshot_hash:
        raise _conflict("De hash hoort niet bij de uitgegeven offerte.")
    return quote


async def receive_acceptance(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    """The client accepted a quote in its own instance."""
    body = message.payload
    if body["form"] != "own_instance":
        # The other two forms arise at the contractor: a guest who signs
        # here, or a signed pdf that is recorded here.
        raise FederationProblem(
            400,
            "Bericht geweigerd",
            "Een akkoord van een andere instantie is getekend in die instantie.",
        )
    quote = await _own_quote(db, peer, body)
    signer = body["signer"]
    try:
        acceptance = await quotes.accept_quote(
            db,
            quote.id,
            quote_hash=quote.snapshot_hash,
            signer_name=signer["name"],
            signer_email=signer["email"],
            signer_function=signer.get("function"),
            organisation=body["organisation"],
            form=body["form"],
            signed_at=datetime.fromisoformat(body["signed_at"]),
            jws=body["jws"],
            acceptance_id=UUID(body["id"]),
            origin="remote",
        )
    except DomainError as error:
        raise _refuse(error) from error
    return {"quote_id": str(quote.id), "acceptance_id": str(acceptance.id)}


async def receive_rejection(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    body = message.payload
    quote = await _own_quote(db, peer, body)
    try:
        rejection = await quotes.reject_quote(
            db,
            quote.id,
            quote_hash=quote.snapshot_hash,
            reason=body.get("reason"),
            organisation=body["organisation"],
            rejected_at=datetime.fromisoformat(body["rejected_at"]),
            rejection_id=UUID(body["id"]),
            origin="remote",
        )
    except DomainError as error:
        raise _refuse(error) from error
    return {"quote_id": str(quote.id), "rejection_id": str(rejection.id)}


async def receive_final_report(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    """The contractor delivers the final report of an assignment.

    The domain has no table for a received report. It is kept with the
    message and in the audit log of the assignment.
    """
    body = message.payload
    assignment = await AssignmentRepository(db).get_by_uri(body["assignment_uri"])
    if assignment is None:
        raise _not_found()
    decision = await peer_access(db, peer).may(
        Action.DELIVER_REPORT, Resource.assignment(assignment.id)
    )
    if not decision.allowed or not assignments.is_shared_with(
        assignment, peer.base_uri
    ):
        raise _not_found()
    record_audit(
        db,
        actor=None,
        action=CREATE,
        entity="final_report_received",
        entity_id=assignment.id,
        new_value={"report_id": body["id"], "from_peer": peer.peer_id, "report": body},
    )
    return {"assignment_id": str(assignment.id), "report_id": body["id"]}


async def receive_vacancy(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    """Another instance puts out an open role.

    The domain has no place for the vacancies of others yet. The message
    stays in the inbox, where a screen can list it.
    """
    return {"vacancy_uri": message.payload["uri"], "status": message.payload["status"]}


async def receive_vacancy_offer(
    db: AsyncSession, peer: Peer, message: InboundMessage
) -> dict[str, Any]:
    """Another instance offers a candidate for a vacancy of this instance."""
    body = message.payload
    vacancy = await VacancyRepository(db).get(UUID(body["vacancy_id"]))
    if (
        vacancy is None
        or vacancy.status != "open"
        or "federated" not in (vacancy.channels or [])
    ):
        raise _not_found()
    record_audit(
        db,
        actor=None,
        action=CREATE,
        entity="vacancy_offer_received",
        entity_id=vacancy.id,
        new_value={"offer_id": body["id"], "from_peer": peer.peer_id},
    )
    return {"vacancy_id": str(vacancy.id), "offer_id": body["id"]}


HANDLERS = {
    "sendAssignmentRequest": receive_assignment_request,
    "sendQuote": receive_quote,
    "sendAcceptance": receive_acceptance,
    "sendRejection": receive_rejection,
    "sendFinalReport": receive_final_report,
    "sendVacancy": receive_vacancy,
    "sendVacancyOffer": receive_vacancy_offer,
}
