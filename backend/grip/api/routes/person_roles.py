"""The roles of a person: read, set by hand, and follow the skills in Wies."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from grip.access import BEHEERDER, Action, DataClass, Resource, build_response
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import require_function
from grip.core.config import Settings, get_settings
from grip.integrations.wies.client import (
    WiesColleague,
    WiesUnavailableError,
    fetch_colleagues,
    is_wies_configured,
)
from grip.models.person import Person
from grip.schema.person_roles import (
    AppliedRoleChange,
    PersonRoleOut,
    PersonRolesOut,
    PersonRolesSet,
    RoleProposalConfirmation,
    RoleProposalList,
    RoleProposalOut,
    RoleProposalResult,
)
from grip.services import person_roles as service
from grip.services.errors import NotFoundError

router = APIRouter(tags=["person-roles"])

C = DataClass.STAFFING
_CLASSES = frozenset({C})


def _out(person_id: UUID, links: list[service.PersonRole]) -> dict[str, Any]:
    return build_response(
        PersonRolesOut(
            person_id=person_id,
            items=[
                PersonRoleOut(
                    role_id=link.role.id,
                    name=link.role.name,
                    source=link.source,
                    is_active=link.role.is_active,
                )
                for link in links
            ],
        ),
        _CLASSES,
    )


@router.get("/people/{person_id}/roles", response_model=None)
async def get_person_roles(
    person_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    """The roles of a person. For whoever may see that person's staffing."""
    await access.require(Action.READ, Resource.person(person_id), C, hide_existence=True)
    if await db.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    return _out(person_id, await service.person_role_links(db, person_id))


@router.put("/people/{person_id}/roles", response_model=None)
async def set_person_roles(
    person_id: UUID,
    body: PersonRolesSet,
    db: DbSession,
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> dict[str, Any]:
    """Make the roles of a person exactly this set. A role added here is manual."""
    links = await service.set_person_roles(db, person_id, body.role_ids, actor=beheerder)
    return _out(person_id, links)


async def _colleagues(settings: Settings) -> list[WiesColleague]:
    try:
        return await fetch_colleagues(settings)
    except WiesUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/integrations/wies/role-proposals", response_model=RoleProposalList)
async def role_proposals(
    db: DbSession,
    settings: Settings = Depends(get_settings),
    _beheerder: Person = Depends(require_function(BEHEERDER)),
) -> RoleProposalList:
    """What the skills in Wies suggest changing in people's roles. Changes nothing."""
    if not is_wies_configured(settings):
        return RoleProposalList(
            configured=False, note="De koppeling met Wies is niet ingesteld."
        )
    proposals = await service.current_role_proposals(db, await _colleagues(settings))
    return RoleProposalList(
        configured=True,
        proposals=[RoleProposalOut(**_proposal(p)) for p in proposals],
    )


def _proposal(proposal: service.RoleProposal) -> dict[str, Any]:
    return {
        "action": proposal.action,
        "person_id": proposal.person_id,
        "person_name": proposal.person_name,
        "role_id": proposal.role_id,
        "role_name": proposal.role_name,
        "reason": proposal.reason,
    }


@router.post("/integrations/wies/role-proposals", response_model=RoleProposalResult)
async def confirm_role_proposals(
    confirmation: RoleProposalConfirmation,
    db: DbSession,
    settings: Settings = Depends(get_settings),
    beheerder: Person = Depends(require_function(BEHEERDER)),
) -> RoleProposalResult:
    """Apply the confirmed changes, as far as Wies still backs them."""
    if not is_wies_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="De koppeling met Wies is niet ingesteld",
        )
    proposals = await service.current_role_proposals(db, await _colleagues(settings))
    outcome = await service.apply_role_proposals(
        db,
        [(c.action, c.person_id, c.role_id) for c in confirmation.changes],
        proposals,
        actor=beheerder,
    )
    return RoleProposalResult(
        applied=[
            AppliedRoleChange(
                action=action, person_id=person_id, role_id=role_id, applied=applied
            )
            for (action, person_id, role_id), applied in outcome
        ]
    )
