"""A filled form looks the same in every viewer.

grip draws the text of a field itself, from the font the form embeds, and
leaves the form's own tick boxes alone. All values are fictional.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from grip.services.vacancies import form as forms

BOX = b"0.9 g 0 0 12 12 re f 0 g 2 2 8 8 re f"
MAPPING = {
    "form": "test",
    "fields": [
        {"name": "naam", "type": "text", "source": "requester_name"},
        {"name": "motivatie", "type": "text", "source": "motivation"},
        {
            "name": "wel",
            "type": "checkbox",
            "source": "hr_decision",
            "equals": True,
            "on_value": "/Ja",
        },
    ],
}


def _rect(x: float, y: float, w: float, h: float) -> ArrayObject:
    return ArrayObject([FloatObject(v) for v in (x, y, x + w, y + h)])


def _form(*, with_font: bool = True) -> bytes:
    """A form with one line, a multi-line field and a tick box of its own
    design. The font is declared with widths (every glyph half an em)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=400)
    refs = ArrayObject()

    def text(name: str, y: float, height: float, flags: int) -> None:
        widget = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/Rect"): _rect(20, y, 204, height),
                NameObject("/DA"): TextStringObject("/Vd 10 Tf 0 g"),
                NameObject("/Ff"): NumberObject(flags),
                NameObject("/F"): NumberObject(4),
            }
        )
        refs.append(writer._add_object(widget))

    text("naam", 360, 14, 0)
    text("motivatie", 280, 60, 1 << 12)

    def appearance(data: bytes):
        stream = DecodedStreamObject()
        stream.set_data(data)
        stream[NameObject("/Type")] = NameObject("/XObject")
        stream[NameObject("/Subtype")] = NameObject("/Form")
        stream[NameObject("/BBox")] = _rect(0, 0, 12, 12)
        return writer._add_object(stream)

    refs.append(
        writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Widget"),
                    NameObject("/FT"): NameObject("/Btn"),
                    NameObject("/T"): TextStringObject("wel"),
                    NameObject("/Rect"): _rect(20, 250, 12, 12),
                    NameObject("/AP"): DictionaryObject(
                        {
                            NameObject("/N"): DictionaryObject(
                                {
                                    NameObject("/Ja"): appearance(BOX),
                                    NameObject("/Off"): appearance(b""),
                                }
                            )
                        }
                    ),
                    NameObject("/AS"): NameObject("/Off"),
                    NameObject("/V"): NameObject("/Off"),
                    NameObject("/F"): NumberObject(4),
                }
            )
        )
    )
    page[NameObject("/Annots")] = refs
    resources = DictionaryObject()
    if with_font:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/TrueType"),
                NameObject("/BaseFont"): NameObject("/Voorbeeld"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                NameObject("/FirstChar"): NumberObject(0),
                NameObject("/LastChar"): NumberObject(255),
                NameObject("/Widths"): ArrayObject([NumberObject(500)] * 256),
                NameObject("/FontDescriptor"): DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/FontDescriptor"),
                        NameObject("/FontName"): NameObject("/Voorbeeld"),
                        NameObject("/FontBBox"): ArrayObject(
                            [NumberObject(v) for v in (0, -300, 1000, 1000)]
                        ),
                    }
                ),
            }
        )
        resources[NameObject("/Font")] = DictionaryObject(
            {NameObject("/Vd"): writer._add_object(font)}
        )
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): refs, NameObject("/DR"): resources}
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _widget(pdf: bytes, name: str):
    reader = PdfReader(io.BytesIO(pdf))
    for ref in reader.pages[0]["/Annots"]:
        widget = ref.get_object()
        if widget.get("/T") == name:
            return widget
    raise AssertionError(name)


def _stream(pdf: bytes, name: str) -> str:
    return _widget(pdf, name)["/AP"]["/N"].get_object().get_data().decode("latin-1")


