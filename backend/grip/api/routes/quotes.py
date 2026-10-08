"""Quotes of an assignment: preview, issue, document, invitations and decisions.

A quote is generated from the budget and issued as a frozen snapshot. The
client's decision arrives in one of three forms; the two that need no second
instance are here (uploaded pdf) and in ``signing`` (signing link).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import (
    Action,
    Context,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    decide,
    permitted_classes,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.quote import Quote
from grip.schema.quotes import (
    AcceptanceOut,
    InvitationListOut,
    InvitationOut,
    InviteSignerIn,
    IssueQuoteIn,
    QuoteDetailOut,
    QuoteListOut,
    QuotePreviewOut,
    QuoteSummaryOut,
    RecordRejectionIn,
    RejectionOut,
    content_from_snapshot,
)
from grip.services import quote_views, quotes, stored_documents
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.quote_document import render_quote_html

router = APIRouter(tags=["quotes"])

# Headers of the quote document: it is a page of its own, so it gets a
# policy that allows its inline stylesheet and nothing else.
DOCUMENT_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "Cache-Control": "private, no-store",
}


async def filtered(
    decider: Decider,
    subject: Subject,
    resource: Resource,
    value: BaseModel,
    context: Context | None = None,
) -> dict[str, Any]:
    """The response with only the fields of classes the subject may read."""
    permitted = await permitted_classes(
        decider, subject, resource, schema_classes(type(value)), context
    )
    return build_response(value, permitted)


def summary_fields(bundle: quote_views.QuoteBundle) -> dict[str, Any]:
    quote = bundle.quote
    acceptance = None
    if bundle.acceptance is not None:
        acc = bundle.acceptance
        acceptance = AcceptanceOut(
            form=acc.form,
            signed_at=acc.signed_at,
            signer_name=acc.signer_name,
            signer_function=acc.signer_function,
            organisation_name=(acc.organisation or {}).get("name"),
            has_document=stored_documents.parse_document_ref(acc.document_ref)
            is not None,
        )
    rejection = None
    if bundle.rejection is not None:
        rejection = RejectionOut(
            rejected_at=bundle.rejection.rejected_at, reason=bundle.rejection.reason
        )
    return {
        "id": quote.id,
        "uri": quote.uri,
        "assignment_id": quote.assignment_id,
        "status": quote.status,
        "issued_at": quote.issued_at,
        "issued_by_name": bundle.issued_by_name,
        "total_cents": quote.total_cents,
        "snapshot_hash": quote.snapshot_hash,
        "valid_until": quote.snapshot.get("valid_until"),
        "acceptance": acceptance,
        "rejection": rejection,
    }


async def visible_quote(
    db: AsyncSession, decider: Decider, subject: Subject, quote_id: UUID
) -> tuple[Quote, Resource]:
    """The quote, or 404 when it does not exist or the subject may not know it."""
    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    resource = Resource.quote(quote.id, quote.assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    return quote, resource


@router.get("/assignments/{assignment_id}/quote-preview", response_model=None)
async def preview_quote(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The quote as it would be issued now, with the difference to the agreed amount."""
    resource = Resource.assignment(assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    assignment = await get_assignment(db, assignment_id)
    content = None
    problem = None
    try:
        snapshot = await quotes.build_snapshot(db, assignment)
        content = content_from_snapshot(snapshot)
    except calc.CalcError as exc:
        problem = quote_views.describe_calc_error(exc)
    except DomainValidationError as exc:
        problem = str(exc)
    quoted = assignment.quoted_amount_cents
    preview = QuotePreviewOut(
        assignment_id=assignment.id,
        assignment_name=assignment.name,
        assignment_status=assignment.status,
        can_issue=assignment.status in quote_views.ISSUABLE_STATUSES
        and content is not None,
        may_issue=bool(await decide(decider, subject, Action.ISSUE_QUOTE, resource)),
        problem=problem,
        content=content,
        quoted_amount_cents=quoted,
        difference_cents=quoted - content.total_cents
        if quoted is not None and content is not None
        else None,
    )
    return await filtered(decider, subject, resource, preview)


@router.get("/assignments/{assignment_id}/quotes", response_model=None)
async def list_quotes(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The issued quotes of an assignment, newest first."""
    resource = Resource.assignment(assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    await get_assignment(db, assignment_id)
    bundles = await quote_views.quotes_of_assignment(db, assignment_id)
    value = QuoteListOut(
        may_manage=bool(await decide(decider, subject, Action.ISSUE_QUOTE, resource)),
        quotes=[QuoteSummaryOut(**summary_fields(b)) for b in bundles],
    )
    return await filtered(decider, subject, resource, value)


@router.post(
    "/assignments/{assignment_id}/quotes",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def issue_quote(
    assignment_id: UUID,
    body: IssueQuoteIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Issue a quote: freeze the budget as it is now."""
    resource = Resource.assignment(assignment_id)
    await require(decider, subject, Action.ISSUE_QUOTE, resource)
    try:
        quote = await quotes.issue_quote(
            db,
            assignment_id,
            actor=person,
            valid_until=body.valid_until,
            conditions=(body.conditions or "").strip() or None,
        )
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    bundle = await quote_views.quote_bundle(db, quote.id)
    value = QuoteDetailOut(
        **summary_fields(bundle), content=content_from_snapshot(quote.snapshot)
    )
    return await filtered(
        decider, subject, Resource.quote(quote.id, assignment_id), value
    )


@router.get("/quotes/{quote_id}", response_model=None)
async def get_quote(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One issued quote with its frozen content and its decision."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    bundle = await quote_views.quote_bundle(db, quote.id)
    value = QuoteDetailOut(
        **summary_fields(bundle), content=content_from_snapshot(quote.snapshot)
    )
    return await filtered(decider, subject, resource, value)


@router.get("/quotes/{quote_id}/document", response_class=HTMLResponse)
async def quote_document(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    download: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """The quote as a print-ready page, rendered from the frozen snapshot."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    await require(
        decider, subject, Action.READ, resource, DataClass.ASSIGNMENT_FINANCIAL
    )
    return await document_response(db, quote, download=download)


async def document_response(
    db: AsyncSession, quote: Quote, *, download: bool
) -> HTMLResponse:
    context = await quote_views.document_context(db, quote)
    headers = dict(DOCUMENT_HEADERS)
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="offerte-{quote.issued_at:%Y%m%d}-{quote.id}.html"'
        )
    return HTMLResponse(render_quote_html(quote.snapshot, context), headers=headers)


@router.get("/quotes/{quote_id}/invitations", response_model=None)
async def list_invitations(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Who was invited to sign this quote. For whoever manages the assignment."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    await require(decider, subject, Action.ISSUE_QUOTE, resource)
    invitations = await quote_views.invitations_of_quote(db, quote.id)
    value = InvitationListOut(
        invitations=[
            InvitationOut(
                id=i.id,
                email=i.email,
                created_at=i.created_at,
                expires_at=i.expires_at,
                used_at=i.used_at,
            )
            for i in invitations
        ]
    )
    return await filtered(decider, subject, resource, value)


@router.post(
    "/quotes/{quote_id}/invitations",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def invite_signer(
    quote_id: UUID,
    body: InviteSignerIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Invite someone at the client to sign this quote through a signing link."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    await require(decider, subject, Action.ISSUE_QUOTE, resource)
    invitation = await quotes.invite_signer(
        db, quote.id, body.email, actor=person, expires_at=body.expires_at
    )
    await db.refresh(invitation)
    value = InvitationOut(
        id=invitation.id,
        email=invitation.email,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        used_at=invitation.used_at,
    )
    return await filtered(decider, subject, resource, value)


@router.post(
    "/quotes/{quote_id}/acceptance/uploaded-pdf",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def record_uploaded_acceptance(
    quote_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    file: UploadFile = File(...),
    signer_name: str = Form(..., max_length=255),
    signer_email: str = Form(..., max_length=320),
    signer_function: str | None = Form(default=None, max_length=255),
    organisation_name: str | None = Form(default=None, max_length=255),
    signed_at: datetime | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record an acceptance from a signed pdf, with the file attached."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    await require(decider, subject, Action.EDIT, resource, DataClass.ASSIGNMENT_BASIC)
    # Read one byte past the limit, so a file that is too large is refused
    # without loading all of it.
    content = await file.read(stored_documents.MAX_DOCUMENT_BYTES + 1)
    await quote_views.accept_with_uploaded_pdf(
        db,
        quote.id,
        actor=person,
        content=content,
        filename=file.filename,
        content_type=file.content_type,
        signer_name=signer_name,
        signer_email=signer_email,
        signer_function=signer_function,
        organisation_name=organisation_name,
        signed_at=signed_at,
    )
    bundle = await quote_views.quote_bundle(db, quote.id)
    value = QuoteSummaryOut(**summary_fields(bundle))
    return await filtered(decider, subject, resource, value)


@router.get("/quotes/{quote_id}/acceptance/document")
async def acceptance_document(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The signed pdf that was recorded with the acceptance."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    await require(
        decider, subject, Action.READ, resource, DataClass.ASSIGNMENT_FINANCIAL
    )
    bundle = await quote_views.quote_bundle(db, quote.id)
    document_id = (
        stored_documents.parse_document_ref(bundle.acceptance.document_ref)
        if bundle.acceptance is not None
        else None
    )
    if document_id is None:
        raise NotFoundError("Getekend document", quote_id)
    document = await stored_documents.load_document(db, document_id)
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/quotes/{quote_id}/rejection",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def record_rejection(
    quote_id: UUID,
    body: RecordRejectionIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record that the client rejected the quote outside grip."""
    quote, resource = await visible_quote(db, decider, subject, quote_id)
    await require(decider, subject, Action.EDIT, resource, DataClass.ASSIGNMENT_BASIC)
    await quotes.reject_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        actor=person,
        reason=(body.reason or "").strip() or None,
    )
    bundle = await quote_views.quote_bundle(db, quote.id)
    value = QuoteSummaryOut(**summary_fields(bundle))
    return await filtered(decider, subject, resource, value)
