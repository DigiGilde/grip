"""Internal approval of a quote, and the instance settings behind it.

Where the instance is set up for it, a made quote is approved inside the
organisation before it can be offered. The maker asks; a person with the
right "Interne goedkeurder van offertes" approves or sends back. None of
this is visible to the client.

``approval_state`` is the one function that says where a quote stands and
what the reader may do. The routes here use it, and a route that shows a
quote can embed its result.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import (
    Action,
    DataClass,
    Decider,
    Resource,
    ResourceKind,
    Subject,
    build_response,
    decide,
    permitted_classes,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.access.quote_approval import quote_resource
from grip.api.routes.quotes import document_response
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation
from grip.models.quote import (
    APPROVAL_APPROVED,
    APPROVAL_REQUESTED,
    Quote,
    QuoteApproval,
)
from grip.schema.quote_approvals import (
    ApprovalRequestOut,
    ApprovalStateOut,
    ApprovalStatesOut,
    ApproverQuoteOut,
    DecideApprovalIn,
    InstanceSettingOut,
    InstanceSettingsIn,
    InstanceSettingsOut,
    RequestApprovalIn,
    WaitingApprovalOut,
    WaitingApprovalsOut,
)
from grip.schema.quotes import content_from_snapshot
from grip.services import instance_settings, quote_approval, quote_views
from grip.services.errors import NotFoundError

router = APIRouter(tags=["quote-approvals"])

A = DataClass.ASSIGNMENT_BASIC


async def approval_resource(db: AsyncSession, quote: Quote) -> Resource:
    """The quote as a resource, with the fact the approver's reading rule needs."""
    return quote_resource(
        quote.id,
        quote.assignment_id,
        approval_requested=await quote_approval.has_request(db, quote.id),
    )


async def _readable_quote(
    db: AsyncSession, decider: Decider, subject: Subject, quote_id: UUID
) -> tuple[Quote, Resource]:
    """The quote, or 404 when it does not exist or the reader may not know it."""
    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    resource = await approval_resource(db, quote)
    await require(decider, subject, Action.READ, resource, A, hide_existence=True)
    return quote, resource


def _request_out(
    approval: QuoteApproval, names: dict[UUID, str], quote: Quote
) -> ApprovalRequestOut:
    return ApprovalRequestOut(
        id=approval.id,
        status=approval.status,
        requested_at=approval.requested_at,
        requested_by_name=names.get(approval.requested_by_id)
        if approval.requested_by_id
        else None,
        request_note=approval.request_note,
        decided_at=approval.decided_at,
        decided_by_name=names.get(approval.decided_by_id)
        if approval.decided_by_id
        else None,
        decision_note=approval.decision_note,
        self_approved=approval.self_approved,
        for_this_version=approval.quote_hash == quote.snapshot_hash,
    )


async def approval_state(
    db: AsyncSession, decider: Decider, subject: Subject, quote: Quote
) -> ApprovalStateOut:
    """Where a quote stands with internal approval and what the reader may do.

    Class A of the quote: whoever may read the quote may read this.
    """
    state = await quote_approval.state_of(db, quote)
    resource = await approval_resource(db, quote)
    may_request = bool(
        await decide(decider, subject, Action.REQUEST_QUOTE_APPROVAL, resource)
    )
    has_right = bool(
        await decide(decider, subject, Action.DECIDE_QUOTE_APPROVAL, resource)
    )
    current = state.current
    own_request = (
        current is not None
        and current.requested_by_id is not None
        and current.requested_by_id == subject.person_id
    )
    allow_self = bool(await instance_settings.get(db, quote_approval.ALLOW_SELF.key))
    names = await quote_views.person_names(
        db,
        {
            person_id
            for row in state.history
            for person_id in (row.requested_by_id, row.decided_by_id)
            if person_id is not None
        },
    )
    is_open = quote.status == "issued"
    return ApprovalStateOut(
        quote_id=quote.id,
        approval_required=state.requirement.required,
        approval_reason=state.requirement.reason,
        status=state.status,
        may_offer=not state.blocks_offering,
        blocked_message=state.blocked_message,
        approver_available=state.approver_available,
        may_request_approval=may_request and is_open and current is None,
        may_decide_approval=(
            has_right
            and is_open
            and current is not None
            and current.status == APPROVAL_REQUESTED
            and (not own_request or allow_self)
        ),
        may_withdraw=is_open
        and current is not None
        and (
            (current.status == APPROVAL_REQUESTED and may_request)
            or (current.status == APPROVAL_APPROVED and has_right and not state.offered)
        ),
        current=_request_out(current, names, quote) if current is not None else None,
        history=[_request_out(row, names, quote) for row in state.history],
    )


