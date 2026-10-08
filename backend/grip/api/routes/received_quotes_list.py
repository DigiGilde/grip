"""Quotes that contractors sent to this instance: the list and one quote.

Deciding on a received quote is in ``received_quotes.py`` (acceptance and
rejection by a tekenbevoegde, signed and sent through the bridge). This file
adds what a person needs before and after deciding: which quotes came in,
the frozen snapshot as the contractor issued it with its hash, and whether
the decision reached the contractor.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess
from grip.api.routes.client_requests import delivery_out
from grip.api.routes.quotes import summary_fields
from grip.core.config import Settings, get_settings
from grip.schema.client_side import (
    ReceivedQuoteDetailOut,
    ReceivedQuoteRowOut,
)
from grip.schema.quotes import QuoteDetailOut, content_from_snapshot
from grip.services import client_side
from grip.services.errors import NotFoundError
from grip.services.quote_views import QuoteBundle

router = APIRouter(prefix="/received-quotes", tags=["received-quotes"])

_A = DataClass.ASSIGNMENT_BASIC


@router.get("", response_model=None)
async def list_received_quotes(
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The received quotes the person may know of, newest first."""
    items: list[dict[str, Any]] = []
    for row in await client_side.received_quotes(db, settings):
        resource = Resource.quote(row.quote.id, row.quote.assignment_id)
        if not await access.may(Action.READ, resource, _A):
            continue
        value = ReceivedQuoteRowOut(
            id=row.quote.id,
            assignment_id=row.assignment.id,
            assignment_name=row.assignment.name,
            contractor_name=row.contractor_name,
            status=row.quote.status,
            issued_at=row.quote.issued_at,
            total_cents=row.quote.total_cents,
            may_decide=row.quote.status == "issued"
            and await access.may(Action.ACCEPT_QUOTE, resource),
        )
        permitted = await access.classes(resource, schema_classes(type(value)))
        items.append(build_response(value, permitted))
    return {"items": items}


@router.get("/{quote_id}", response_model=None)
async def get_received_quote(
    quote_id: UUID,
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """A received quote: the snapshot, its hash, the decision and its delivery."""
    row = await client_side.received_quote(db, quote_id, settings)
    if row is None:
        raise NotFoundError("Offerte", quote_id)
    resource = Resource.quote(row.quote.id, row.quote.assignment_id)
    await access.require(Action.READ, resource, _A, hide_existence=True)
    bundle = QuoteBundle(
        quote=row.quote,
        acceptance=row.acceptance,
        rejection=row.rejection,
        issued_by_name=None,
    )
    value = ReceivedQuoteDetailOut(
        assignment_id=row.assignment.id,
        assignment_name=row.assignment.name,
        contractor_name=row.contractor_name,
        may_decide=row.quote.status == "issued"
        and await access.may(Action.ACCEPT_QUOTE, resource),
        quote=QuoteDetailOut(
            **summary_fields(bundle), content=content_from_snapshot(row.quote.snapshot)
        ),
        deliveries=[
            out
            for out in (delivery_out(delivery) for delivery in row.deliveries)
            if out is not None
        ],
    )
    permitted = await access.classes(resource, schema_classes(type(value)))
    return build_response(value, permitted)
