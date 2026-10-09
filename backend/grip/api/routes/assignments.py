"""Assignments: list, detail, roles, status."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from grip.access import (
    Action,
    DataClass,
    Resource,
    build_response,
    schema_classes,
)
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core import clock
from grip.core.auth import CurrentPerson
from grip.schema.assignments import (
    AssignmentCreate,
    AssignmentDetailOut,
    AssignmentPermissionsOut,
    AssignmentSummaryOut,
    AssignmentUpdate,
    PersonOptionOut,
    RoleHolderOut,
    RoleIn,
    TransitionIn,
)
from grip.services import assignment_views as views
from grip.services import assignments as service
from grip.services import internal_judges
from grip.services.phase import Phase

router = APIRouter(tags=["assignments"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
_SUMMARY_CLASSES = schema_classes(AssignmentSummaryOut)
_DETAIL_CLASSES = schema_classes(AssignmentDetailOut)


def _summary_fields(
    row: views.AssignmentRow, budgeted_cents: int | None = None
) -> dict[str, Any]:
    """The fields of a summary.

    ``budgeted_cents`` is what a potential assignment without a quote is
    worth; the caller computes it only for whoever may see money.
    """
    a = row.assignment
    owner = row.owner
    shared_at = a.shared_at
    pipeline_cents: int | None = None
    pipeline_source: str | None = None
    if row.phase is Phase.POTENTIAL:
        if row.latest_quote_cents is not None:
            pipeline_cents, pipeline_source = row.latest_quote_cents, "quote"
        elif budgeted_cents is not None:
            pipeline_cents, pipeline_source = budgeted_cents, "budget"
    return {
        "version": a.version,
        "id": a.id,
        "uri": a.uri,
        "name": a.name,
        "kind": a.kind,
        "status": a.status,
        "phase": row.phase.value,
        "status_since": clock.local_date(row.status_since)
        if row.status_since
        else None,
        "shared_with_client_at": clock.local_date(shared_at) if shared_at else None,
        "client_organisation_id": a.client_organisation_id,
        "client_name": row.client_name,
        "start_date": a.start_date,
        "end_date": a.end_date,
        "owner_name": owner.person_name if owner else None,
        "quoted_amount_cents": a.quoted_amount_cents,
        "pipeline_amount_cents": pipeline_cents,
        "pipeline_amount_source": pipeline_source,
    }


async def _detail(row: views.AssignmentRow, access: RequestAccess) -> dict[str, Any]:
    a = row.assignment
    resource = Resource.assignment(a.id)
    edit_basic = await access.may(Action.EDIT, resource, A)
    me = access.subject.person_id
    relations = [r.role for r in row.roles if me is not None and r.person_id == me]
    if not relations and a.id in await access.own_assignment_ids():
        relations = ["member"]
    if not relations:
        # No relation of their own: they read it from a function in grip.
        relations = [f"function:{name}" for name in sorted(access.subject.functions)]
    model = AssignmentDetailOut(
        **_summary_fields(row),
        contractor_organisation_id=a.contractor_organisation_id,
        contractor_name=row.contractor_name,
        parent_assignment_uri=a.parent_assignment_uri,
        context_refs=list(a.context_refs or []),
        client_contact=a.client_contact,
        quote_date=a.quote_date,
        notes=a.notes,
        verbal_agreement_note=a.verbal_agreement_note,
        verbal_agreement_at=clock.local_date(a.verbal_agreement_at)
        if a.verbal_agreement_at
        else None,
        roles=[
            RoleHolderOut(person_id=r.person_id, name=r.person_name, role=r.role)
            for r in row.roles
        ],
        # Only offered to whoever may make the change.
        allowed_transitions=sorted(service.allowed_transitions(a))
        if edit_basic
        else [],
        viewer_relations=sorted(set(relations)),
        permissions=AssignmentPermissionsOut(
            edit_basic=edit_basic,
            manage_roles=await access.may(Action.MANAGE_ROLES, resource),
            edit_financial=await access.may(Action.EDIT, resource, B),
            edit_staffing=await access.may(Action.EDIT, resource, DataClass.STAFFING),
            read_financial=await access.may(Action.READ, resource, B),
            read_staffing=await access.may(Action.READ, resource, DataClass.STAFFING),
            read_roster=await access.may(
                Action.READ, resource, DataClass.STAFFING_ROSTER
            ),
        ),
    )
    return build_response(model, await access.classes(resource, _DETAIL_CLASSES))


@router.get("/assignments", response_model=None)
async def list_assignments(
    access: RequestAccess,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    """Every assignment for whoever reads them all; otherwise the own ones."""
    if await access.may(Action.READ, Resource.assignment(), A):
        rows = await views.assignment_rows(db, status=status_filter)
    else:
        rows = await views.assignment_rows(
            db, status=status_filter, only_ids=await access.own_assignment_ids()
        )
    readable = []
    for row in rows:
        permitted = await access.classes(
            Resource.assignment(row.assignment.id), _SUMMARY_CLASSES
        )
        if A in permitted:
            readable.append((row, permitted))
    # A potential assignment without a quote shows its budget instead.
    budgeted = await views.budgeted_totals(
        db,
        [
            row.assignment.id
            for row, permitted in readable
            if B in permitted
            and row.phase is Phase.POTENTIAL
            and row.latest_quote_cents is None
        ],
    )
    items = [
        build_response(
            AssignmentSummaryOut(
                **_summary_fields(row, budgeted.get(row.assignment.id))
            ),
            permitted,
        )
        for row, permitted in readable
    ]
    return {
        "items": items,
        "can_create": await access.may(Action.CREATE_ASSIGNMENT, Resource.assignment()),
    }


@router.post("/assignments", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    body: AssignmentCreate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    await access.require(Action.CREATE_ASSIGNMENT, Resource.assignment())
    assignment = await service.create_assignment(
        db,
        name=body.name.strip(),
        actor=person,
        kind=body.kind,
        client_organisation_id=body.client_organisation_id,
        client_contact=body.client_contact,
        start_date=body.start_date,
        end_date=body.end_date,
        notes=body.notes,
        context_refs=body.context_refs,
        owner_id=body.owner_id,
    )
    return await _detail(await views.assignment_row(db, assignment.id), access)


@router.get("/person-options", response_model=None)
async def list_person_options(
    access: RequestAccess,
    db: DbSession,
    judging: bool = Query(default=False, alias="oordeel"),
) -> dict[str, Any]:
    """Names to pick from when naming a manager or staffing a line.

    With ``oordeel`` the list is who can be asked to advise, approve or
    review something internal: people with an account who are not in grip
    for a client-side right only.
    """
    await access.require(Action.READ, Resource.person(), DataClass.STAFFING_ROSTER)
    permitted = frozenset({DataClass.STAFFING_ROSTER})
    if judging:
        return {
            "items": [
                build_response(PersonOptionOut(id=person_id, name=name), permitted)
                for person_id, name in await internal_judges.judge_options(db)
            ]
        }
    return {
        "items": [
            build_response(
                PersonOptionOut(id=p.person_id, name=p.name, starts_on=p.starts_on),
                permitted,
            )
            for p in await views.person_options(db)
        ]
    }


@router.get("/assignments/{assignment_id}", response_model=None)
async def get_assignment(
    assignment_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    await access.require(
        Action.READ, Resource.assignment(assignment_id), A, hide_existence=True
    )
    return await _detail(await views.assignment_row(db, assignment_id), access)


@router.patch("/assignments/{assignment_id}", response_model=None)
async def update_assignment(
    assignment_id: UUID,
    body: AssignmentUpdate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    changes = body.model_dump(exclude_unset=True)
    if "quoted_amount_cents" in changes:
        await access.require(Action.EDIT, resource, B)
    if set(changes) - {"quoted_amount_cents"}:
        await access.require(Action.EDIT, resource, A)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
    if changes:
        await service.update_assignment(db, assignment_id, actor=person, **changes)
    return await _detail(await views.assignment_row(db, assignment_id), access)


@router.post("/assignments/{assignment_id}/transition", response_model=None)
async def transition_assignment(
    assignment_id: UUID,
    body: TransitionIn,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.EDIT, resource, A)
    await service.transition(
        db, assignment_id, body.target, actor=person, reason=body.reason
    )
    return await _detail(await views.assignment_row(db, assignment_id), access)


@router.put("/assignments/{assignment_id}/roles/{person_id}", response_model=None)
async def set_role(
    assignment_id: UUID,
    person_id: UUID,
    body: RoleIn,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.MANAGE_ROLES, resource)
    await service.set_assignment_role(
        db,
        assignment_id,
        person_id,
        body.role,
        actor=person,
        as_beheerder=not await access.may(Action.EDIT, resource, A),
    )
    access.forget()
    return await _detail(await views.assignment_row(db, assignment_id), access)


@router.delete("/assignments/{assignment_id}/roles/{person_id}", response_model=None)
async def remove_role(
    assignment_id: UUID,
    person_id: UUID,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.MANAGE_ROLES, resource)
    await service.remove_assignment_role(
        db,
        assignment_id,
        person_id,
        actor=person,
        as_beheerder=not await access.may(Action.EDIT, resource, A),
    )
    # Whoever removed the own role may no longer read the assignment.
    access.forget()
    if not await access.may(Action.READ, resource, A):
        return {"removed": True}
    return await _detail(await views.assignment_row(db, assignment_id), access)
