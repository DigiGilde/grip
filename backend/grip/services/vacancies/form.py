"""Fill a fillable PDF form from a field mapping.

Pure functions on bytes, no database. A template is the blank form of an
organisation; a mapping says which form field gets which value. The filled
form stays fillable, so an adviser outside grip can complete it.

Mapping format (JSON)::

    {
      "form": "...", "mapping_version": 1, "date_format": "d-m-yyyy",
      "fields": [
        {"name": "Text1", "type": "text", "source": "requester_name"},
        {"name": "Box 3", "type": "checkbox", "source": "vacancy_type",
         "equals": "gerede", "on_value": "/Ja"}
      ]
    }

A text field gets the value of its source. A checkbox is ticked when the
value of its source equals ``equals``. A source without a value (``None``)
leaves the field untouched, so it stays open for completion by hand.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

# Every value a mapping may ask for. A mapping that names another source is
# rejected, so a typo cannot silently leave a field empty.
FORM_SOURCES: frozenset[str] = frozenset(
    {
        "requester_name",
        "request_date",
        "addressee_name",
        "declarable",
        "vacancy_type",
        "contract_type",
        "function_title",
        "fgr_function_name",
        "scale",
        "fte",
        "motivation",
        "hr_adviser_name",
        "hr_decision",
        "hr_note",
        "controller_name",
        "control_decision",
        "control_note",
        "approver_name",
        "approval_decision",
    }
)

_DATE_FORMATS = {
    "d-m-yyyy": lambda d: f"{d.day}-{d.month}-{d.year}",
    "dd-mm-yyyy": lambda d: f"{d.day:02d}-{d.month:02d}-{d.year}",
    "yyyy-mm-dd": lambda d: d.isoformat(),
}

_OFF = "/Off"

_BUNDLED_MAPPINGS = Path(__file__).resolve().parents[2] / "data" / "forms"


class FormMappingError(ValueError):
    """The mapping is not usable. The message is shown to the beheerder."""


class FormTemplateError(ValueError):
    """The uploaded file is not a usable blank form."""


@dataclass(frozen=True)
class FieldRule:
    name: str
    type: str
    source: str
    equals: Any = None
    on_value: str = "/Ja"
    verified: bool = True


@dataclass(frozen=True)
class FormMapping:
    form: str
    date_format: str
    fields: tuple[FieldRule, ...]

    @property
    def unverified(self) -> tuple[FieldRule, ...]:
        return tuple(rule for rule in self.fields if not rule.verified)


@dataclass(frozen=True)
class FormField:
    """A field found in a PDF form."""

    name: str
    type: str
    states: tuple[str, ...] = ()
    has_value: bool = False


def parse_mapping(data: Mapping[str, Any]) -> FormMapping:
    """Validate a mapping and turn it into rules."""
    date_format = data.get("date_format", "d-m-yyyy")
    if date_format not in _DATE_FORMATS:
        raise FormMappingError(
            f"Onbekende datumnotatie '{date_format}'. Kies uit: "
            + ", ".join(sorted(_DATE_FORMATS))
            + "."
        )
    raw_fields = data.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise FormMappingError("De veldkoppeling bevat geen velden.")

    rules: list[FieldRule] = []
    seen: set[str] = set()
    for raw in raw_fields:
        name = raw.get("name")
        kind = raw.get("type")
        source = raw.get("source")
        if not name or not isinstance(name, str):
            raise FormMappingError("Een veld in de koppeling heeft geen naam.")
        if name in seen:
            raise FormMappingError(
                f"Het veld '{name}' staat twee keer in de koppeling."
            )
        seen.add(name)
        if kind not in ("text", "checkbox"):
            raise FormMappingError(
                f"Het veld '{name}' heeft een onbekend type '{kind}'."
            )
        if source not in FORM_SOURCES:
            raise FormMappingError(
                f"Het veld '{name}' verwijst naar een onbekend gegeven '{source}'."
            )
        if kind == "checkbox" and "equals" not in raw:
            raise FormMappingError(
                f"Het selectievakje '{name}' mist de waarde waarbij het wordt "
                "aangevinkt."
            )
        on_value = raw.get("on_value", "/Ja")
        if not isinstance(on_value, str) or not on_value.startswith("/"):
            raise FormMappingError(
                f"De aan-waarde van '{name}' moet met een schuine streep beginnen."
            )
        rules.append(
            FieldRule(
                name=name,
                type=kind,
                source=source,
                equals=raw.get("equals"),
                on_value=on_value,
                verified=bool(raw.get("verified", True)),
            )
        )
    return FormMapping(
        form=str(data.get("form", "")), date_format=date_format, fields=tuple(rules)
    )


def load_bundled_mapping(name: str) -> dict[str, Any]:
    """A mapping that ships with grip (field names only, never a form)."""
    if not name.replace("-", "").replace("_", "").isalnum():
        raise FormMappingError(f"Ongeldige naam voor een veldkoppeling: '{name}'.")
    path = _BUNDLED_MAPPINGS / f"{name}.json"
    if not path.is_file():
        raise FormMappingError(f"Er is geen veldkoppeling met de naam '{name}'.")
    return json.loads(path.read_text(encoding="utf-8"))


def _reader(pdf: bytes) -> PdfReader:
    try:
        return PdfReader(io.BytesIO(pdf))
    except Exception as exc:  # pypdf raises several unrelated error types
        raise FormTemplateError("Het bestand is geen leesbare pdf.") from exc


def _widgets(reader: PdfReader):
    for page_index, page in enumerate(reader.pages):
        for ref in page.get("/Annots", None) or []:
            annotation = ref.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            parent = annotation.get("/Parent")
            holder = annotation
            if "/T" not in annotation and parent is not None:
                holder = parent.get_object()
            name = holder.get("/T")
            if name is None:
                continue
            yield page_index, str(name), annotation, holder


def inspect_form(pdf: bytes) -> list[FormField]:
    """List the fields of a form: name, type, checkbox states, filled or not.

    Field values are never returned, only whether a field has one.
    """
    reader = _reader(pdf)
    found: dict[str, FormField] = {}
    for _page, name, annotation, holder in _widgets(reader):
        field_type = holder.get("/FT") or annotation.get("/FT")
        if field_type == "/Btn":
            states: tuple[str, ...] = ()
            appearance = annotation.get("/AP")
            if appearance is not None and "/N" in appearance:
                states = tuple(str(key) for key in appearance["/N"])
            state = annotation.get("/AS") or holder.get("/V")
            has_value = state is not None and str(state) != _OFF
            found[name] = FormField(name, "checkbox", states, has_value)
        elif field_type == "/Tx":
            value = holder.get("/V")
            found[name] = FormField(name, "text", (), bool(value and str(value)))
        else:
            found[name] = FormField(name, str(field_type or "").lstrip("/").lower())
    return list(found.values())


def check_template(pdf: bytes, mapping: FormMapping) -> None:
    """Refuse a template that is not blank or does not match the mapping.

    A filled-in form holds names of people; storing it as the template would
    keep them forever and leak them into every form generated from it.
    """
    fields = {field.name: field for field in inspect_form(pdf)}
    if not fields:
        raise FormTemplateError("De pdf bevat geen invulbare velden.")
    filled = sorted(field.name for field in fields.values() if field.has_value)
    if filled:
        raise FormTemplateError(
            "Het formulier is al ingevuld (" + ", ".join(filled) + "). Lever een "
            "leeg formulier aan, of maak het eerst leeg."
        )
    for rule in mapping.fields:
        field = fields.get(rule.name)
        if field is None:
            raise FormTemplateError(
                f"Het veld '{rule.name}' uit de veldkoppeling staat niet in de pdf."
            )
        if field.type != rule.type:
            raise FormTemplateError(
                f"Het veld '{rule.name}' is in de pdf een ander soort veld dan in "
                "de veldkoppeling."
            )
        if rule.type == "checkbox" and rule.on_value not in field.states:
            raise FormTemplateError(
                f"Het selectievakje '{rule.name}' kent de aan-waarde "
                f"'{rule.on_value}' niet."
            )


def _writer(pdf: bytes) -> PdfWriter:
    return PdfWriter(clone_from=_reader(pdf))


def _to_bytes(writer: PdfWriter) -> bytes:
    # Ask the viewer to redraw the field contents in the form's own font.
    # Set last: updating field values resets the flag.
    writer.set_need_appearances_writer(True)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def clear_form(pdf: bytes) -> bytes:
    """Empty every field of a form, so it can serve as a blank template."""
    writer = _writer(pdf)
    for page in writer.pages:
        updates: dict[str, str] = {}
        for ref in page.get("/Annots", None) or []:
            annotation = ref.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            parent = annotation.get("/Parent")
            holder = annotation
            if "/T" not in annotation and parent is not None:
                holder = parent.get_object()
            name = holder.get("/T")
            if name is None:
                continue
            field_type = holder.get("/FT") or annotation.get("/FT")
            if field_type == "/Btn":
                updates[str(name)] = _OFF
            elif field_type == "/Tx":
                updates[str(name)] = ""
        if updates:
            writer.update_page_form_field_values(page, updates, auto_regenerate=False)
    return _to_bytes(writer)


def format_value(value: Any, date_format: str = "d-m-yyyy") -> str:
    """How a value is written in a text field."""
    if isinstance(value, bool):
        return "Ja" if value else "Nee"
    if isinstance(value, date):
        return _DATE_FORMATS[date_format](value)
    if isinstance(value, Decimal):
        text = format(value.normalize(), "f")
        return text.replace(".", ",")
    return str(value)


def fill_form(pdf: bytes, mapping: FormMapping, values: Mapping[str, Any]) -> bytes:
    """Fill the template with the values and return a PDF that stays fillable.

    ``values`` is keyed by source name. A missing or ``None`` value leaves
    every field of that source as it is in the template.
    """
    unknown = set(values) - FORM_SOURCES
    if unknown:
        raise FormMappingError(
            "Onbekende gegevens voor het formulier: " + ", ".join(sorted(unknown))
        )

    updates: dict[str, str] = {}
    for rule in mapping.fields:
        value = values.get(rule.source)
        if value is None:
            continue
        if rule.type == "checkbox":
            updates[rule.name] = rule.on_value if value == rule.equals else _OFF
        else:
            updates[rule.name] = format_value(value, mapping.date_format)

    writer = _writer(pdf)
    remaining = set(updates)
    for page in writer.pages:
        on_page: dict[str, str] = {}
        for ref in page.get("/Annots", None) or []:
            annotation = ref.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            parent = annotation.get("/Parent")
            holder = annotation
            if "/T" not in annotation and parent is not None:
                holder = parent.get_object()
            name = holder.get("/T")
            if name is not None and str(name) in updates:
                on_page[str(name)] = updates[str(name)]
                # pypdf sets /V on a checkbox but leaves the visible state to
                # the widget's /AS; set both so every viewer agrees.
                if (holder.get("/FT") or annotation.get("/FT")) == "/Btn":
                    annotation[NameObject("/AS")] = NameObject(updates[str(name)])
        if on_page:
            writer.update_page_form_field_values(page, on_page, auto_regenerate=False)
            remaining -= set(on_page)
    if remaining:
        raise FormTemplateError(
            "Deze velden uit de veldkoppeling staan niet in het formulier: "
            + ", ".join(sorted(remaining))
        )
    return _to_bytes(writer)
