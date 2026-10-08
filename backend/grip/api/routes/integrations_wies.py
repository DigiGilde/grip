"""The link with Wies: the export Wies pulls, and the reconciliation of persons.

See docs/wies.md. The export is for a machine with a key; the reconciliation
is for the beheerder.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.fields import build_response
from grip.access.machine_deps import require_wies_export_key
from grip.access.types import DataClass
from grip.core.auth import require_function
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.integrations.wies.client import (
    WiesColleague,
    WiesUnavailableError,
    fetch_colleagues,
    is_wies_configured,
)
from grip.integrations.wies.export import build_export
from grip.integrations.wies.reconcile import (
    apply_confirmed,
    load_persons,
    parse_scope,
    propose,
)
from grip.models.person import Person
from grip.schema.integrations_wies import (
    ReconciliationConfirmation,
    ReconciliationProposal,
    ReconciliationResult,
)

router = APIRouter(prefix="/integrations/wies", tags=["integrations"])

# What may leave to Wies. The export schema has no field outside these, and
# building the response through the field filter keeps it that way.
EXPORT_CLASSES = frozenset({DataClass.ASSIGNMENT_BASIC, DataClass.STAFFING})

BEHEERDER = "beheerder"


@router.get("/export", dependencies=[Depends(require_wies_export_key)])
async def export_for_wies(
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Assignments, roles, placements and open roles, for Wies to take over."""
    response.headers["Cache-Control"] = "no-store"
    return build_response(await build_export(db, settings), EXPORT_CLASSES)


async def _colleagues(settings: Settings) -> list[WiesColleague]:
    try:
        return await fetch_colleagues(settings)
    except WiesUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/reconciliation", response_model=ReconciliationProposal)
async def reconciliation_proposal(
    _beheerder: Person = Depends(require_function(BEHEERDER)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReconciliationProposal:
    """What Wies suggests changing in grip's persons. Changes nothing."""
    if not is_wies_configured(settings):
        return ReconciliationProposal(
            configured=False, note="De koppeling met Wies is niet ingesteld."
        )
    colleagues = await _colleagues(settings)
    proposals = propose(
        colleagues,
        await load_persons(db),
        suborganizations=parse_scope(settings.WIES_SUBORGANIZATIONS),
    )
    return ReconciliationProposal(
        configured=True,
        fetched_at=datetime.now(UTC),
        wies_colleagues=len(colleagues),
        proposals=proposals,
    )


@router.post("/reconciliation", response_model=ReconciliationResult)
async def confirm_reconciliation(
    confirmation: ReconciliationConfirmation,
    beheerder: Person = Depends(require_function(BEHEERDER)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReconciliationResult:
    """Apply the changes the beheerder confirmed, as far as Wies still backs them."""
    if not is_wies_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="De koppeling met Wies is niet ingesteld",
        )
    colleagues = await _colleagues(settings)
    proposals = propose(
        colleagues,
        await load_persons(db),
        suborganizations=parse_scope(settings.WIES_SUBORGANIZATIONS),
    )
    applied = await apply_confirmed(
        db,
        [(change.action, change.email) for change in confirmation.changes],
        proposals,
        actor=beheerder,
    )
    return ReconciliationResult(applied=applied)
