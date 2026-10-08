"""Organisations: search, read, add by hand, and the sync with the register."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from grip.access import BEHEERDER, Action, DataClass, Resource, build_response
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import CurrentPerson, require_function
from grip.core.database import async_session
from grip.models.organisation import (
    SOURCE_MANUAL,
    SOURCE_REGISTRY,
    Organisation,
    OrganisationSyncRun,
)
from grip.models.person import Person
from grip.schema.organisations import (
    OrganisationCreate,
    OrganisationOut,
    OrganisationPage,
    OrganisationSyncRunOut,
    OrganisationSyncStatus,
    OrganisationTypeCount,
    OrganisationUpdate,
)
from grip.services import assignments as assignment_service
from grip.services import organisations as service
from grip.services.organisations import OrganisationHit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organisations", tags=["organisations"])

_CLASSES = frozenset({DataClass.ASSIGNMENT_BASIC})


def _out(hit: OrganisationHit) -> OrganisationOut:
    o = hit.organisation
    return OrganisationOut(
        id=o.id,
        name=o.name,
        label=o.display_name,
        abbreviation=o.abbreviation,
        abbreviations=list(o.abbreviations or []),
        organisation_types=list(o.organisation_types or []),
        main_type=o.main_type,
        source=o.source,
        parent_id=o.parent_id,
        path=list(hit.path),
        path_label=hit.path_label,
        tooi_uri=o.tooi_uri,
        unit_key=o.unit_key,
        instance_uri=o.instance_uri,
        source_url=o.source_url,
        end_date=o.end_date,
    )


async def _one(db: DbSession, organisation: Organisation) -> dict[str, Any]:
    (hit,) = await service.with_paths(db, [organisation])
    return build_response(_out(hit), _CLASSES)


def _run_out(run: OrganisationSyncRun) -> OrganisationSyncRunOut:
    return OrganisationSyncRunOut(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        source_url=run.source_url,
        result=run.result or {},
        error=run.error,
    )


# Every person of the instance may search and read: who the government's
# organisations are is public, and a manual one is class A like the rest.
@router.get("", response_model=None)
async def search_organisations(
    _person: CurrentPerson,
    db: DbSession,
    q: Annotated[str, Query(max_length=200)] = "",
    type: Annotated[str | None, Query(max_length=100)] = None,  # noqa: A002
    source: Annotated[str | None, Query(pattern="^(registry|manual)$")] = None,
    include_ended: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = 20,
) -> dict[str, Any]:
    result = await service.search_organisations(
        db,
        query=q,
        organisation_type=type,
        source=source,
        include_ended=include_ended,
        page=page,
        page_size=page_size,
    )
    return build_response(
        OrganisationPage(
            items=[_out(hit) for hit in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        ),
        _CLASSES,
    )


@router.get("/types", response_model=list[OrganisationTypeCount])
async def organisation_types(
    _person: CurrentPerson, db: DbSession
) -> list[OrganisationTypeCount]:
    return [
        OrganisationTypeCount(name=name, count=count)
        for name, count in await service.type_counts(db)
    ]


# The register answers slowly: fetching the export takes minutes, longer
# than a browser or a proxy waits for one request. A run started from the
# screen therefore continues in the background and the screen asks for the
# status. One run at a time per process.
_background: dict[str, Any] = {"task": None, "since": None}


def _is_running() -> bool:
    task = _background["task"]
    return task is not None and not task.done()


async def _run_in_background(actor_id: UUID) -> None:
    try:
        async with async_session() as db:
            actor = await db.get(Person, actor_id)
            await service.run_registry_sync(db, actor=actor)
            await db.commit()
    except Exception:
        logger.exception("Organisation sync failed unexpectedly")


async def _status(db: DbSession) -> OrganisationSyncStatus:
    counts = dict(
        (
            await db.execute(
                select(Organisation.source, func.count()).group_by(Organisation.source)
            )
        ).all()
    )
    last = await service.last_sync_run(db)
    running = _is_running()
    return OrganisationSyncStatus(
        running=running,
        running_since=_background["since"] if running else None,
        last_run=_run_out(last) if last else None,
        registry_organisations=counts.get(SOURCE_REGISTRY, 0),
        manual_organisations=counts.get(SOURCE_MANUAL, 0),
    )


@router.get("/sync", response_model=OrganisationSyncStatus)
async def sync_status(
    db: DbSession,
    _beheerder: Person = Depends(require_function(BEHEERDER)),
) -> OrganisationSyncStatus:
    """Whether a run is under way, the last run, and the number of organisations."""
    return await _status(db)


@router.post("/sync", response_model=OrganisationSyncStatus)
async def run_sync(
    response: Response,
    db: DbSession,
    wait: bool = False,
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> OrganisationSyncStatus:
    """Fetch the public register and bring the list in line with it.

    Answers 202 at once and runs in the background; ask ``GET /sync`` for the
    outcome. With ``wait=true`` the run happens within the request and the
    answer holds its result. A run that failed is recorded like any other:
    its status and error say what happened.
    """
    if wait:
        await service.run_registry_sync(db, actor=beheerder)
        return await _status(db)
    if not _is_running():
        _background["since"] = datetime.now(UTC)
        _background["task"] = asyncio.create_task(_run_in_background(beheerder.id))
    response.status_code = status.HTTP_202_ACCEPTED
    return await _status(db)


@router.get("/{organisation_id}", response_model=None)
async def get_organisation(
    organisation_id: UUID, _person: CurrentPerson, db: DbSession
) -> dict[str, Any]:
    return await _one(db, await service.get_organisation(db, organisation_id))


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_organisation(
    body: OrganisationCreate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    """Add an organisation by hand, for a party the register does not hold."""
    if BEHEERDER not in access.subject.functions:
        await access.require(Action.CREATE_ASSIGNMENT, Resource.assignment())
    if body.tooi_uri:
        # A counterparty registered by its identifiers, as before.
        organisation = await assignment_service.upsert_organisation(
            db,
            name=body.name.strip(),
            tooi_uri=body.tooi_uri,
            unit_key=body.unit_key or None,
            instance_uri=body.instance_uri or None,
        )
    else:
        organisation = await service.create_manual_organisation(
            db,
            name=body.name,
            parent_id=body.parent_id,
            instance_uri=body.instance_uri,
            actor=person,
        )
    return await _one(db, organisation)


@router.patch("/{organisation_id}", response_model=None)
async def update_organisation(
    organisation_id: UUID,
    body: OrganisationUpdate,
    db: DbSession,
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> dict[str, Any]:
    """Change what grip owns: of a register organisation only the instance URI."""
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Er is niets om te wijzigen",
        )
    organisation = await service.update_organisation(
        db, organisation_id, changes, actor=beheerder
    )
    return await _one(db, organisation)
