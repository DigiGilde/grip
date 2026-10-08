"""Counterparty organisations: the minimal list needed to pick a client."""

from typing import Any

from fastapi import APIRouter, status

from grip.access import Action, DataClass, Resource, build_response
from grip.api.assignment_support import DbSession, RequestAccess
from grip.schema.organisations import OrganisationCreate, OrganisationOut
from grip.services import assignment_views as views
from grip.services import assignments as service

router = APIRouter(prefix="/organisations", tags=["organisations"])

_CLASSES = frozenset({DataClass.ASSIGNMENT_BASIC})


def _out(organisation: Any) -> dict[str, Any]:
    return build_response(
        OrganisationOut(
            id=organisation.id,
            name=organisation.name,
            tooi_uri=organisation.tooi_uri,
            unit_key=organisation.unit_key,
            instance_uri=organisation.instance_uri,
        ),
        _CLASSES,
    )


async def _require_reader(access: RequestAccess) -> None:
    # Whoever reads all assignments, or may start one, may see the parties.
    if await access.may(Action.READ, Resource.assignment(), DataClass.ASSIGNMENT_BASIC):
        return
    await access.require(Action.CREATE_ASSIGNMENT, Resource.assignment())


@router.get("", response_model=None)
async def list_organisations(access: RequestAccess, db: DbSession) -> dict[str, Any]:
    await _require_reader(access)
    return {"items": [_out(o) for o in await views.organisations(db)]}


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_organisation(
    body: OrganisationCreate, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    await access.require(Action.CREATE_ASSIGNMENT, Resource.assignment())
    organisation = await service.upsert_organisation(
        db,
        name=body.name.strip(),
        tooi_uri=body.tooi_uri or None,
        unit_key=body.unit_key or None,
        instance_uri=body.instance_uri or None,
    )
    return _out(organisation)
