"""From a domain event to the message another instance gets.

A builder reads what the event names through the repositories and the
service layer, and returns the message in code names plus, where the message
does not name its receiver, the recipient. It returns None when nothing has
to be sent: the change came from another instance (``origin`` is remote),
the assignment has no federated traffic, or a party cannot be named.

The outbox translates the message to contract terms and validates it; a
message that does not fit the contract aborts the domain change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.federation import signing, terms
from grip.federation.bridge.organisations import (
    organisation_by_id,
    own_reference,
    reference,
)
from grip.models.assignment import Assignment
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository
from grip.repositories.vacancy import VacancyRepository
from grip.services.assignments import mint_uri

Built = dict[str, Any] | None

# A vacancy in the domain has more statuses than cross the boundary.
_VACANCY_STATUSES = {"open", "filled", "withdrawn"}


def _is_remote(payload: dict[str, Any]) -> bool:
    return payload.get("origin") == "remote"


def _decimal_text(value: Decimal) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text if text != "-0" else "0"


async def _federated_assignment(
    db: AsyncSession, payload: dict[str, Any]
) -> Assignment | None:
    assignment = await AssignmentRepository(db).get(UUID(payload["assignment_id"]))
    if assignment is None or assignment.traffic_form != "federated":
        return None
    return assignment


async def _party(db: AsyncSession, organisation_id: Any) -> dict[str, Any] | None:
    """A party of an assignment; this instance when none is recorded."""
    if organisation_id is None:
        return own_reference()
    return reference(await organisation_by_id(db, organisation_id))


def _quote_hash(snapshot: dict[str, Any]) -> str:
    """The hash as the contract defines it: over the snapshot in contract terms."""
    return signing.snapshot_hash(terms.to_contract(snapshot))


async def assignment_request(db: AsyncSession, payload: dict[str, Any]) -> Built:
    """This instance, as client, asks a contractor for a quote."""
    if _is_remote(payload):
        return None
    assignment = await _federated_assignment(db, payload)
    if assignment is None:
        return None
    client = await _party(db, assignment.client_organisation_id)
    contractor = reference(
        await organisation_by_id(db, assignment.contractor_organisation_id)
    )
    if client is None or contractor is None:
        return None
    message: dict[str, Any] = {
        "id": payload["request_id"],
        "assignment_uri": assignment.uri,
        "name": assignment.name,
        "client": client,
        "contractor": contractor,
        "context_refs": list(assignment.context_refs or []),
        "parent_assignment_uri": assignment.parent_assignment_uri,
        "sent_at": datetime.now(UTC).isoformat(),
    }
    if payload.get("description"):
        message["description"] = payload["description"]
    if assignment.start_date is not None:
        message["desired_period"] = {
            "start_date": assignment.start_date.isoformat(),
            "end_date": assignment.end_date.isoformat()
            if assignment.end_date
            else None,
        }
    return {"message": message}


async def quote_issued(db: AsyncSession, payload: dict[str, Any]) -> Built:
    """This instance, as contractor, issued a quote."""
    if _is_remote(payload):
        return None
    assignment = await _federated_assignment(db, payload)
    if assignment is None:
        return None
    client = reference(await organisation_by_id(db, assignment.client_organisation_id))
    if client is None:
        return None
    message = {
        "id": payload["quote_id"],
        "uri": payload["quote_uri"],
        "assignment_uri": assignment.uri,
        "request_id": payload.get("request_id"),
        "contractor": own_reference(),
        "client": client,
        "parent_assignment_uri": assignment.parent_assignment_uri,
        "snapshot": payload["snapshot"],
        "snapshot_hash": _quote_hash(payload["snapshot"]),
        "hash_algorithm": "sha-256",
        "canonicalization": "RFC8785",
        "issued_at": payload["issued_at"],
    }
    return {"message": message}


async def _decision_recipient(
    db: AsyncSession, payload: dict[str, Any]
) -> tuple[Quote, dict[str, Any]] | None:
    """The quote a decision is about and the contractor that issued it."""
    assignment = await _federated_assignment(db, payload)
    quote = await db.get(Quote, UUID(payload["quote_id"]))
    if assignment is None or quote is None:
        return None
    contractor = reference(
        await organisation_by_id(db, assignment.contractor_organisation_id)
    )
    if contractor is None:
        return None
    return quote, contractor


async def quote_accepted(db: AsyncSession, payload: dict[str, Any]) -> Built:
    """This instance, as client, accepted a quote of a contractor.

    Only an acceptance that was signed here goes out. One that was recorded
    at the contractor (signing link, signed pdf) is already where it belongs.
    """
    if _is_remote(payload) or payload.get("form") != "own_instance":
        return None
    found = await _decision_recipient(db, payload)
    if found is None or not payload.get("jws"):
        return None
    quote, contractor = found
    message = {
        "id": payload["acceptance_id"],
        "quote_id": payload["quote_id"],
        "quote_hash": _quote_hash(quote.snapshot),
        "signer": payload["signer"],
        "organisation": payload["organisation"],
        "signed_at": payload["signed_at"],
        "form": payload["form"],
        "jws": payload["jws"],
    }
    return {"message": message, "recipient": contractor}


async def quote_rejected(db: AsyncSession, payload: dict[str, Any]) -> Built:
    if _is_remote(payload):
        return None
    found = await _decision_recipient(db, payload)
    if found is None:
        return None
    quote, contractor = found
    message = {
        "id": payload["rejection_id"],
        "quote_id": payload["quote_id"],
        "quote_hash": _quote_hash(quote.snapshot),
        "organisation": payload.get("organisation") or own_reference(),
        "reason": payload.get("reason"),
        "rejected_at": payload["rejected_at"],
    }
    return {"message": message, "recipient": contractor}


async def final_report(db: AsyncSession, payload: dict[str, Any]) -> Built:
    """This instance, as contractor, sends the final report to the client."""
    if _is_remote(payload):
        return None
    assignment = await _federated_assignment(db, payload)
    if assignment is None:
        return None
    client = reference(await organisation_by_id(db, assignment.client_organisation_id))
    if client is None:
        return None
    report = payload.get("report") or {}
    # The same report gives the same message id, so issuing it twice is one
    # message; a revised report is a new one.
    digest = signing.payload_hash(report)
    message: dict[str, Any] = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{assignment.uri}#{digest}")),
        "assignment_uri": assignment.uri,
        "agreed": list(report.get("agreed") or []),
        "delivered": list(report.get("delivered") or []),
        "not_delivered": list(report.get("not_delivered") or []),
        "issued_at": report.get("issued_at") or datetime.now(UTC).isoformat(),
    }
    for optional in ("period", "total_cost", "summary"):
        if report.get(optional) is not None:
            message[optional] = report[optional]
    return {"message": message, "recipient": client}


async def vacancy_published(db: AsyncSession, payload: dict[str, Any]) -> Built:
    """An open role with an established text is put out to other instances."""
    if _is_remote(payload) or "federated" not in (payload.get("channels") or []):
        return None
    repository = VacancyRepository(db)
    vacancy = await repository.get(UUID(payload["vacancy_id"]))
    text = await repository.text(UUID(payload["text_id"]))
    if vacancy is None or text is None or vacancy.status not in _VACANCY_STATUSES:
        return None
    published_at = vacancy.published_at or datetime.now(UTC)
    assignment_uri = None
    rate_category = None
    if vacancy.budget_line_id is not None:
        lines = await AssignmentRepository(db).budget_lines_by_id(
            [vacancy.budget_line_id]
        )
        if lines:
            rate_category = lines[0].rate_category
            assignment = await AssignmentRepository(db).get(lines[0].assignment_id)
            assignment_uri = assignment.uri if assignment is not None else None
    uri = mint_uri("vacature", vacancy.id)
    start = vacancy.start_date or published_at.date()
    message = {
        # A change of status is a new message about the same vacancy.
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{uri}#{vacancy.status}")),
        "uri": uri,
        "organisation": own_reference(),
        "assignment_uri": assignment_uri,
        "role": vacancy.function_title,
        "description": text.body,
        "rate_category": rate_category,
        "fte": _decimal_text(vacancy.fte),
        "period": {
            "start_date": start.isoformat(),
            "end_date": vacancy.end_date.isoformat() if vacancy.end_date else None,
        },
        "status": vacancy.status,
        "published_at": published_at.isoformat(),
    }
    return {"message": message}


BUILDERS = {
    "assignment_request.created": assignment_request,
    "quote.issued": quote_issued,
    "quote.accepted": quote_accepted,
    "quote.rejected": quote_rejected,
    "final_report.issued": final_report,
    "vacancy.published": vacancy_published,
}
