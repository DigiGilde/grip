"""The role catalogue: search, add, rename, switch off, merge, follow Wies."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from grip.access import BEHEERDER, PLANNER, Action, Resource
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import CurrentPerson, require_function
from grip.core.config import Settings, get_settings
from grip.integrations.wies.client import is_wies_configured
from grip.models.catalogue_role import CatalogueRole, CatalogueRoleSyncRun
from grip.models.person import Person
from grip.schema.catalogue_roles import (
    CatalogueRoleCreate,
    CatalogueRoleList,
    CatalogueRoleMerge,
    CatalogueRoleMergeResult,
    CatalogueRoleOut,
    CatalogueRoleUpdate,
    RoleSyncRunOut,
    RoleSyncStatus,
)
from grip.services import catalogue_roles as service
from grip.services.catalogue_roles import RoleRow

router = APIRouter(prefix="/catalogue-roles", tags=["catalogue-roles"])


def _out(row: RoleRow) -> CatalogueRoleOut:
    role = row.role
    return CatalogueRoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        source=role.source,
        is_active=role.is_active,
        needs_review=role.needs_review,
        usage_count=row.usage_count,
    )


def _run_out(run: CatalogueRoleSyncRun) -> RoleSyncRunOut:
    return RoleSyncRunOut(
        id=run.id,
        finished_at=run.finished_at,
        status=run.status,
        result=run.result or {},
        error=run.error,
    )


async def _may_add(access: RequestAccess) -> bool:
    """Whoever fills in a budget may add a role that is missing.

    Blocking a budget on a missing word is worse than a duplicate that can
    be merged: the role is added as manual and marked for the beheerder.
    """
    functions = access.subject.functions
    if BEHEERDER in functions or PLANNER in functions:
        return True
    if await access.may(Action.CREATE_ASSIGNMENT, Resource.assignment()):
        return True
    return bool(await access.own_assignment_ids())


# Reading is for everyone in the instance: the names of roles are no secret,
# and every screen that shows a budget line shows them.
@router.get("", response_model=CatalogueRoleList)
async def list_roles(
    _person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
    q: Annotated[str, Query(max_length=200)] = "",
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> CatalogueRoleList:
    rows = await service.list_roles(
        db, query=q, include_inactive=include_inactive, limit=limit
    )
    return CatalogueRoleList(
        items=[_out(row) for row in rows],
        can_add=await _may_add(access),
        can_manage=BEHEERDER in access.subject.functions,
    )


async def _sync_status(db: DbSession, settings: Settings) -> RoleSyncStatus:
    last = await service.last_sync_run(db)
    total = (
        await db.execute(select(func.count()).select_from(CatalogueRole))
    ).scalar_one()
    return RoleSyncStatus(
        wies_configured=is_wies_configured(settings),
        last_run=_run_out(last) if last else None,
        roles=total,
        needs_review=await service.review_count(db),
    )


@router.get("/sync", response_model=RoleSyncStatus)
async def sync_status(
    db: DbSession,
    settings: Settings = Depends(get_settings),
    _beheerder: Person = Depends(require_function(BEHEERDER)),
) -> RoleSyncStatus:
    return await _sync_status(db, settings)


@router.post("/sync", response_model=RoleSyncStatus)
async def run_sync(
    db: DbSession,
    settings: Settings = Depends(get_settings),
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> RoleSyncStatus:
    """Take over the skills of Wies. A failed run is recorded and reported."""
    if not is_wies_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="De koppeling met Wies is niet ingesteld",
        )
    await service.run_wies_sync(db, settings, actor=beheerder)
    return await _sync_status(db, settings)


@router.post("", response_model=CatalogueRoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: CatalogueRoleCreate,
    response: Response,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> CatalogueRoleOut:
    """Add a role. An existing name answers 200 with the role that is there."""
    is_beheerder = BEHEERDER in access.subject.functions
    if not is_beheerder and not await _may_add(access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Je kunt hier geen rol toevoegen",
        )
    existing = await service.find_by_name(db, body.name)
    role = await service.create_role(
        db,
        name=body.name,
        description=body.description,
        actor=person,
        needs_review=not is_beheerder,
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
    return _out(await service.with_usage(db, role))


@router.get("/{role_id}", response_model=CatalogueRoleOut)
async def get_role(
    role_id: UUID, _person: CurrentPerson, db: DbSession
) -> CatalogueRoleOut:
    return _out(await service.with_usage(db, await service.get_role(db, role_id)))


@router.patch("/{role_id}", response_model=CatalogueRoleOut)
async def update_role(
    role_id: UUID,
    body: CatalogueRoleUpdate,
    db: DbSession,
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> CatalogueRoleOut:
    """Rename, describe, switch on or off, or mark as reviewed."""
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Er is niets om te wijzigen",
        )
    role = await service.update_role(db, role_id, changes, actor=beheerder)
    return _out(await service.with_usage(db, role))


@router.post("/{role_id}/merge", response_model=CatalogueRoleMergeResult)
async def merge_role(
    role_id: UUID,
    body: CatalogueRoleMerge,
    db: DbSession,
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> CatalogueRoleMergeResult:
    """Merge this role into another: its budget lines move, the role goes."""
    target, moved = await service.merge_roles(
        db, role_id, body.into_id, actor=beheerder
    )
    return CatalogueRoleMergeResult(
        role=_out(await service.with_usage(db, target)),
        budget_lines_rewritten=moved,
    )
