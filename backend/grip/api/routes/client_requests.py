"""The client side: ask a contractor for a quote and follow what was asked.

An instance is also opdrachtgever (ADR 0016). A person with the function
aanvrager, or the beheerder, asks a contractor this instance has a contract
with for a quote, in the context of nodes. The request is an assignment in
this instance with this instance as client; the federation bridge sends it.

The mirror image is here too: the requests other instances sent to this
one, for whoever picks them up as contractor.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import Access, DbSession, RequestAccess
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.models import Peer
from grip.federation.peers import normalize_uri
from grip.schema.client_side import (
    AssignmentRequestIn,
    ClientAssignmentDetailOut,
    ClientAssignmentListOut,
    ClientAssignmentOut,
    ClientOptionsOut,
    ContractorOptionOut,
    DeliveryOut,
    QuoteRefOut,
    ReceivedRequestOut,
)
from grip.services import assignments, client_side
from grip.services.errors import DomainValidationError, NotFoundError

router = APIRouter(tags=["client"])

_A = DataClass.ASSIGNMENT_BASIC
_B = DataClass.ASSIGNMENT_FINANCIAL


async def may_request(access: Access) -> bool:
    """The aanvrager asks for quotes; the beheerder may as well."""
    return await access.may(
        Action.REQUEST_ASSIGNMENT, Resource.instance()
    ) or await access.may(Action.MANAGE_USERS, Resource.instance())


async def require_may_request(access: Access) -> None:
    if not await may_request(access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Je hebt hier geen toegang toe",
        )


def delivery_out(delivery: client_side.Delivery | None) -> DeliveryOut | None:
    if delivery is None:
        return None
    return DeliveryOut(
        operation=delivery.operation,
        status=delivery.status,
        queued_at=delivery.queued_at,
        sent_at=delivery.sent_at,
        attempts=delivery.attempts,
    )


def quote_ref_out(quote: client_side.QuoteRef | None) -> QuoteRefOut | None:
    if quote is None:
        return None
    return QuoteRefOut(
        id=quote.id,
        status=quote.status,
        issued_at=quote.issued_at,
        total_cents=quote.total_cents,
    )


def _row_fields(row: client_side.ClientAssignment) -> dict[str, Any]:
    assignment = row.assignment
    return {
        "id": assignment.id,
        "uri": assignment.uri,
        "name": assignment.name,
        "status": assignment.status,
        "contractor_name": row.contractor_name,
        "start_date": assignment.start_date,
        "end_date": assignment.end_date,
        "created_at": assignment.created_at,
        "context_count": len(assignment.context_refs or []),
        "latest_quote": quote_ref_out(row.latest_quote),
        "request_delivery": delivery_out(row.request_delivery),
    }


def _sending_problem(settings: Settings) -> str | None:
    """Why a request would stay in this instance, when that is so."""
    if not settings.FEDERATION_OUTBOUND_ENABLED:
        return (
            "Het verkeer met andere organisaties staat uit in deze instantie. "
            "Een aanvraag wordt vastgelegd, maar niet verstuurd."
        )
    if not settings.OUTWAY_URL:
        return (
            "Deze instantie is niet verbonden met andere organisaties. "
            "Een aanvraag wordt vastgelegd, maar niet verstuurd."
        )
    if not settings.INSTANCE_TOOI_URI:
        return (
            "Van deze instantie is niet vastgelegd welke organisatie zij is "
            "(TOOI-URI). Zonder dat kan zij geen aanvraag versturen."
        )
    return None


@router.get("/client/options", response_model=None)
async def client_options(
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Whether the person may ask for a quote, and from whom."""
    allowed = await may_request(access)
    contractors: list[ContractorOptionOut] = []
    problem = None
    if allowed:
        peers = await client_side.contractor_peers(db)
        contractors = [
            ContractorOptionOut(
                peer_id=peer.id,
                name=peer.name,
                base_uri=normalize_uri(peer.base_uri),
                reachable=client_side.has_grant(
                    peer, client_side.SERVICE_OPDRACHTVERKEER
                )
                and bool(peer.organisation_tooi_uri),
            )
            for peer in peers
        ]
        problem = _sending_problem(settings)
        if problem is None and not contractors:
            problem = (
                "Er is nog geen opdrachtnemer gekoppeld aan deze instantie. "
                "De beheerder legt koppelingen vast."
            )
    return build_response(
        ClientOptionsOut(may_request=allowed, contractors=contractors, problem=problem),
        {_A},
    )


