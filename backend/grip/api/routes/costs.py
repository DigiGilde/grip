"""Cost items, their invoice lines, and which budget lines cover them.

All of it is class B. A cost item is not tied to one assignment: it is seen
and changed by whoever manages an assignment whose budget covers it, and by
the beheerder. Until a cost item has coverage nobody manages it through an
assignment; its creator does. The access model decides all of this.

Coverage is a commitment of a budget line, so setting or changing it asks
for edit rights on the assignment of that line.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import (
    Action,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    permitted_classes,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.reference_support import may
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.schema.costs import (
    AttachmentOut,
    BudgetLineOptionOut,
    CostItemCreate,
    CostItemOut,
    CostItemUpdate,
    CoverageOut,
    CoverageUpdate,
    InvoiceLineCreate,
    InvoiceLineOut,
    InvoiceLineUpdate,
)
from grip.services import cost_overview, costs, invoice_lines, stored_documents
from grip.services.cost_overview import CostItemOverview

router = APIRouter(prefix="/costs", tags=["costs"])

_FIN = DataClass.ASSIGNMENT_FINANCIAL
_COLLECTION = Resource.cost_item()
YearQuery = Annotated[int | None, Query(ge=2000, le=2100)]


def _resource(overview: CostItemOverview) -> Resource:
    return Resource.cost_item(overview.item.id)


class _AssignmentRights:
    """Read and edit rights on class B per assignment, asked once each."""

    def __init__(self, decider: Decider, subject: Subject) -> None:
        self._decider = decider
        self._subject = subject
        self._cache: dict[tuple[Action, UUID], bool] = {}

    async def _ask(self, action: Action, assignment_id: UUID) -> bool:
        key = (action, assignment_id)
        if key not in self._cache:
            self._cache[key] = await may(
                self._decider,
                self._subject,
                action,
                Resource.assignment(assignment_id),
                _FIN,
            )
        return self._cache[key]

    async def read(self, assignment_id: UUID) -> bool:
        return await self._ask(Action.READ, assignment_id)

    async def edit(self, assignment_id: UUID) -> bool:
        return await self._ask(Action.EDIT, assignment_id)


async def _item_out(
    decider: Decider,
    subject: Subject,
    overview: CostItemOverview,
    rights: _AssignmentRights,
) -> dict[str, Any] | None:
    """The cost item as the subject may see it; ``None`` when not at all."""
    resource = _resource(overview)
    permitted = await permitted_classes(
        decider, subject, resource, schema_classes(CostItemOut)
    )
    if _FIN not in permitted:
        return None

    coverages: list[CoverageOut] = []
    hidden = Decimal(0)
    for line in overview.coverages:
        # A share covered by an assignment the asker may not see counts in
        # the totals, without saying which assignment it is.
        if not await rights.read(line.assignment_id):
            hidden += line.pct
            continue
        coverages.append(
            CoverageOut(
                budget_line_id=line.budget_line_id,
                budget_line_description=line.budget_line_description,
                assignment_id=line.assignment_id,
                assignment_name=line.assignment_name,
                pct=line.pct,
                amount_cents=line.amount_cents,
                may_edit=await rights.edit(line.assignment_id),
            )
        )
    item = overview.item
    value = CostItemOut(
        id=item.id,
        description=item.description,
        budgeted_cents=item.budgeted_cents,
        forecast_cents=overview.forecast_cents,
        actual_cents=overview.actual_cents,
        estimate_cents=overview.estimate_cents,
        variance_cents=overview.variance_cents,
        covered_cents=overview.covered_cents,
        uncovered_cents=overview.uncovered_cents,
        pct_total=overview.pct_total,
        hidden_coverage_pct=hidden,
        invoice_lines=[
            InvoiceLineOut(
                id=line.id,
                reference=line.reference,
                description=line.description,
                kind=line.kind,
                amount_cents=line.amount_cents,
                period=line.period,
                attachments=[
                    AttachmentOut(
                        id=document.id,
                        filename=document.filename,
                        content_type=document.content_type,
                        size_bytes=document.size_bytes,
                        uploaded_at=document.created_at,
                        uploaded_by_name=overview.uploader_names.get(
                            document.uploaded_by_id
                        )
                        if document.uploaded_by_id
                        else None,
                    )
                    for document in overview.attachments.get(line.id, ())
                ],
            )
            for line in overview.invoice_lines
        ],
        coverages=coverages,
        may_edit=await may(decider, subject, Action.EDIT, resource, _FIN),
    )
    return build_response(value, permitted)


async def _overview(
    db: AsyncSession, cost_item_id: UUID, year: int | None = None
) -> CostItemOverview:
    return (
        await cost_overview.cost_item_overviews(
            db, cost_item_id=cost_item_id, year=year
        )
    )[0]


async def _one(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    cost_item_id: UUID,
    year: int | None = None,
) -> dict[str, Any]:
    overview = await _overview(db, cost_item_id, year)
    item = await _item_out(
        decider, subject, overview, _AssignmentRights(decider, subject)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Niet gevonden")
    return item


async def _require_edit(
    db: AsyncSession, decider: Decider, subject: Subject, cost_item_id: UUID
) -> None:
    overview = await _overview(db, cost_item_id)
    resource = _resource(overview)
    # Someone who may not even see the item learns nothing about it.
    await require(decider, subject, Action.READ, resource, _FIN, hide_existence=True)
    await require(decider, subject, Action.EDIT, resource, _FIN)


@router.get("", response_model=None)
async def list_cost_items(
    subject: CurrentSubject,
    decider: AccessDecider,
    year: YearQuery = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The cost items the asker may see.

    With a year only invoice lines of that year count, in the forecast and
    in the coverage amounts.
    """
    rights = _AssignmentRights(decider, subject)
    items: list[dict[str, Any]] = []
    for overview in await cost_overview.cost_item_overviews(db, year=year):
        item = await _item_out(decider, subject, overview, rights)
        if item is not None:
            items.append(item)
    return {
        "items": items,
        "year": year,
        "may_create": await may(decider, subject, Action.EDIT, _COLLECTION, _FIN),
    }


