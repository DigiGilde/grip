"""The Functiegebouw Rijk: function families, groups and their scales.

Reading is for every person of the instance: it is public information and
a vacancy picks its FGR name from it. Correcting, adding and reloading the
reference file is for the beheerder.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, build_response, decide, schema_classes
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.access.vacancies import function_framework_resource
from grip.core import clock
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.function_framework import FunctionFamily, FunctionGroup
from grip.schema.function_framework import (
    FunctionFamilyCreate,
    FunctionFamilyOut,
    FunctionFamilyUpdate,
    FunctionFrameworkOut,
    FunctionFrameworkSourceOut,
    FunctionGroupCreate,
    FunctionGroupOut,
    FunctionGroupUpdate,
    ReloadOut,
)
from grip.services import function_framework as framework

router = APIRouter(prefix="/function-framework", tags=["function-framework"])

_ALL = frozenset({DataClass.MASTER_DATA})


def _group_out(group: FunctionGroup) -> FunctionGroupOut:
    return FunctionGroupOut(
        id=group.id,
        family_id=group.family_id,
        name=group.name,
        scales=list(group.scales),
        scales_text=framework.describe_scales(list(group.scales)),
        source=group.source,
        source_url=group.source_url,
        valid_to=group.valid_to,
        edited=group.edited_at is not None,
    )


def _family_out(
    family: FunctionFamily, groups: list[FunctionGroup]
) -> FunctionFamilyOut:
    return FunctionFamilyOut(
        id=family.id,
        name=family.name,
        source=family.source,
        source_url=family.source_url,
        valid_to=family.valid_to,
        groups=[_group_out(group) for group in groups],
    )


async def _require_manage(decider: Any, subject: Any) -> None:
    await require(
        decider,
        subject,
        Action.EDIT,
        function_framework_resource(),
        DataClass.MASTER_DATA,
    )


@router.get("", response_model=None)
async def get_function_framework(
    subject: CurrentSubject,
    decider: AccessDecider,
    include_ended: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Families with their groups and scales, and where the list comes from.

    Without ``include_ended`` only what is valid today, which is what a
    vacancy chooses from.
    """
    resource = function_framework_resource()
    await require(decider, subject, Action.READ, resource, DataClass.MASTER_DATA)
    info = framework.reference_info()
    families = await framework.list_families(db, include_ended=include_ended)
    today = clock.today()
    out = FunctionFrameworkOut(
        source=FunctionFrameworkSourceOut(
            name=info.name,
            source_url=info.source_url,
            read_on=info.read_on,
            reference_families=info.families,
            reference_groups=info.groups,
        ),
        families=[
            _family_out(
                family,
                [
                    group
                    for group in family.groups
                    if include_ended or group.is_valid_on(today)
                ],
            )
            for family in families
        ],
        can_manage=bool(
            await decide(decider, subject, Action.EDIT, resource, DataClass.MASTER_DATA)
        ),
    )
    return build_response(out, schema_classes(FunctionFrameworkOut))


@router.post("/reload", response_model=None)
async def reload_reference(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bring the list in line with the reference file that ships with grip.

    Nothing is removed, and a row a beheerder changed is left as it is.
    """
    await _require_manage(decider, subject)
    result = await framework.reload_reference(db, actor=person)
    out = ReloadOut(
        families_created=result.families_created,
        families_updated=result.families_updated,
        groups_created=result.groups_created,
        groups_updated=result.groups_updated,
        groups_kept=result.groups_kept,
    )
    return build_response(out, _ALL)


@router.post("/families", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_family(
    body: FunctionFamilyCreate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manage(decider, subject)
    family = await framework.create_family(db, actor=person, name=body.name)
    return build_response(_family_out(family, []), _ALL)


@router.patch("/families/{family_id}", response_model=None)
async def update_family(
    family_id: UUID,
    body: FunctionFamilyUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manage(decider, subject)
    family = await framework.update_family(
        db, family_id, actor=person, changes=body.model_dump(exclude_unset=True)
    )
    return build_response(_family_out(family, []), _ALL)


@router.post("/groups", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: FunctionGroupCreate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Add a function group that the reference file does not have."""
    await _require_manage(decider, subject)
    group = await framework.create_group(
        db,
        actor=person,
        family_id=body.family_id,
        name=body.name,
        scales=body.scales,
    )
    return build_response(_group_out(group), _ALL)


@router.patch("/groups/{group_id}", response_model=None)
async def update_group(
    group_id: UUID,
    body: FunctionGroupUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Correct a group: its name, scales, family, or the date it ended."""
    await _require_manage(decider, subject)
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "scales", "family_id"):
        if required in changes and changes[required] is None:
            del changes[required]
    group = await framework.update_group(db, group_id, actor=person, changes=changes)
    return build_response(_group_out(group), _ALL)
