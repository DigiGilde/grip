"""The routes of grip-opdrachtverkeer, as other instances call them.

Paths, parameters and message bodies are in the Dutch terms of the contract.
A received body is validated, hashed and stored as it came in; the checks
here and the domain handlers work with its translation to code names (see
:mod:`grip.federation.terms`). An answer is built in code names and
translated right before it is validated and sent.

Mounted without a prefix here; the federation app serves them under ``/v1``.
Every route depends on the peer check. Paths, methods and parameters are
written out by hand and compared with the vendored contract in the tests;
the schemas in the generated OpenAPI refer to the contract's own schemas.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.events import context as event_context
from grip.federation import signing, terms
from grip.federation.contract_loader import (
    SERVICE_OPDRACHTVERKEER,
    Operation,
    api_version,
    load_openapi,
    operation,
    validation_errors,
)
from grip.federation.models import FederationInbox, Peer
from grip.federation.outway import OutwayClient
from grip.federation.peers import (
    PeerKeysUnavailableError,
    get_peer_jwks,
    normalize_uri,
    require_caller,
)
from grip.federation.problems import PROBLEM_MEDIA_TYPE, FederationProblem
from grip.federation.registry import (
    InboundMessage,
    get_inbound_handler,
    get_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter()

API_VERSION_HEADER = "API-Version"
_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@lru_cache(maxsize=1)
def _shared_outway() -> OutwayClient:
    return OutwayClient(get_settings())


def get_outway_client() -> OutwayClient:
    """The outway client of this process. Overridden in tests."""
    return _shared_outway()


def _docs(operation_id: str) -> dict[str, Any]:
    """Route arguments that describe an operation with the contract's schemas."""
    op = operation(operation_id)
    responses: dict[int | str, dict[str, Any]] = {}
    for status, schema in op.response_schemas.items():
        media = "application/json" if status.startswith("2") else PROBLEM_MEDIA_TYPE
        responses[int(status)] = {
            "description": f"Zie het contract ({operation_id}, {status}).",
            "content": {media: {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
        }
    extra: dict[str, Any] = {
        "x-grip-caller": op.caller,
        "x-grip-data-class": list(op.data_classes),
    }
    if op.on_request:
        extra["x-grip-on-request"] = True
    if op.request_schema:
        extra["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{op.request_schema}"}
                }
            },
        }
    return {
        "operation_id": operation_id,
        "responses": responses,
        "openapi_extra": extra,
        "response_class": JSONResponse,
    }


def _json(body: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        body, status_code=status_code, headers={API_VERSION_HEADER: api_version()}
    )


# --- pushed messages -------------------------------------------------------


async def _read_json(request: Request) -> Any:
    try:
        return json.loads(await request.body())
    except ValueError as exc:
        raise FederationProblem(
            400, "Ongeldig bericht", "De inhoud is geen geldige JSON."
        ) from exc


def _require_same(path_value: UUID, body_value: str, field: str) -> None:
    """``field`` is the code name; the message names the contract term."""
    if str(path_value) != body_value.lower():
        raise FederationProblem(
            400,
            "Ongeldig bericht",
            f"Het veld {terms.term(field)} in het bericht hoort niet bij het pad.",
        )


def _require_sender(peer: Peer, organisation: dict[str, Any], field: str) -> None:
    """A peer may not send a message in the name of another instance."""
    instance_uri = organisation.get("instance_uri")
    if instance_uri and normalize_uri(instance_uri) != normalize_uri(peer.base_uri):
        raise FederationProblem(
            403,
            "Geen toegang",
            f"Het veld {terms.term(field)} noemt een andere instantie dan de afzender.",
        )


def _receipt(row: FederationInbox, outcome: str) -> dict[str, Any]:
    receipt: dict[str, Any] = terms.to_contract(
        {
            "message_id": str(row.message_id),
            "received_at": row.received_at.astimezone(UTC).isoformat(),
            "outcome": outcome,
        }
    )
    return receipt


async def _find_inbox(
    db: AsyncSession, peer: Peer, message_id: UUID
) -> FederationInbox | None:
    return (
        await db.execute(
            select(FederationInbox).where(
                FederationInbox.peer_id == peer.id,
                FederationInbox.message_id == message_id,
            )
        )
    ).scalar_one_or_none()