@router.get("/coverage-options", response_model=None)
async def list_coverage_options(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The budget lines the asker may let cover a cost item."""
    rights = _AssignmentRights(decider, subject)
    items: list[dict[str, Any]] = []
    for option in await cost_overview.budget_line_options(db):
        if not await rights.edit(option.assignment_id):
            continue
        value = BudgetLineOptionOut(
            budget_line_id=option.budget_line_id,
            description=option.description,
            kind=option.kind,
            assignment_id=option.assignment_id,
            assignment_name=option.assignment_name,
        )
        items.append(build_response(value, {_FIN}))
    return {"items": items}


@router.get("/{cost_item_id}", response_model=None)
async def get_cost_item(
    cost_item_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    year: YearQuery = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _one(db, decider, subject, cost_item_id, year)


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_cost_item(
    body: CostItemCreate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require(decider, subject, Action.EDIT, _COLLECTION, _FIN)
    item = await costs.create_cost_item(
        db,
        description=body.description,
        budgeted_cents=body.budgeted_cents,
        actor=actor,
    )
    return await _one(db, decider, subject, item.id)


@router.patch("/{cost_item_id}", response_model=None)
async def update_cost_item(
    cost_item_id: UUID,
    body: CostItemUpdate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_edit(db, decider, subject, cost_item_id)
    await costs.update_cost_item(
        db,
        cost_item_id,
        description=body.description,
        budgeted_cents=body.budgeted_cents,
        actor=actor,
    )
    return await _one(db, decider, subject, cost_item_id)


@router.post(
    "/{cost_item_id}/invoice-lines",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def add_invoice_line(
    cost_item_id: UUID,
    body: InvoiceLineCreate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a realised or estimated amount on the cost item."""
    await _require_edit(db, decider, subject, cost_item_id)
    line = await costs.add_invoice_line(
        db,
        cost_item_id,
        kind=body.kind,
        amount_cents=body.amount_cents,
        reference=body.reference,
        description=body.description,
        period=body.period,
        actor=actor,
    )
    item = await _one(db, decider, subject, cost_item_id)
    # So the caller can attach the invoice itself to the line it just made.
    return {**item, "created_invoice_line_id": str(line.id)}


@router.patch("/{cost_item_id}/invoice-lines/{invoice_line_id}", response_model=None)
async def update_invoice_line(
    cost_item_id: UUID,
    invoice_line_id: UUID,
    body: InvoiceLineUpdate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Correct an invoice line, for example a typo in the amount."""
    await _require_edit(db, decider, subject, cost_item_id)
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    # Kind and amount cannot be cleared; null means "leave as it is".
    for name in ("kind", "amount_cents"):
        if name in changes and changes[name] is None:
            del changes[name]
    await invoice_lines.update_invoice_line(
        db, cost_item_id, invoice_line_id, actor=actor, changes=changes
    )
    return await _one(db, decider, subject, cost_item_id)


@router.delete("/{cost_item_id}/invoice-lines/{invoice_line_id}", response_model=None)
async def delete_invoice_line(
    cost_item_id: UUID,
    invoice_line_id: UUID,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete an invoice line, with the documents attached to it."""
    await _require_edit(db, decider, subject, cost_item_id)
    await invoice_lines.delete_invoice_line_with_attachments(
        db, cost_item_id, invoice_line_id, actor=actor
    )
    return await _one(db, decider, subject, cost_item_id)


_ATTACHMENTS = "/{cost_item_id}/invoice-lines/{invoice_line_id}/attachments"


@router.post(_ATTACHMENTS, response_model=None, status_code=status.HTTP_201_CREATED)
async def add_attachment(
    cost_item_id: UUID,
    invoice_line_id: UUID,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Attach the received invoice (pdf, scan, photo or e-invoice) to a line."""
    await _require_edit(db, decider, subject, cost_item_id)
    # One byte past the limit, so a file that is too large is refused
    # without loading all of it.
    content = await file.read(stored_documents.MAX_DOCUMENT_BYTES + 1)
    await invoice_lines.add_attachment(
        db,
        cost_item_id,
        invoice_line_id,
        content=content,
        filename=file.filename,
        content_type=file.content_type,
        actor=actor,
    )
    return await _one(db, decider, subject, cost_item_id)


@router.get(_ATTACHMENTS + "/{document_id}", response_model=None)
async def download_attachment(
    cost_item_id: UUID,
    invoice_line_id: UUID,
    document_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The attached file. Access follows the cost item it belongs to."""
    overview = await _overview(db, cost_item_id)
    await require(
        decider, subject, Action.READ, _resource(overview), _FIN, hide_existence=True
    )
    document = await invoice_lines.get_attachment(
        db, cost_item_id, invoice_line_id, document_id, with_content=True
    )
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers=stored_documents.download_headers(document),
    )


@router.delete(_ATTACHMENTS + "/{document_id}", response_model=None)
async def remove_attachment(
    cost_item_id: UUID,
    invoice_line_id: UUID,
    document_id: UUID,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete an attachment: the file itself is removed, an audit row is kept."""
    await _require_edit(db, decider, subject, cost_item_id)
    await invoice_lines.remove_attachment(
        db, cost_item_id, invoice_line_id, document_id, actor=actor
    )
    return await _one(db, decider, subject, cost_item_id)


@router.put("/{cost_item_id}/coverage/{budget_line_id}", response_model=None)
async def set_coverage(
    cost_item_id: UUID,
    budget_line_id: UUID,
    body: CoverageUpdate,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Let a budget line cover a share of the cost item."""
    overview = await _overview(db, cost_item_id)
    await require(
        decider, subject, Action.READ, _resource(overview), _FIN, hide_existence=True
    )
    assignment_id = await cost_overview.budget_line_assignment(db, budget_line_id)
    await require(
        decider, subject, Action.EDIT, Resource.assignment(assignment_id), _FIN
    )
    await costs.set_coverage(db, cost_item_id, budget_line_id, body.pct, actor=actor)
    return await _one(db, decider, subject, cost_item_id)


@router.delete("/{cost_item_id}/coverage/{budget_line_id}", response_model=None)
async def remove_coverage(
    cost_item_id: UUID,
    budget_line_id: UUID,
    actor: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    overview = await _overview(db, cost_item_id)
    await require(
        decider, subject, Action.READ, _resource(overview), _FIN, hide_existence=True
    )
    assignment_id = await cost_overview.budget_line_assignment(db, budget_line_id)
    await require(
        decider, subject, Action.EDIT, Resource.assignment(assignment_id), _FIN
    )
    await costs.remove_coverage(db, cost_item_id, budget_line_id, actor=actor)
    # Removing the last coverage can take the item out of the asker's view,
    # so there is nothing to return.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
