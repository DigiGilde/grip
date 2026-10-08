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
    WiesProposalAnswer,
    WiesUnavailableError,
    fetch_wies_state,
    is_wies_configured,
)
from grip.integrations.wies.export import build_export
from grip.integrations.wies.reconcile import (
    apply_confirmed,
    load_persons,
    outgoing_states,
    parse_scope,
    propose,
    record_answers,
)
from grip.models.person import Person
from grip.schema.integrations_wies import (
    ReconciliationConfirmation,
    ReconciliationProposal,
    ReconciliationResult,
    WiesProposedColleague,
    WiesProposedColleagues,
)
from grip.services import standing

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


@router.get("/proposed-colleagues", dependencies=[Depends(require_wies_export_key)])
async def proposed_colleagues_for_wies(
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """New colleagues grip proposes to Wies, and hires that fell through.

    A person reaches grip at the moment of hire, before Wies knows them.
    Staff of Wies confirms or declines each proposal there. Only the name,
    the merk, the start date and the person URI leave.
    """
    response.headers["Cache-Control"] = "no-store"
    proposals = [
        WiesProposedColleague(
            person_uri=p.person_uri,
            name=p.name,
            suborganization=p.suborganization,
            start_date=p.start_date,
            state=p.state,  # type: ignore[arg-type]
        )
        for p in await standing.outgoing_proposals(db)
    ]
    return build_response(
        WiesProposedColleagues(
            generated_at=datetime.now(UTC),
            instance_base_uri=settings.INSTANCE_BASE_URI,
            proposals=proposals,
        ),
        EXPORT_CLASSES,
    )


async def _colleagues(
    settings: Settings,
) -> tuple[list[WiesColleague], list[WiesProposalAnswer]]:
    try:
        return await fetch_wies_state(settings)
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
    colleagues, answers = await _colleagues(settings)
    # What staff of Wies decided on proposed colleagues is a fact about Wies,
    # not a change to grip's persons, so it is stored on reading.
    await record_answers(db, answers, actor=_beheerder)
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
        outgoing=await outgoing_states(db),
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
    colleagues, answers = await _colleagues(settings)
    await record_answers(db, answers, actor=beheerder)
    proposals = propose(
        colleagues,
        await load_persons(db),
        suborganizations=parse_scope(settings.WIES_SUBORGANIZATIONS),
    )
    applied = await apply_confirmed(
        db,
        [
            (change.action, change.email, change.person_id)
            for change in confirmation.changes
        ],
        proposals,
        actor=beheerder,
        colleagues=colleagues,
    )
    return ReconciliationResult(applied=applied)