def _repeat(existing: FederationInbox, op: Operation, digest: str) -> JSONResponse:
    """The answer to a message id that was received before."""
    if existing.payload_hash == digest and existing.operation == op.operation_id:
        return _json(_receipt(existing, "duplicate"), 200)
    raise FederationProblem(
        409,
        "Bericht bestaat al met andere inhoud",
        "Een bericht met dit id en andere inhoud is al ontvangen.",
    )


async def receive(
    db: AsyncSession,
    peer: Peer,
    op: Operation,
    payload: Any,
    path_parameters: dict[str, str] | None = None,
) -> JSONResponse:
    """Store a validated message and hand it to the domain handler.

    ``payload`` is the message in contract terms, as received. It is stored
    like that; the handler gets it in code names.

    201 on first receipt, 200 with outcome duplicate when the same id with
    the same content was received before, 409 when the content differs.
    """
    message_id = UUID(payload["id"])
    digest = signing.payload_hash(payload)
    # Everything this message causes is the peer's doing and shares one id.
    event_context.set_peer(peer.peer_id)
    event_context.update(correlation_id=message_id.hex)

    existing = await _find_inbox(db, peer, message_id)
    if existing is not None:
        return _repeat(existing, op, digest)

    row = FederationInbox(
        message_id=message_id,
        peer_id=peer.id,
        operation=op.operation_id,
        payload_hash=digest,
        payload=payload,
        received_at=datetime.now(UTC),
    )
    try:
        # A savepoint, so that a handler that refuses the message leaves
        # nothing behind, whatever the caller does with the transaction.
        async with db.begin_nested():
            db.add(row)
            await db.flush()
            handler = get_inbound_handler(op.operation_id)
            if handler is not None:
                result = await handler(
                    db,
                    peer,
                    InboundMessage(
                        message_id=message_id,
                        operation=op.operation_id,
                        payload=terms.from_contract(payload),
                        path_parameters=path_parameters or {},
                        contract_payload=payload,
                        received_at=row.received_at,
                    ),
                )
                row.processed_at = datetime.now(UTC)
                row.result = result or {}
                await db.flush()
    except IntegrityError:
        # The same message arrived twice at the same moment.
        existing = await _find_inbox(db, peer, message_id)
        if existing is None:
            raise
        return _repeat(existing, op, digest)
    return _json(_receipt(row, "accepted"), 201)


async def _validated_body(request: Request, op: Operation) -> dict[str, Any]:
    payload = await _read_json(request)
    errors = validation_errors(op.request_schema or "", payload)
    if errors:
        raise FederationProblem(
            400,
            "Ongeldig bericht",
            "Het bericht voldoet niet aan het schema van het contract.",
            errors=errors,
        )
    return payload


@router.post("/opdrachtaanvragen", **_docs("sendAssignmentRequest"))
async def send_assignment_request(
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendAssignmentRequest")),
) -> JSONResponse:
    op = operation("sendAssignmentRequest")
    payload = await _validated_body(request, op)
    message = terms.from_contract(payload)
    _require_sender(peer, message["client"], "client")
    return await receive(db, peer, op, payload)


@router.post("/offertes", **_docs("sendQuote"))
async def send_quote(
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendQuote")),
) -> JSONResponse:
    op = operation("sendQuote")
    payload = await _validated_body(request, op)
    message = terms.from_contract(payload)
    _require_sender(peer, message["contractor"], "contractor")
    # The hash is over the snapshot as it crosses the boundary.
    snapshot = payload[terms.term("snapshot")]
    if signing.snapshot_hash(snapshot) != message["snapshot_hash"]:
        raise FederationProblem(
            400,
            "Hash komt niet overeen",
            f"De {terms.term('snapshot_hash')} is niet de SHA-256 over de canonieke "
            f"JSON van {terms.term('snapshot')}.",
        )
    return await receive(db, peer, op, payload)