VALUES = {
    "requester_name": "Vera Voorbeeld",
    "motivation": "Het team groeit en heeft een derde collega nodig voor de "
    "sturing. Zonder die rol blijft werk liggen.",
    "hr_decision": True,
}


def test_text_is_drawn_from_the_font_of_the_form():
    filled = forms.fill_form(_form(), forms.parse_mapping(MAPPING), VALUES)
    acroform = PdfReader(io.BytesIO(filled)).trailer["/Root"]["/AcroForm"]
    # Nothing is left to the viewer, so its own tick boxes cannot appear.
    assert "/NeedAppearances" not in acroform

    line = _stream(filled, "naam")
    assert "/Vd 10 Tf" in line and "(Vera Voorbeeld) Tj" in line
    # One line sits in the middle of the field: leading 13 in a height of 14,
    # plus the part of the font below the baseline.
    assert "2 3.5000 Td" in line
    assert _widget(filled, "naam")["/AP"]["/N"]["/Resources"]["/Font"]["/Vd"]


def test_a_long_text_wraps_inside_its_box():
    filled = forms.fill_form(_form(), forms.parse_mapping(MAPPING), VALUES)
    stream = _stream(filled, "motivatie")
    lines = re.findall(r"\((.*?)\) Tj", stream)
    assert len(lines) > 1
    assert " ".join(lines) == VALUES["motivation"]
    # Every glyph is 5 wide at this size; the box leaves 200 for text.
    assert all(len(line) * 5 <= 200 for line in lines)
    # The first line hangs from the top, the next ones a line height lower.
    assert "2 45.0000 Td" in stream
    assert stream.count("0 -13.000 Td") == len(lines) - 1


def test_the_tick_box_keeps_the_drawing_of_the_form():
    blank = _form()
    filled = forms.fill_form(blank, forms.parse_mapping(MAPPING), VALUES)
    widget = _widget(filled, "wel")
    assert widget["/AS"] == "/Ja"
    assert widget["/AP"]["/N"]["/Ja"].get_object().get_data() == BOX


def test_the_result_can_be_filled_in_further():
    mapping = forms.parse_mapping(MAPPING)
    first = forms.fill_form(_form(), mapping, {"requester_name": "Vera Voorbeeld"})
    second = forms.fill_form(first, mapping, {"motivation": "Later aangevuld."})
    fields = PdfReader(io.BytesIO(second)).get_fields()
    assert fields["naam"]["/V"] == "Vera Voorbeeld"
    assert fields["motivatie"]["/V"] == "Later aangevuld."
    assert "(Later aangevuld.) Tj" in _stream(second, "motivatie")


def test_without_an_embedded_font_the_viewer_draws():
    filled = forms.fill_form(
        _form(with_font=False), forms.parse_mapping(MAPPING), VALUES
    )
    acroform = PdfReader(io.BytesIO(filled)).trailer["/Root"]["/AcroForm"]
    assert acroform["/NeedAppearances"]


def test_a_cleared_form_holds_no_trace_of_what_was_filled_in():
    filled = forms.fill_form(_form(), forms.parse_mapping(MAPPING), VALUES)
    blank = forms.clear_form(filled)
    assert not forms.has_values(blank)
    for name in ("naam", "motivatie"):
        assert "Voorbeeld" not in _stream(blank, name)
        assert "team" not in _stream(blank, name)
    forms.check_template(blank, forms.parse_mapping(MAPPING))


def test_a_form_filled_in_an_example_instance_says_so_on_every_page():
    mapping = forms.parse_mapping(MAPPING)
    marked = PdfReader(
        io.BytesIO(forms.fill_form(_form(), mapping, VALUES, example=True))
    )
    for page in marked.pages:
        assert "Voorbeeld, geen echt document" in page.extract_text()
    # Still a form that can be filled in further.
    assert marked.get_fields()
    plain = PdfReader(io.BytesIO(forms.fill_form(_form(), mapping, VALUES)))
    assert "geen echt document" not in plain.pages[0].extract_text()
