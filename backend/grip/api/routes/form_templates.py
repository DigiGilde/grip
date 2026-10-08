"""Form templates: the blank request form of the instance and its mapping.

Beheerder only. The blank form is uploaded per instance and never lives in
the repository; a form that is still filled in holds names of people and is
refused unless the beheerder has it cleared first.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, build_response, schema_classes
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.access.vacancies import form_template_resource
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.models.vacancy import FormTemplate
from grip.repositories.vacancy import VacancyRepository
from grip.schema.form_templates import (
    BundledMappingOut,
    FormFieldOut,
    FormInspectionOut,
    FormTemplateOut,
)
from grip.services.errors import DomainValidationError
from grip.services.vacancies import form as forms
from grip.services.vacancies import service

router = APIRouter(prefix="/form-templates", tags=["form-templates"])

# A request form is a few hundred kilobytes; anything far beyond is not one.
MAX_FORM_BYTES = 10 * 1024 * 1024


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_FORM_BYTES + 1)
    if len(content) > MAX_FORM_BYTES:
        raise DomainValidationError("Het bestand is te groot voor een formulier.")
    if not content:
        raise DomainValidationError("Het bestand is leeg.")
    return content


def _mapping_from(mapping_json: str | None, bundled: str | None) -> dict[str, Any]:
    """The mapping the beheerder sent, or the bundled one they picked."""
    if mapping_json and mapping_json.strip():
        try:
            data = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise DomainValidationError(
                "De veldkoppeling is geen geldige JSON."
            ) from exc
        if not isinstance(data, dict):
            raise DomainValidationError("De veldkoppeling moet een JSON-object zijn.")
        return data
    if bundled:
        try:
            return forms.load_bundled_mapping(bundled)
        except forms.FormMappingError as exc:
            raise DomainValidationError(str(exc)) from exc
    raise DomainValidationError(
        "Kies een meegeleverde veldkoppeling of lever er zelf een aan."
    )


def _template_out(template: FormTemplate, names: dict[UUID, str]) -> FormTemplateOut:
    fields = template.mapping.get("fields") or []
    return FormTemplateOut(
        id=template.id,
        name=template.name,
        file_name=template.file_name,
        is_active=template.is_active,
        created_at=template.created_at,
        uploaded_by_name=names.get(template.uploaded_by_id)
        if template.uploaded_by_id
        else None,
        mapped_fields=len(fields),
        unverified_fields=sum(1 for rule in fields if rule.get("verified") is False),
    )


async def _require_beheer(decider: Any, subject: Any, action: Action) -> None:
    await require(
        decider, subject, action, form_template_resource(), DataClass.MASTER_DATA
    )


@router.get("", response_model=None)
async def list_form_templates(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _require_beheer(decider, subject, Action.READ)
    templates = await service.list_form_templates(db)
    names = await VacancyRepository(db).person_names_by_id(
        t.uploaded_by_id for t in templates if t.uploaded_by_id is not None
    )
    return [
        build_response(_template_out(t, names), schema_classes(FormTemplateOut))
        for t in templates
    ]


@router.get("/bundled-mappings", response_model=None)
async def list_bundled_mappings(
    subject: CurrentSubject,
    decider: AccessDecider,
) -> list[dict[str, Any]]:
    """The field mappings that ship with grip (field names only, no form)."""
    await _require_beheer(decider, subject, Action.READ)
    result: list[dict[str, Any]] = []
    for name in forms.bundled_mapping_names():
        mapping = forms.load_bundled_mapping(name)
        out = BundledMappingOut(
            name=name,
            title=str(mapping.get("title") or name),
            description=mapping.get("description"),
            mapping=mapping,
        )
        result.append(build_response(out, schema_classes(BundledMappingOut)))
    return result


@router.post("/inspect", response_model=None)
async def inspect_form(
    subject: CurrentSubject,
    decider: AccessDecider,
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
    bundled_mapping: str | None = Form(default=None),
) -> dict[str, Any]:
    """List the fields of an uploaded form, as help for the mapping.

    Nothing is stored, and no value of a field is returned: only its name,
    its kind, and whether it is filled in.
    """
    await _require_beheer(decider, subject, Action.EDIT)
    content = await _read_upload(file)
    try:
        fields = forms.inspect_form(content)
    except forms.FormTemplateError as exc:
        raise DomainValidationError(str(exc)) from exc

    rules: dict[str, dict[str, Any]] = {}
    problem: str | None = None
    missing: list[str] = []
    if (mapping and mapping.strip()) or bundled_mapping:
        data = _mapping_from(mapping, bundled_mapping)
        try:
            parsed = forms.parse_mapping(data)
        except forms.FormMappingError as exc:
            raise DomainValidationError(str(exc)) from exc
        rules = {rule["name"]: rule for rule in data.get("fields", [])}
        found = {field.name for field in fields}
        missing = sorted(rule.name for rule in parsed.fields if rule.name not in found)
        try:
            forms.check_template(content, parsed)
        except forms.FormTemplateError as exc:
            problem = str(exc)

    out = FormInspectionOut(
        fields=[
            FormFieldOut(
                name=field.name,
                type=field.type,
                states=list(field.states),
                has_value=field.has_value,
                source=rules.get(field.name, {}).get("source"),
                label=rules.get(field.name, {}).get("label"),
            )
            for field in fields
        ],
        has_values=any(field.has_value for field in fields),
        missing_fields=missing,
        problem=problem,
    )
    return build_response(out, schema_classes(FormInspectionOut))


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def upload_form_template(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=255),
    mapping: str | None = Form(default=None),
    bundled_mapping: str | None = Form(default=None),
    clear_values: bool = Form(default=False),
    activate: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Store a blank form with its mapping.

    A form that still holds values is refused. With ``clear_values`` the
    values are removed before it is stored.
    """
    await _require_beheer(decider, subject, Action.EDIT)
    content = await _read_upload(file)
    template = await service.upload_form_template(
        db,
        actor=person,
        name=name.strip(),
        file_name=(file.filename or "formulier.pdf")[:255],
        content=content,
        mapping=_mapping_from(mapping, bundled_mapping),
        activate=activate,
        clear_values=clear_values,
    )
    return build_response(
        _template_out(template, {person.id: person.name}),
        schema_classes(FormTemplateOut),
    )


@router.post("/{template_id}/activate", response_model=None)
async def activate_form_template(
    template_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate new forms from this template from now on."""
    await _require_beheer(decider, subject, Action.EDIT)
    template = await service.activate_form_template(db, template_id, actor=person)
    names = await VacancyRepository(db).person_names_by_id(
        [template.uploaded_by_id] if template.uploaded_by_id else []
    )
    return build_response(
        _template_out(template, names), schema_classes(FormTemplateOut)
    )