@router.post("/offertes/{offerteId}/akkoorden", **_docs("sendAcceptance"))
async def send_acceptance(
    offerteId: UUID,  # noqa: N803 - parameter name as in the contract
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendAcceptance")),
    settings: Settings = Depends(get_settings),
    outway: OutwayClient = Depends(get_outway_client),
) -> JSONResponse:
    op = operation("sendAcceptance")
    payload = await _validated_body(request, op)
    message = terms.from_contract(payload)
    _require_same(offerteId, message["quote_id"], "quote_id")
    if message["form"] == "own_instance":
        try:
            jwks = await get_peer_jwks(
                db, peer, outway, settings, kid=signing.jws_kid(message["jws"])
            )
        except PeerKeysUnavailableError as exc:
            raise FederationProblem(
                503,
                "Sleutels van de afzender niet beschikbaar",
                "De handtekening is nu niet te controleren. Probeer het later opnieuw.",
            ) from exc
        try:
            signing.verify_acceptance(payload, jwks)
        except signing.SignatureInvalidError as exc:
            raise FederationProblem(
                400, "Handtekening ongeldig", "De JWS van het akkoord klopt niet."
            ) from exc
    return await receive(db, peer, op, payload, {"quoteId": str(offerteId)})


@router.post("/offertes/{offerteId}/afwijzingen", **_docs("sendRejection"))
async def send_rejection(
    offerteId: UUID,  # noqa: N803
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendRejection")),
) -> JSONResponse:
    op = operation("sendRejection")
    payload = await _validated_body(request, op)
    message = terms.from_contract(payload)
    _require_same(offerteId, message["quote_id"], "quote_id")
    return await receive(db, peer, op, payload, {"quoteId": str(offerteId)})


@router.put("/opdrachten/{opdrachtId}/eindrapport", **_docs("sendFinalReport"))
async def send_final_report(
    opdrachtId: UUID,  # noqa: N803
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendFinalReport")),
) -> JSONResponse:
    op = operation("sendFinalReport")
    payload = await _validated_body(request, op)
    message = terms.from_contract(payload)
    if not normalize_uri(message["assignment_uri"]).lower().endswith(f"/{opdrachtId}"):
        raise FederationProblem(
            400,
            "Ongeldig bericht",
            f"Het veld {terms.term('assignment_uri')} in het bericht hoort niet "
            "bij het pad.",
        )
    return await receive(db, peer, op, payload, {"assignmentId": str(opdrachtId)})


@router.post("/vacatures", **_docs("sendVacancy"))
async def send_vacancy(
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendVacancy")),
) -> JSONResponse:
    op = operation("sendVacancy")
    payload = await _validated_body(request, op)
    return await receive(db, peer, op, payload)


@router.post("/vacatures/{vacatureId}/aanbiedingen", **_docs("sendVacancyOffer"))
async def send_vacancy_offer(
    vacatureId: UUID,  # noqa: N803
    request: Request,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("sendVacancyOffer")),
) -> JSONResponse:
    op = operation("sendVacancyOffer")
    payload = await _validated_body(request, op)
    message = terms.from_contract(payload)
    _require_same(vacatureId, message["vacancy_id"], "vacancy_id")
    return await receive(db, peer, op, payload, {"vacancyId": str(vacatureId)})


# --- pull operations -------------------------------------------------------


async def provide(
    db: AsyncSession, peer: Peer, operation_id: str, parameters: dict[str, Any]
) -> JSONResponse:
    """Answer a pull operation with what the registered provider returns."""
    op = operation(operation_id)
    provider = get_provider(operation_id)
    if provider is None:
        raise FederationProblem(
            501,
            "Nog niet beschikbaar",
            "Deze instantie biedt deze operatie nog niet aan.",
        )
    body = await provider(db, peer, parameters)
    if body is None:
        raise FederationProblem(
            404, "Niet gevonden", "Niet gevonden, of er is geen relatie mee."
        )
    # The provider answers in code names.
    body = terms.to_contract(body)
    errors = validation_errors(op.success_schema or "", body)
    if errors:
        # Never send something across the boundary that the contract does
        # not describe; the fault is on this side.
        logger.error("Provider of %s broke the contract: %s", operation_id, errors)
        raise FederationProblem(
            500,
            "Interne fout",
            "Het antwoord van deze instantie voldoet niet aan het contract.",
        )
    return _json(body)


