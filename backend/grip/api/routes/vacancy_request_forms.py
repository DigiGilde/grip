"""The request form of a vacancy as a kept document.

Reading takes what the form itself takes: the staffing class of the
vacancy. Making a form and recording a signed copy take the right to edit
the vacancy.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action
from grip.access.deps import AccessDecider, CurrentSubject, decide
from grip.api.routes.vacancies import (
    _load,
    _load_for_edit,
    _load_for_form,
    _resource,
)
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.services import stored_documents
from grip.services.vacancies import request_forms, service

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


async def _names(db: AsyncSession, documents: list[StoredDocument]) -> dict[UUID, str]:
    names: dict[UUID, str] = {}
    for document in documents:
        person_id = document.uploaded_by_id
        if person_id is not None and person_id not in names:
            person = await db.get(Person, person_id)
            if person is not None:
                names[person_id] = person.name
    return names


def _document(document: StoredDocument, names: dict[UUID, str]) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "file_name": document.filename,
        "sha256": document.sha256,
        "size_bytes": document.size_bytes,
        "made_at": document.created_at.isoformat(),
        "made_by_name": names.get(document.uploaded_by_id)
        if document.uploaded_by_id
        else None,
    }


async def _out(
    db: AsyncSession, decider: Any, subject: Any, vacancy_id: UUID
) -> dict[str, Any]:
    vacancy, assignment_id = await _load(db, decider, subject, vacancy_id)
    standing = await request_forms.standing(db, vacancy)
    names = await _names(db, [*standing.versions, *standing.signed])
    versions = [_document(document, names) for document in standing.versions]
    return {
        "available": await service.has_active_form_template(db),
        # A vacancy that is filled, withdrawn or rejected gets no new form.
        "may_make": vacancy.status not in request_forms.CLOSED
        and bool(
            await decide(
                decider, subject, Action.EDIT, _resource(vacancy, assignment_id)
            )
        ),
        # What the vacancy lacks before a form can be made; empty when it can.
        "missing": await service.request_missing(db, vacancy),
        # The newest kept form, or null when none was made yet.
        "current": versions[0] if versions else None,
        "earlier": versions[1:],
        # What the vacancy says now that the newest form does not.
        "changed": standing.changed,
        "signed": [_document(document, names) for document in standing.signed],
    }


@router.get("/{vacancy_id}/request-forms", response_model=None)
async def read_request_forms(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The kept request forms of a vacancy and whether the newest still fits."""
    await _load_for_form(db, decider, subject, vacancy_id)
    return await _out(db, decider, subject, vacancy_id)


@router.post(
    "/{vacancy_id}/request-forms",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def make_request_form(
    vacancy_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fill the form of the instance for this vacancy and keep the file."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await request_forms.make(db, vacancy, actor=person)
    return await _out(db, decider, subject, vacancy_id)


@router.post(
    "/{vacancy_id}/request-forms/signed",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def record_signed_form(
    vacancy_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Keep a copy of the form that was completed or signed outside grip."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    content = await file.read(stored_documents.MAX_DOCUMENT_BYTES + 1)
    await request_forms.record_signed(
        db,
        vacancy,
        content=content,
        filename=file.filename,
        content_type=file.content_type,
        actor=person,
    )
    return await _out(db, decider, subject, vacancy_id)


@router.get("/{vacancy_id}/request-forms/{document_id}")
async def read_request_form_file(
    vacancy_id: UUID,
    document_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    download: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The kept file: the same bytes on every view and download."""
    await _load_for_form(db, decider, subject, vacancy_id)
    document = await request_forms.file_of(db, vacancy_id, document_id)
    safe = (
        document.filename.encode("ascii", "ignore").decode("ascii") or "formulier.pdf"
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe}"',
            "Cache-Control": "private, no-store",
            "X-Document-SHA256": document.sha256,
        },
    )
