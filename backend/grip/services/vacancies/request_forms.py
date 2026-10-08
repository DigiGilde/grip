"""The request form of a vacancy as a kept document.

"Maak aanvraagformulier" fills the form of the instance once and keeps the
file with the vacancy: its hash, who made it and when. Every later view and
download gives those bytes. When the vacancy changed since, a new version is
made on request; earlier versions stay. A copy that was completed or signed
outside grip is kept next to them as a document of its own.

The form holds names of colleagues (data class C). It is kept no longer than
the vacancy runs: once the vacancy is filled, withdrawn or rejected the
files are removed after the days the instance sets (ADR 0018).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, record_audit
from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.models.vacancy import TextKind, Vacancy, VacancyStatus
from grip.repositories.vacancy import FormTemplateRepository
from grip.services import instance_settings, stored_documents
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.stored_documents import PDF, DocumentUse
from grip.services.vacancies import form as forms
from grip.services.vacancies import form_setup, service

REQUEST_FORM = DocumentUse(
    owner_kind="vacancy_request_form",
    content_types=frozenset({PDF}),
    accepted_text="Het aanvraagformulier is een pdf.",
)
SIGNED_FORM = DocumentUse(
    owner_kind="vacancy_signed_form",
    content_types=frozenset({PDF}),
    accepted_text="Alleen een pdf-bestand kan worden vastgelegd.",
)

CLOSED = (
    VacancyStatus.filled.value,
    VacancyStatus.withdrawn.value,
    VacancyStatus.rejected.value,
)


def _days(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(
            "Een bewaartermijn is een geheel aantal dagen van nul of meer."
        )
    return value


RETENTION_DAYS = instance_settings.declare(
    "vacancy.request_form_retention_days",
    0,
    _days,
    "Hoeveel dagen het aanvraagformulier blijft bewaard nadat een vacature is "
    "vervuld, ingetrokken of afgewezen (0 is direct weg)",
)


@dataclass(frozen=True)
class Standing:
    """The kept forms of a vacancy and whether the newest still fits."""

    versions: list[StoredDocument]
    signed: list[StoredDocument]
    # Labels of what the vacancy now says differently from the newest form.
    changed: list[str]


async def _values(db: AsyncSession, vacancy: Vacancy) -> dict[str, Any]:
    motivation = await service.established_text(db, vacancy.id, TextKind.motivation)
    return service.form_values(
        vacancy, motivation=motivation.body if motivation else None
    )


async def _kept(
    db: AsyncSession, use: DocumentUse, vacancy_id: UUID
) -> list[StoredDocument]:
    """Newest first."""
    found = await stored_documents.documents_of(db, use, [vacancy_id])
    return list(reversed(found.get(vacancy_id, [])))


def _field_text(field: dict[str, Any]) -> str:
    value = field.get("/V")
    return "" if value is None else str(value)


async def changed_since(
    db: AsyncSession, vacancy: Vacancy, document: StoredDocument
) -> list[str]:
    """What the vacancy says now that the kept form does not: per piece of
    the vacancy its plain name. Read from the file itself, so it is about
    what the reader of that file sees."""
    template = await FormTemplateRepository(db).active(service.VACANCY_REQUEST_FORM)
    if template is None:
        return []
    kept = await stored_documents.owned_document(
        db, REQUEST_FORM, vacancy.id, document.id, with_content=True
    )
    fields = PdfReader(io.BytesIO(kept.content)).get_fields() or {}
    values = await _values(db, vacancy)
    mapping = forms.parse_mapping(form_setup.usable_mapping(template))
    changed: list[str] = []
    for rule in mapping.fields:
        if rule.name not in fields:
            continue
        value = values.get(rule.source)
        if rule.type == "checkbox":
            expected = rule.on_value if value == rule.equals else "/Off"
            have = _field_text(fields[rule.name]) or "/Off"
            if value is None:
                expected = "/Off"
        else:
            expected = (
                "" if value is None else forms.format_value(value, mapping.date_format)
            )
            have = _field_text(fields[rule.name])
        if have != expected:
            label = form_setup.source_label(rule.source)
            if label not in changed:
                changed.append(label)
    return changed


async def standing(db: AsyncSession, vacancy: Vacancy) -> Standing:
    versions = await _kept(db, REQUEST_FORM, vacancy.id)
    signed = await _kept(db, SIGNED_FORM, vacancy.id)
    changed = await changed_since(db, vacancy, versions[0]) if versions else []
    return Standing(versions=versions, signed=signed, changed=changed)


async def make(
    db: AsyncSession, vacancy: Vacancy, *, actor: Person | None
) -> StoredDocument:
    """Fill the form once and keep it. With a kept form that still fits the
    vacancy nothing new is made."""
    missing = await service.request_missing(db, vacancy)
    if missing:
        raise DomainValidationError(
            "Het aanvraagformulier kan nog niet worden gemaakt. "
            + service.missing_sentence(missing)
        )
    versions = await _kept(db, REQUEST_FORM, vacancy.id)
    if versions and not await changed_since(db, vacancy, versions[0]):
        raise DomainValidationError(
            "Het aanvraagformulier klopt nog met de vacature. Er is niets "
            "veranderd om een nieuwe versie van te maken."
        )
    generated = await service.build_request_form(db, vacancy.id)
    document = await stored_documents.store_document(
        db,
        use=REQUEST_FORM,
        content=generated.content,
        filename=generated.file_name,
        content_type=PDF,
        actor=actor,
        owner_id=vacancy.id,
        uploaded=False,
    )
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="vacancy",
        entity_id=vacancy.id,
        new_value={
            "request_form": str(document.id),
            "sha256": document.sha256,
            "version": len(versions) + 1,
        },
        vacancy_id=vacancy.id,
    )
    return document


async def record_signed(
    db: AsyncSession,
    vacancy: Vacancy,
    *,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    actor: Person | None,
) -> StoredDocument:
    """Keep a copy of the form that was completed or signed outside grip."""
    document = await stored_documents.store_document(
        db,
        use=SIGNED_FORM,
        content=content,
        filename=filename,
        content_type=content_type,
        actor=actor,
        owner_id=vacancy.id,
    )
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="vacancy",
        entity_id=vacancy.id,
        new_value={"signed_form": str(document.id), "sha256": document.sha256},
        vacancy_id=vacancy.id,
    )
    return document


async def file_of(
    db: AsyncSession, vacancy_id: UUID, document_id: UUID
) -> StoredDocument:
    """A kept form or signed copy of this vacancy, with its bytes."""
    try:
        return await stored_documents.owned_document(
            db, REQUEST_FORM, vacancy_id, document_id, with_content=True
        )
    except NotFoundError:
        return await stored_documents.owned_document(
            db, SIGNED_FORM, vacancy_id, document_id, with_content=True
        )


async def remove_expired(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Remove the forms of vacancies that closed longer ago than the
    instance keeps them. Returns how many files went."""
    now = now or datetime.now(UTC)
    days = int(await instance_settings.get(db, RETENTION_DAYS.key))
    closed = (
        await db.execute(
            select(Vacancy.id).where(
                Vacancy.status.in_(CLOSED),
                Vacancy.updated_at <= now - timedelta(days=days),
            )
        )
    ).scalars()
    removed = 0
    for vacancy_id in closed:
        for use in (REQUEST_FORM, SIGNED_FORM):
            documents = await _kept(db, use, vacancy_id)
            for document in documents:
                await stored_documents.delete_document(db, document)
                removed += 1
            if documents:
                record_audit(
                    db,
                    actor=None,
                    action=DELETE,
                    entity="vacancy",
                    entity_id=vacancy_id,
                    old_value={"documents": use.owner_kind, "count": len(documents)},
                    note="retention",
                    vacancy_id=vacancy_id,
                )
    return removed


async def _main() -> None:
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            removed = await remove_expired(db)
            await db.commit()
        print(f"{removed} aanvraagformulieren verwijderd")  # noqa: T201
    finally:
        await close_db()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