async def _filtered(
    decider: Decider, subject: Subject, resource: Resource, value: Any
) -> dict[str, Any]:
    permitted = await permitted_classes(
        decider, subject, resource, schema_classes(type(value))
    )
    return build_response(value, permitted)


@router.get("/quotes/{quote_id}/approval", response_model=None)
async def get_approval(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Where this quote stands with internal approval."""
    quote, resource = await _readable_quote(db, decider, subject, quote_id)
    value = await approval_state(db, decider, subject, quote)
    return await _filtered(decider, subject, resource, value)


@router.get("/assignments/{assignment_id}/quote-approvals", response_model=None)
async def list_approvals(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The approval state of every quote of an assignment, for the quote list."""
    await require(
        decider,
        subject,
        Action.READ,
        Resource.assignment(assignment_id),
        A,
        hide_existence=True,
    )
    quotes = (
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
    value = ApprovalStatesOut(
        items=[await approval_state(db, decider, subject, quote) for quote in quotes]
    )
    return await _filtered(decider, subject, Resource.assignment(assignment_id), value)


@router.post(
    "/quotes/{quote_id}/approval/request",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def request_approval(
    quote_id: UUID,
    body: RequestApprovalIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ask for internal approval of a made quote."""
    quote, resource = await _readable_quote(db, decider, subject, quote_id)
    await require(decider, subject, Action.REQUEST_QUOTE_APPROVAL, resource)
    await quote_approval.request_approval(db, quote.id, actor=person, note=body.note)
    resource = await approval_resource(db, quote)
    value = await approval_state(db, decider, subject, quote)
    return await _filtered(decider, subject, resource, value)


@router.post(
    "/quotes/{quote_id}/approval/decision",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def decide_approval(
    quote_id: UUID,
    body: DecideApprovalIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve the quote, or send it back to the maker with a note."""
    quote, resource = await _readable_quote(db, decider, subject, quote_id)
    await require(decider, subject, Action.DECIDE_QUOTE_APPROVAL, resource)
    await quote_approval.decide(
        db,
        quote.id,
        approve=body.decision == "approve",
        actor=person,
        quote_hash=body.quote_hash,
        note=body.note,
    )
    value = await approval_state(db, decider, subject, quote)
    return await _filtered(decider, subject, resource, value)


@router.post("/quotes/{quote_id}/approval/withdrawal", response_model=None)
async def withdraw_approval(
    quote_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Take back an open request (the maker) or an approval (the approver).

    An approval can be taken back only while the quote was not offered.
    """
    quote, resource = await _readable_quote(db, decider, subject, quote_id)
    state = await quote_approval.state_of(db, quote)
    approved = state.current is not None and state.current.status == APPROVAL_APPROVED
    await require(
        decider,
        subject,
        Action.DECIDE_QUOTE_APPROVAL if approved else Action.REQUEST_QUOTE_APPROVAL,
        resource,
    )
    await quote_approval.withdraw(db, quote.id, actor=person)
    value = await approval_state(db, decider, subject, quote)
    return await _filtered(decider, subject, resource, value)


# --- for the approver, across assignments ----------------------------------


async def _require_approver(decider: Decider, subject: Subject) -> None:
    await require(
        decider,
        subject,
        Action.DECIDE_QUOTE_APPROVAL,
        Resource(ResourceKind.QUOTE),
    )


async def _names_of(db: AsyncSession, quote: Quote) -> tuple[str, str | None]:
    assignment = await db.get(Assignment, quote.assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", quote.assignment_id)
    client = (
        await db.get(Organisation, assignment.client_organisation_id)
        if assignment.client_organisation_id
        else None
    )
    return assignment.name, client.name if client is not None else None


@router.get("/quote-approvals/waiting", response_model=None)
async def waiting_approvals(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Quotes that wait for the reader's approval, across assignments."""
    await _require_approver(decider, subject)
    allow_self = bool(await instance_settings.get(db, quote_approval.ALLOW_SELF.key))
    rows = await quote_approval.waiting(db)
    names = await quote_views.person_names(
        db, {a.requested_by_id for a, _ in rows if a.requested_by_id is not None}
    )
    items: list[dict[str, Any]] = []
    for approval, quote in rows:
        resource = await approval_resource(db, quote)
        assignment_name, client_name = await _names_of(db, quote)
        own = approval.requested_by_id == subject.person_id
        value = WaitingApprovalOut(
            quote_id=quote.id,
            quote_reference=quote.reference,
            assignment_id=quote.assignment_id,
            assignment_name=assignment_name,
            client_name=client_name,
            requested_at=approval.requested_at,
            requested_by_name=names.get(approval.requested_by_id)
            if approval.requested_by_id
            else None,
            request_note=approval.request_note,
            total_cents=quote.total_cents,
            snapshot_hash=quote.snapshot_hash,
            may_decide=not own or allow_self,
        )
        items.append(await _filtered(decider, subject, resource, value))
    return WaitingApprovalsOut().model_dump() | {"items": items}


async def _approver_quote(
    db: AsyncSession, decider: Decider, subject: Subject, quote_id: UUID
) -> tuple[Quote, Resource]:
    """A quote that was put before an approver, for a holder of the right."""
    await _require_approver(decider, subject)
    quote, resource = await _readable_quote(db, decider, subject, quote_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_FINANCIAL,
        hide_existence=True,
    )
    return quote, resource


@router.get("/quote-approvals/quotes/{quote_id}", response_model=None)
async def approver_quote(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The quote in full, for whoever decides on its approval."""
    quote, resource = await _approver_quote(db, decider, subject, quote_id)
    assignment_name, client_name = await _names_of(db, quote)
    names = await quote_views.person_names(
        db, {quote.issued_by_id} if quote.issued_by_id else set()
    )
    value = ApproverQuoteOut(
        quote_id=quote.id,
        quote_reference=quote.reference,
        assignment_id=quote.assignment_id,
        assignment_name=assignment_name,
        client_name=client_name,
        issued_at=quote.issued_at,
        issued_by_name=names.get(quote.issued_by_id) if quote.issued_by_id else None,
        total_cents=quote.total_cents,
        snapshot_hash=quote.snapshot_hash,
        content=content_from_snapshot(quote.snapshot),
        approval=await approval_state(db, decider, subject, quote),
    )
    return await _filtered(decider, subject, resource, value)


@router.get("/quote-approvals/quotes/{quote_id}/document")
async def approver_quote_document(
    quote_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    download: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The quote as the client will get it, for whoever decides on it."""
    quote, _ = await _approver_quote(db, decider, subject, quote_id)
    return await document_response(db, quote, download=download)


# --- instance settings ------------------------------------------------------


def _settings_out(values: dict[str, Any]) -> InstanceSettingsOut:
    declared = instance_settings.declared()
    return InstanceSettingsOut(
        items=[
            InstanceSettingOut(
                key=key,
                value=value,
                default=declared[key].default,
                label=declared[key].label,
            )
            for key, value in values.items()
        ]
    )


@router.get("/instance-settings", response_model=InstanceSettingsOut)
async def get_instance_settings(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> InstanceSettingsOut:
    """The settings of this instance that the organisation itself changes."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.instance())
    return _settings_out(await instance_settings.get_all(db))


@router.patch("/instance-settings", response_model=InstanceSettingsOut)
async def set_instance_settings(
    body: InstanceSettingsIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> InstanceSettingsOut:
    """Change settings. For the beheerder; every change leaves an audit row."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.instance())
    return _settings_out(
        await instance_settings.set_values(db, body.values, actor=person)
    )