@router.get("/opdrachten", **_docs("listAssignmentsByNode"))
async def list_assignments_by_node(
    node_uri: Annotated[str, Query(alias="nodeUri", min_length=1)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("listAssignmentsByNode")),
) -> JSONResponse:
    return await provide(
        db,
        peer,
        "listAssignmentsByNode",
        {"nodeUri": node_uri, "page": page, "pageSize": page_size},
    )


@router.get("/opdrachten/{opdrachtId}", **_docs("getAssignment"))
async def get_assignment(
    opdrachtId: UUID,  # noqa: N803
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getAssignment")),
) -> JSONResponse:
    return await provide(db, peer, "getAssignment", {"assignmentId": opdrachtId})


@router.get("/opdrachten/{opdrachtId}/voortgang", **_docs("getProgress"))
async def get_progress(
    opdrachtId: UUID,  # noqa: N803
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getProgress")),
) -> JSONResponse:
    return await provide(db, peer, "getProgress", {"assignmentId": opdrachtId})


@router.get("/opdrachten/{opdrachtId}/uitputting", **_docs("getBudgetUsage"))
async def get_budget_usage(
    opdrachtId: UUID,  # noqa: N803
    year: Annotated[int | None, Query(alias="jaar", ge=2000)] = None,
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getBudgetUsage")),
) -> JSONResponse:
    return await provide(
        db, peer, "getBudgetUsage", {"assignmentId": opdrachtId, "year": year}
    )


@router.get("/opdrachten/{opdrachtId}/factuurgegevens", **_docs("getBillingData"))
async def get_billing_data(
    opdrachtId: UUID,  # noqa: N803
    month: Annotated[str, Query(alias="maand", pattern=_MONTH_PATTERN)],
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getBillingData")),
) -> JSONResponse:
    return await provide(
        db, peer, "getBillingData", {"assignmentId": opdrachtId, "month": month}
    )


@router.get("/doorgifte/opdrachten", **_docs("getHandoverAssignments"))
async def get_handover_assignments(
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getHandoverAssignments")),
) -> JSONResponse:
    return await provide(db, peer, "getHandoverAssignments", {})


@router.get("/doorgifte/factuurgegevens", **_docs("getHandoverBillingData"))
async def get_handover_billing_data(
    month: Annotated[str, Query(alias="maand", pattern=_MONTH_PATTERN)],
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getHandoverBillingData")),
) -> JSONResponse:
    return await provide(db, peer, "getHandoverBillingData", {"month": month})


@router.get("/doorgifte/bemensing", **_docs("getHandoverStaffing"))
async def get_handover_staffing(
    month: Annotated[str, Query(alias="maand", pattern=_MONTH_PATTERN)],
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getHandoverStaffing")),
) -> JSONResponse:
    return await provide(db, peer, "getHandoverStaffing", {"month": month})


@router.get("/doorgifte/capaciteit", **_docs("getHandoverCapacity"))
async def get_handover_capacity(
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getHandoverCapacity")),
) -> JSONResponse:
    return await provide(db, peer, "getHandoverCapacity", {})


@router.get("/doorgifte/kosten", **_docs("getHandoverCosts"))
async def get_handover_costs(
    year: Annotated[int, Query(alias="jaar", ge=2000)],
    db: AsyncSession = Depends(get_db),
    peer: Peer = Depends(require_caller("getHandoverCosts")),
) -> JSONResponse:
    return await provide(db, peer, "getHandoverCosts", {"year": year})


# --- keys and the contract itself ------------------------------------------


@router.get("/jwks", **_docs("getJwks"))
async def get_jwks(
    _peer: Peer = Depends(require_caller("getJwks")),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    return _json(signing.own_jwks(settings))


@router.get("/openapi.json", **_docs("getOpenapi"))
async def get_contract(
    _peer: Peer = Depends(require_caller("getOpenapi")),
) -> JSONResponse:
    """The contract this instance follows, as one document."""
    return _json(load_openapi(SERVICE_OPDRACHTVERKEER))
