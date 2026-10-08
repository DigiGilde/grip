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
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
)

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


def bundled_mapping_names() -> list[str]:
    """The names of the mappings that ship with grip."""
    if not _BUNDLED_MAPPINGS.is_dir():
        return []
    return sorted(path.stem for path in _BUNDLED_MAPPINGS.glob("*.json"))


def has_values(pdf: bytes) -> bool:
    """Whether any field of the form is filled in."""
    return any(field.has_value for field in inspect_form(pdf))


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


def _to_bytes(writer: PdfWriter, *, viewer_draws: bool) -> bytes:
    """Write the form.

    ``viewer_draws`` asks the viewer to draw the field contents itself. That
    is the fallback only: a viewer that redraws also replaces the form's own
    tick boxes by its default, so a filled form no longer looks like the
    organisation's. Where grip can draw the text itself it does, and the
    flag stays off.
    """
    acroform = writer._root_object.get("/AcroForm")
    if viewer_draws:
        writer.set_need_appearances_writer(True)
    elif acroform is not None and "/NeedAppearances" in acroform.get_object():
        del acroform.get_object()[NameObject("/NeedAppearances")]
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# --- drawing a text field the way the form's own tool does -----------------------
#
# A viewer shows what the appearance stream of a field draws. Leaving that to
# the viewer gives another line spacing and wrapping per viewer. These
# functions draw it once, from the font the form embeds: padding of 2 pt, a
# line height of the font's bounding box, words wrapped on the font's widths.

_PADDING = 2.0
_DEFAULT_SIZE = 9.0
_MULTILINE = 1 << 12


@dataclass(frozen=True)
class _Font:
    name: str
    reference: Any
    widths: tuple[float, ...]
    first_char: int
    missing_width: float
    y_min: float
    y_max: float
    codec: str

    def encode(self, text: str) -> bytes:
        return text.encode(self.codec, errors="replace")

    def width(self, data: bytes, size: float) -> float:
        total = 0.0
        for code in data:
            index = code - self.first_char
            unit = self.widths[index] if 0 <= index < len(self.widths) else 0.0
            total += unit or self.missing_width
        return total * size / 1000


_CODECS = {
    "/WinAnsiEncoding": "cp1252",
    "/MacRomanEncoding": "mac_roman",
    "/StandardEncoding": "latin-1",
}


def _form_font(writer: PdfWriter, name: str) -> _Font | None:
    """The font a field names, when the form embeds it with its widths."""
    acroform = writer._root_object.get("/AcroForm")
    if acroform is None:
        return None
    resources = acroform.get_object().get("/DR")
    fonts = resources.get_object().get("/Font") if resources is not None else None
    if fonts is None or name not in fonts.get_object():
        return None
    reference = fonts.get_object().raw_get(name)
    font = reference.get_object()
    descriptor = font.get("/FontDescriptor")
    if "/Widths" not in font or descriptor is None:
        return None
    descriptor = descriptor.get_object()
    box = descriptor.get("/FontBBox")
    if box is None:
        return None
    encoding = font.get("/Encoding")
    if encoding is not None and not isinstance(encoding, str):
        encoding = encoding.get_object().get("/BaseEncoding")
    codec = _CODECS.get(str(encoding)) if encoding is not None else None
    if codec is None:
        return None
    return _Font(
        name=name,
        reference=reference,
        widths=tuple(float(w) for w in font["/Widths"]),
        first_char=int(font.get("/FirstChar", 0)),
        missing_width=float(descriptor.get("/MissingWidth", 0)),
        y_min=float(box[1]),
        y_max=float(box[3]),
        codec=codec,
    )


def _default_appearance(annotation, holder) -> tuple[str, float] | None:
    """Font name and size from the field's /DA, e.g. ``/Verdana 9 Tf 0 g``."""
    raw = annotation.get("/DA") or holder.get("/DA")
    if raw is None:
        return None
    parts = str(raw).split()
    if "Tf" not in parts:
        return None
    at = parts.index("Tf")
    if at < 2:
        return None
    try:
        size = float(parts[at - 1])
    except ValueError:
        return None
    return parts[at - 2], size or _DEFAULT_SIZE


def _wrap(text: str, font: _Font, size: float, room: float) -> list[bytes]:
    """Lines of at most ``room`` wide; a word that is too long gets its own line."""
    lines: list[bytes] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        current = b""
        for word in font.encode(paragraph).split(b" "):
            candidate = word if not current else current + b" " + word
            if current and font.width(candidate, size) > room:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def _literal(data: bytes) -> bytes:
    escaped = data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + escaped + b")"


def _draw_text(writer: PdfWriter, annotation, holder, value: str) -> bool:
    """Give a text field an appearance stream of its own. False when grip
    cannot draw it (no embedded font with widths); the viewer then does."""
    named = _default_appearance(annotation, holder)
    if named is None:
        return False
    font = _form_font(writer, named[0])
    if font is None:
        return False
    size = named[1]
    rect = [float(x) for x in annotation["/Rect"]]
    width, height = abs(rect[2] - rect[0]), abs(rect[3] - rect[1])
    leading = size * (font.y_max - font.y_min) / 1000
    flags = int(holder.get("/Ff", annotation.get("/Ff", 0)) or 0)
    if flags & _MULTILINE:
        lines = _wrap(value, font, size, width - 2 * _PADDING)
        baseline = height - _PADDING - leading
    else:
        lines = [font.encode(" ".join(value.split()))]
        baseline = (height - leading) / 2 - size * font.y_min / 1000

    out = [
        b"/Tx BMC",
        b"q",
        f"1 1 {width - 2:.3f} {height - 2:.3f} re".encode(),
        b"W",
        b"n",
        b"BT",
        f"{font.name} {size:g} Tf".encode(),
        b"0 g",
        f"{_PADDING:g} {baseline:.4f} Td".encode(),
    ]
    for index, line in enumerate(lines):
        if index:
            out.append(f"0 {-leading:.3f} Td".encode())
        if line:
            out.append(_literal(line) + b" Tj")
    out += [b"ET", b"Q", b"EMC"]

    stream = DecodedStreamObject()
    stream.set_data(b"\n".join(out) + b"\n")
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/BBox")] = ArrayObject(
        [FloatObject(0), FloatObject(0), FloatObject(width), FloatObject(height)]
    )
    stream[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject(font.name): font.reference})}
    )
    annotation[NameObject("/AP")] = DictionaryObject(
        {NameObject("/N"): writer._add_object(stream)}
    )
    return True


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
    return _to_bytes(writer, viewer_draws=False)


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
    viewer_draws = False
    for page in writer.pages:
        on_page: dict[str, str] = {}
        texts: list[tuple[Any, Any, str]] = []
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
                else:
                    texts.append((annotation, holder, updates[str(name)]))
        if on_page:
            writer.update_page_form_field_values(page, on_page, auto_regenerate=False)
            remaining -= set(on_page)
        for annotation, holder, value in texts:
            if not _draw_text(writer, annotation, holder, value):
                viewer_draws = True
    if remaining:
        raise FormTemplateError(
            "Deze velden uit de veldkoppeling staan niet in het formulier: "
            + ", ".join(sorted(remaining))
        )
    return _to_bytes(writer, viewer_draws=viewer_draws)