async def _detail(
    db: DbSession,
    access: Access,
    row: client_side.ClientAssignment,
    settings: Settings,
) -> dict[str, Any]:
    assignment = row.assignment
    resource = Resource.assignment(assignment.id)
    peer = await client_side.contractor_peer(db, assignment)
    reachable = (
        peer is not None
        and bool(settings.OUTWAY_URL)
        and client_side.has_grant(peer, client_side.SERVICE_OPDRACHTVERKEER)
    )
    value = ClientAssignmentDetailOut(
        **_row_fields(row),
        description=assignment.notes,
        context_refs=list(assignment.context_refs or []),
        quotes=[
            quote
            for quote in (
                quote_ref_out(ref)
                for ref in await client_side.quotes_of(db, assignment.id)
            )
            if quote is not None
        ],
        contractor_reachable=reachable,
        may_request_usage=reachable and await access.may(Action.READ, resource, _B),
    )
    permitted = await access.classes(resource, schema_classes(type(value)))
    return build_response(value, permitted)


@router.post(
    "/client/requests", response_model=None, status_code=status.HTTP_201_CREATED
)
async def request_quote(
    body: AssignmentRequestIn,
    access: RequestAccess,
    db: DbSession,
    person: CurrentPerson,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Ask a contractor for a quote, with this instance as the client."""
    await require_may_request(access)
    peer = await db.get(Peer, body.contractor_peer_id)
    if (
        peer is None
        or not peer.is_active
        or peer not in await client_side.contractor_peers(db)
    ):
        raise DomainValidationError(
            "Deze opdrachtnemer is niet gekoppeld aan deze instantie."
        )
    if not peer.organisation_tooi_uri:
        raise DomainValidationError(
            "Bij de koppeling met deze opdrachtnemer ontbreekt de organisatie "
            "(TOOI-URI). De beheerder vult die aan."
        )
    if settings.FEDERATION_OUTBOUND_ENABLED and not settings.INSTANCE_TOOI_URI:
        raise DomainValidationError(
            "Van deze instantie is niet vastgelegd welke organisatie zij is "
            "(TOOI-URI). Zonder dat kan zij geen aanvraag versturen."
        )
    own = await own_organisation(db, settings)
    contractor = await from_reference(
        db,
        {
            "tooi_uri": peer.organisation_tooi_uri,
            "name": peer.name,
            "instance_uri": peer.base_uri,
        },
    )
    assignment, _request_id = await assignments.create_assignment_request(
        db,
        name=body.name,
        contractor_organisation_id=contractor.id,
        client_organisation_id=own.id,
        actor=person,
        description=(body.description or "").strip() or None,
        context_refs=body.context_uris,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    # The requester became the owner of the assignment in this instance.
    access.forget()
    row = await client_side.client_assignment(db, assignment.id, settings)
    assert row is not None
    return await _detail(db, access, row, settings)


@router.get("/client/assignments", response_model=None)
async def list_client_assignments(
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The assignments this instance is the client of, as far as visible."""
    items: list[dict[str, Any]] = []
    for row in await client_side.client_assignments(db, settings):
        resource = Resource.assignment(row.assignment.id)
        if not await access.may(Action.READ, resource, _A):
            continue
        value = ClientAssignmentOut(**_row_fields(row))
        permitted = await access.classes(resource, schema_classes(type(value)))
        items.append(build_response(value, permitted))
    head = build_response(
        ClientAssignmentListOut(may_request=await may_request(access)), {_A}
    )
    return {**head, "items": items}


@router.get("/client/assignments/{assignment_id}", response_model=None)
async def get_client_assignment(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    await access.require(
        Action.READ, Resource.assignment(assignment_id), _A, hide_existence=True
    )
    row = await client_side.client_assignment(db, assignment_id, settings)
    if row is None:
        # Not an assignment this instance is the client of.
        raise NotFoundError("Opdracht", assignment_id)
    return await _detail(db, access, row, settings)


@router.get("/received-requests", response_model=None)
async def list_received_requests(
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Requests other instances sent to this one, as far as visible."""
    items: list[dict[str, Any]] = []
    for row in await client_side.received_requests(db, settings):
        assignment = row.assignment
        resource = Resource.assignment(assignment.id)
        if not await access.may(Action.READ, resource, _A):
            continue
        value = ReceivedRequestOut(
            id=assignment.id,
            uri=assignment.uri,
            name=assignment.name,
            status=assignment.status,
            client_name=row.client_name,
            start_date=assignment.start_date,
            end_date=assignment.end_date,
            description=assignment.notes,
            context_count=len(assignment.context_refs or []),
            quote_count=row.quote_count,
            received_at=assignment.created_at,
        )
        permitted = await access.classes(resource, schema_classes(type(value)))
        items.append(build_response(value, permitted))
    return {"items": items}
