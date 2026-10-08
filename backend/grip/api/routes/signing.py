"""The signing link: an invited person sees one quote and accepts or rejects it.

Everything here runs as a guest subject (see ``grip.access.guest_deps``):
the decider lets a guest read and sign exactly the quotes they were invited
to, and nothing else. A quote the signer was not invited to answers 404, the
same as a quote that does not exist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, Decider, Resource
from grip.access.deps import AccessDecider, require
from grip.access.guest_deps import CurrentSigner, Signer
from grip.api.routes.quotes import document_response, filtered
from grip.core.database import get_db
from grip.models.quote import Quote
from grip.schema.quotes import content_from_snapshot, document_fields
from grip.schema.signing import (
    SignAcceptIn,
    SigningInvitationOut,
    SigningQuoteOut,
    SignRejectIn,
)
from grip.services import quote_views, quotes
from grip.services.errors import DomainValidationError, NotFoundError

router = APIRouter(prefix="/signing", tags=["signing"])


async def invited_quote(
    db: AsyncSession, decider: Decider, signer: Signer, quote_id: UUID
) -> tuple[Quote, Resource]:
    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    resource = Resource.quote(quote.id, quote.assignment_id)
    await require(
        decider,
        signer.subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    return quote, resource


async def signing_view(
    db: AsyncSession, decider: Decider, signer: Signer, quote: Quote, resource: Resource
) -> dict[str, Any]:
    context = await quote_views.document_context(db, quote)
    bundle = await quote_views.quote_bundle(db, quote.id)
    decided_at = None
    if bundle.acceptance is not None:
        decided_at = bundle.acceptance.signed_at
    elif bundle.rejection is not None:
        decided_at = bundle.rejection.rejected_at
    value = SigningQuoteOut(
        id=quote.id,
        uri=quote.uri,
        reference=quote.reference,
        status=quote.status,
        issued_at=quote.issued_at,
        contractor_name=str(quote.snapshot.get("sender") or context.contractor_name),
        client_name=context.client_name,
        snapshot_hash=quote.snapshot_hash,
        **document_fields(quote),
        content=content_from_snapshot(quote.snapshot),
        decided_at=decided_at,
    )
    return await filtered(decider, signer.subject, resource, value)


@router.get("/invitations", response_model=None)
async def my_invitations(
    signer: CurrentSigner,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The quotes the signer is invited to sign."""
    rows = await quote_views.invited_quotes(db, signer.email)
    items = []
    for invitation, quote, assignment in rows:
        resource = Resource.quote(quote.id, quote.assignment_id)
        item = SigningInvitationOut(
            quote_id=quote.id,
            reference=quote.reference,
            assignment_name=quote.snapshot.get("name") or assignment.name,
            status=quote.status,
            issued_at=quote.issued_at,
            valid_until=quote.snapshot.get("valid_until"),
            expires_at=invitation.expires_at,
        )
        items.append((resource, item))
    invitations = [
        await filtered(decider, signer.subject, resource, item)
        for resource, item in items
    ]
    # Each entry is filtered against its own quote; an entry the decider
    # grants nothing on would be empty and is left out.
    visible = [entry for entry in invitations if entry]
    return {"invitations": visible}


@router.get("/quotes/{quote_id}", response_model=None)
async def get_signing_quote(
    quote_id: UUID,
    signer: CurrentSigner,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The one quote behind a signing link."""
    quote, resource = await invited_quote(db, decider, signer, quote_id)
    # Whoever offered the quote sees that the invited person opened it.
    await quotes.mark_invitation_opened(db, quote.id, signer.email)
    return await signing_view(db, decider, signer, quote, resource)


@router.get("/quotes/{quote_id}/document")
async def signing_document(
    quote_id: UUID,
    signer: CurrentSigner,
    decider: AccessDecider,
    download: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The quote as a document, for the invited signer: page or PDF."""
    quote, resource = await invited_quote(db, decider, signer, quote_id)
    await require(
        decider,
        signer.subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_FINANCIAL,
    )
    return await document_response(db, quote, download=download)


@router.post(
    "/quotes/{quote_id}/accept",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def accept(
    quote_id: UUID,
    body: SignAcceptIn,
    signer: CurrentSigner,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Accept the quote on behalf of the client."""
    quote, resource = await invited_quote(db, decider, signer, quote_id)
    await require(decider, signer.subject, Action.ACCEPT_QUOTE, resource)
    if not body.confirm_mandate:
        raise DomainValidationError(
            "Bevestig dat je namens de opdrachtgever mag tekenen."
        )
    await quote_views.accept_via_signing_link(
        db,
        quote.id,
        quote_hash=body.quote_hash,
        signer_name=signer.name,
        signer_email=signer.email,
        signer_person_id=signer.person_id,
        signer_function=body.signer_function,
        organisation_name=body.organisation_name,
    )
    await db.refresh(quote)
    return await signing_view(db, decider, signer, quote, resource)


@router.post(
    "/quotes/{quote_id}/reject",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def reject(
    quote_id: UUID,
    body: SignRejectIn,
    signer: CurrentSigner,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reject the quote on behalf of the client."""
    quote, resource = await invited_quote(db, decider, signer, quote_id)
    await require(decider, signer.subject, Action.ACCEPT_QUOTE, resource)
    await quote_views.reject_via_signing_link(
        db,
        quote.id,
        quote_hash=body.quote_hash,
        signer_person_id=signer.person_id,
        reason=body.reason,
    )
    await db.refresh(quote)
    return await signing_view(db, decider, signer, quote, resource)
