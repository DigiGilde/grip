"""Looking at a stored form: its fields, what fills them, and a filled sample.

For the beheerder who set a form up and wants to see whether the mapping is
right. The sample is made by the same function as the form of a real
vacancy, so what is seen here is what a requester gets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.core.config import get_settings
from grip.models.person import Person
from grip.models.vacancy import FormTemplate, TextKind
from grip.repositories.vacancy import FormTemplateRepository, VacancyRepository
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.vacancies import form as forms
from grip.services.vacancies import service


@dataclass(frozen=True)
class Choice:
    value: Any
    label: str


@dataclass(frozen=True)
class Source:
    """A piece of a vacancy a form field can be filled with."""

    key: str
    # What grip puts in the field, in plain words.
    label: str
    # A text source fills a text field. A source with choices ticks a box:
    # one box per choice.
    choices: tuple[Choice, ...] = ()


_YES_NO = (Choice(True, "ja"), Choice(False, "nee"))
_AGREED = (Choice(True, "akkoord"), Choice(False, "niet akkoord"))

SOURCES: tuple[Source, ...] = (
    Source("requester_name", "Naam van de aanvrager"),
    Source("request_date", "Datum van de aanvraag"),
    Source("addressee_name", "Naam van wie akkoord moet geven"),
    Source("declarable", "Of de vacature declarabel is", _YES_NO),
    Source(
        "vacancy_type",
        "Type vacature",
        (
            Choice("regulier", "regulier"),
            Choice("specialistisch", "specialistisch"),
            Choice("beoogd", "beoogde kandidaat"),
            Choice("gerede", "gerede kandidaat"),
        ),
    ),
    Source(
        "contract_type",
        "Type contract",
        (
            Choice("temporary_project", "tijdelijk (projectcontract)"),
            Choice("temporary_before_permanent", "tijdelijk voorafgaand aan vast"),
        ),
    ),
    Source("function_title", "Functienaam van de vacature"),
    Source("fgr_function_name", "Functienaam uit het Functiegebouw Rijk"),
    Source("scale", "Schaal"),
    Source("fte", "Aantal fte"),
    Source("motivation", "De vastgestelde aanleiding en motivatie"),
    Source("hr_adviser_name", "Naam van de HR-adviseur"),
    Source("hr_decision", "Advies van HR", _AGREED),
    Source("hr_note", "Toelichting van HR"),
    Source("controller_name", "Naam van de controller"),
    Source("control_decision", "Advies van concern control", _AGREED),
    Source("control_note", "Toelichting van concern control"),
    Source("approver_name", "Naam van wie akkoord gaf"),
    Source("approval_decision", "Het akkoord", _AGREED),
)
_BY_KEY = {source.key: source for source in SOURCES}
assert set(_BY_KEY) == set(forms.FORM_SOURCES)

# What a sample shows when no vacancy is chosen: every field filled, with
# values nobody can mistake for a real request.
SAMPLE_VALUES: dict[str, Any] = {
    "requester_name": "Vera Voorbeeld",
    "request_date": date(2026, 1, 15),
    "addressee_name": "Dirk Directeur",
    "declarable": True,
    "vacancy_type": "regulier",
    "contract_type": "temporary_project",
    "function_title": "Voorbeeldfunctie",
    "fgr_function_name": "Voorbeeldfunctie uit het Functiegebouw",
    "scale": 11,
    "fte": Decimal("0.8"),
    "motivation": "Dit is een voorbeeld van de aanleiding en motivatie. De tekst "
    "is lang genoeg om over meer regels te lopen, zodat je ziet hoe het "
    "formulier een langere toelichting afbreekt en of die binnen het vak blijft.",
    "hr_adviser_name": "Hanna Hulp",
    "hr_decision": True,
    "hr_note": "Voorbeeld van een toelichting van HR.",
    "controller_name": "Coen Controle",
    "control_decision": True,
    "control_note": "Voorbeeld van een toelichting van concern control.",
    "approver_name": "Dirk Directeur",
    "approval_decision": True,
}


def source_text(source_key: str, equals: Any = None) -> str:
    """What a rule puts in its field, as a sentence part."""
    source = _BY_KEY.get(source_key)
    if source is None:
        return source_key
    if source.choices:
        for choice in source.choices:
            if choice.value == equals:
                return f"{source.label}: aangevinkt bij {choice.label}"
    return source.label


def source_label(source_key: str) -> str:
    """The plain name of a piece of the vacancy."""
    source = _BY_KEY.get(source_key)
    return source.label if source is not None else source_key


async def get_template(db: AsyncSession, template_id: UUID) -> FormTemplate:
    template = await FormTemplateRepository(db).get(template_id)
    if template is None:
        raise NotFoundError("Formulier", template_id)
    return template


@dataclass(frozen=True)
class FieldView:
    name: str
    type: str
    # The caption the mapping gives the field, as it reads on the form.
    label: str | None
    source: str | None
    equals: Any
    fills: str | None
    # "mapped", "unfilled" (in the form, nothing fills it) or "missing"
    # (in the mapping, no longer in the form).
    state: str


def describe(template: FormTemplate) -> list[FieldView]:
    """Every field of the form and of the mapping, in the order of the form."""
    rules = {
        raw["name"]: raw
        for raw in template.mapping.get("fields", [])
        if isinstance(raw, dict) and raw.get("name")
    }
    views: list[FieldView] = []
    seen: set[str] = set()
    for field in forms.inspect_form(template.content):
        seen.add(field.name)
        rule = rules.get(field.name)
        if rule is None:
            views.append(
                FieldView(field.name, field.type, None, None, None, None, "unfilled")
            )
            continue
        views.append(
            FieldView(
                name=field.name,
                type=field.type,
                label=rule.get("label"),
                source=rule.get("source"),
                equals=rule.get("equals"),
                fills=source_text(str(rule.get("source")), rule.get("equals")),
                state="mapped",
            )
        )
    for name, rule in rules.items():
        if name not in seen:
            views.append(
                FieldView(
                    name=name,
                    type=str(rule.get("type") or ""),
                    label=rule.get("label"),
                    source=rule.get("source"),
                    equals=rule.get("equals"),
                    fills=source_text(str(rule.get("source")), rule.get("equals")),
                    state="missing",
                )
            )
    return views


async def sample(db: AsyncSession, template_id: UUID, vacancy_id: UUID | None) -> bytes:
    """The form filled in: for a vacancy as its requester would get it, or
    with example values in every field when no vacancy is given."""
    template = await get_template(db, template_id)
    if vacancy_id is None:
        values = dict(SAMPLE_VALUES)
    else:
        vacancy = await VacancyRepository(db).get(vacancy_id)
        if vacancy is None:
            raise NotFoundError("Vacature", vacancy_id)
        motivation = await service.established_text(db, vacancy.id, TextKind.motivation)
        values = service.form_values(
            vacancy, motivation=motivation.body if motivation else None
        )
    try:
        mapping = forms.parse_mapping(usable_mapping(template))
        return forms.fill_form(
            template.content, mapping, values, example=get_settings().is_example
        )
    except (forms.FormMappingError, forms.FormTemplateError) as exc:
        raise DomainValidationError(str(exc)) from exc


def usable_mapping(template: FormTemplate) -> dict[str, Any]:
    """The mapping without the rules for fields the form no longer has."""
    present = {field.name for field in forms.inspect_form(template.content)}
    mapping = dict(template.mapping)
    mapping["fields"] = [
        raw for raw in template.mapping.get("fields", []) if raw.get("name") in present
    ]
    return mapping


async def set_field(
    db: AsyncSession,
    template_id: UUID,
    name: str,
    *,
    source: str | None,
    equals: Any = None,
    actor: Person | None,
) -> FormTemplate:
    """Say what fills one field, or that nothing does (``source`` None)."""
    template = await get_template(db, template_id)
    fields = {field.name: field for field in forms.inspect_form(template.content)}
    rules = [dict(raw) for raw in template.mapping.get("fields", [])]
    before = next((raw for raw in rules if raw.get("name") == name), None)
    if name not in fields and before is None:
        raise DomainValidationError(f"Het formulier heeft geen veld '{name}'.")
    rules = [raw for raw in rules if raw.get("name") != name]
    if source is not None:
        field = fields.get(name)
        if field is None:
            raise DomainValidationError(
                f"Het veld '{name}' staat niet meer in het formulier. Haal de "
                "koppeling weg."
            )
        chosen = _BY_KEY.get(source)
        if chosen is None:
            raise DomainValidationError("Kies een gegeven uit de lijst.")
        rule: dict[str, Any] = {"name": name, "type": field.type, "source": source}
        if before is not None and before.get("label"):
            rule["label"] = before["label"]
        if field.type == "checkbox":
            if not chosen.choices:
                raise DomainValidationError(
                    f"'{chosen.label}' is tekst en past niet in een selectievakje."
                )
            if equals not in [choice.value for choice in chosen.choices]:
                raise DomainValidationError(
                    "Kies bij welke waarde het vakje wordt aangevinkt."
                )
            states = [state for state in field.states if state != "/Off"]
            rule["equals"] = equals
            rule["on_value"] = (before or {}).get("on_value") or (
                states[0] if states else "/Ja"
            )
        elif field.type != "text":
            raise DomainValidationError("Dit soort veld kan grip niet invullen.")
        # Set by a person on this screen, looking at the form.
        rule["verified"] = True
        rules.append(rule)
    order = {field_name: index for index, field_name in enumerate(fields)}
    rules.sort(key=lambda raw: order.get(raw.get("name"), len(order)))
    mapping = {**template.mapping, "fields": rules}
    if any(raw.get("name") in fields for raw in rules):
        try:
            forms.parse_mapping(
                {**mapping, "fields": [r for r in rules if r["name"] in fields]}
            )
        except forms.FormMappingError as exc:
            raise DomainValidationError(str(exc)) from exc
    template.mapping = mapping
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="form_template",
        entity_id=template.id,
        old_value={"field": name, "source": (before or {}).get("source")},
        new_value={"field": name, "source": source},
    )
    return template
