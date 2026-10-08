"""Fixtures for the vacancy tests. Every name and value here is fictional."""

from __future__ import annotations

import io
from typing import Any

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)


def _rect(x: float, y: float, w: float, h: float) -> ArrayObject:
    return ArrayObject([FloatObject(v) for v in (x, y, x + w, y + h)])


def _appearance(writer: PdfWriter, content: bytes) -> Any:
    stream = DecodedStreamObject()
    stream.set_data(content)
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/BBox")] = _rect(0, 0, 12, 12)
    return writer._add_object(stream)


def build_form_pdf(
    text_fields: list[str],
    checkboxes: list[str],
    *,
    on_value: str = "/Ja",
    text_values: dict[str, str] | None = None,
    checked: set[str] | None = None,
) -> bytes:
    """A small fillable PDF with the given text fields and checkboxes."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=400)
    annotations = ArrayObject()
    fields = ArrayObject()
    y = 360.0

    for name in text_fields:
        widget = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/Rect"): _rect(20, y, 200, 14),
                NameObject("/DA"): TextStringObject("/Helv 9 Tf 0 g"),
                NameObject("/F"): NumberObject(4),
                NameObject("/P"): page.indirect_reference,
            }
        )
        value = (text_values or {}).get(name)
        if value:
            widget[NameObject("/V")] = TextStringObject(value)
        ref = writer._add_object(widget)
        annotations.append(ref)
        fields.append(ref)
        y -= 20

    for name in checkboxes:
        state = on_value if name in (checked or set()) else "/Off"
        normal = DictionaryObject(
            {
                NameObject(on_value): _appearance(writer, b"0 0 12 12 re f"),
                NameObject("/Off"): _appearance(writer, b""),
            }
        )
        widget = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Btn"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/Rect"): _rect(20, y, 12, 12),
                NameObject("/AP"): DictionaryObject({NameObject("/N"): normal}),
                NameObject("/AS"): NameObject(state),
                NameObject("/V"): NameObject(state),
                NameObject("/F"): NumberObject(4),
                NameObject("/P"): page.indirect_reference,
            }
        )
        ref = writer._add_object(widget)
        annotations.append(ref)
        fields.append(ref)
        y -= 20

    page[NameObject("/Annots")] = annotations
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {
            NameObject("/Fields"): fields,
            NameObject("/DA"): TextStringObject("/Helv 9 Tf 0 g"),
            NameObject("/DR"): DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/Helv"): writer._add_object(font)}
                    )
                }
            ),
        }
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# A fictional form: field names differ from any real form on purpose.
TEST_MAPPING: dict[str, Any] = {
    "form": "testformulier",
    "mapping_version": 1,
    "date_format": "d-m-yyyy",
    "fields": [
        {"name": "aanvrager", "type": "text", "source": "requester_name"},
        {"name": "datum", "type": "text", "source": "request_date"},
        {"name": "aan", "type": "text", "source": "addressee_name"},
        {"name": "functie", "type": "text", "source": "function_title"},
        {"name": "fgr", "type": "text", "source": "fgr_function_name"},
        {"name": "schaal", "type": "text", "source": "scale"},
        {"name": "fte", "type": "text", "source": "fte"},
        {"name": "motivatie", "type": "text", "source": "motivation"},
        {"name": "hr_naam", "type": "text", "source": "hr_adviser_name"},
        {"name": "hr_toelichting", "type": "text", "source": "hr_note"},
        {"name": "controller", "type": "text", "source": "controller_name"},
        {"name": "akkoord_naam", "type": "text", "source": "approver_name"},
        {"name": "decl_ja", "type": "checkbox", "source": "declarable", "equals": True},
        {
            "name": "decl_nee",
            "type": "checkbox",
            "source": "declarable",
            "equals": False,
        },
        {
            "name": "type_regulier",
            "type": "checkbox",
            "source": "vacancy_type",
            "equals": "regulier",
        },
        {
            "name": "type_gerede",
            "type": "checkbox",
            "source": "vacancy_type",
            "equals": "gerede",
        },
        {
            "name": "contract_project",
            "type": "checkbox",
            "source": "contract_type",
            "equals": "temporary_project",
        },
        {
            "name": "hr_wel",
            "type": "checkbox",
            "source": "hr_decision",
            "equals": True,
        },
        {
            "name": "hr_niet",
            "type": "checkbox",
            "source": "hr_decision",
            "equals": False,
        },
        {
            "name": "control_wel",
            "type": "checkbox",
            "source": "control_decision",
            "equals": True,
        },
        {
            "name": "akkoord_wel",
            "type": "checkbox",
            "source": "approval_decision",
            "equals": True,
        },
        {
            "name": "akkoord_niet",
            "type": "checkbox",
            "source": "approval_decision",
            "equals": False,
        },
    ],
}


def _names(kind: str) -> list[str]:
    return [f["name"] for f in TEST_MAPPING["fields"] if f["type"] == kind]


@pytest.fixture
def test_mapping() -> dict[str, Any]:
    return TEST_MAPPING


@pytest.fixture
def blank_form() -> bytes:
    return build_form_pdf(_names("text"), _names("checkbox"))


@pytest.fixture
def filled_form() -> bytes:
    return build_form_pdf(
        _names("text"),
        _names("checkbox"),
        text_values={"aanvrager": "Fictieve Aanvrager"},
        checked={"decl_ja"},
    )


class FakeChatClient:
    """Stands in for the language model and remembers what it was sent."""

    def __init__(self, answer: str = "Concepttekst van het model.") -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    @property
    def model_id(self) -> str:
        return "testmodel-1"

    async def complete(self, *, system: str, user: str, max_tokens: int = 1500) -> str:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return self.answer


@pytest.fixture
def fake_client() -> FakeChatClient:
    return FakeChatClient()


@pytest.fixture
def form_builder():
    """The builder itself, for tests that need another form."""
    return build_form_pdf
