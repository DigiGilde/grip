"""The restricted text form of a quote's prose, and how it becomes HTML.

A person writes the sections of a quote as plain text with a small set of
marks. It is stored as that text, frozen with the quote and covered by the
fingerprint, so what is signed is the text itself and not a rendering of it.

The marks:

- a blank line separates paragraphs;
- a line that starts with ``- `` is an item of a bulleted list;
- a line that starts with ``1. `` (any number) is an item of a numbered list;
- a line that starts with ``### `` is a small heading inside the section;
- ``**tekst**`` is strong, ``*tekst*`` is emphasis.

Nothing else has a meaning. There is no HTML: every character is escaped
when the text is rendered, so a ``<`` is a ``<`` on paper.

Pure functions, no database.
"""

from __future__ import annotations

import re
from html import escape

MAX_SECTION_CHARS = 20000

_BULLET = re.compile(r"^\s*[-•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
_SUBHEADING = re.compile(r"^\s*###\s+(.*)$")
_STRONG = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_EMPHASIS = re.compile(r"(?<![*\w])\*(?=\S)(.+?)(?<=\S)\*(?![*\w])")
# Characters that have no place in a text for print.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ProseError(ValueError):
    """The text cannot be part of a quote. The message is for the writer."""


def clean(text: str | None) -> str:
    """The text as it is stored: line ends unified, outer whitespace gone."""
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ProseError("Een tekst van een offerte is tekst.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if _CONTROL.search(text):
        raise ProseError("De tekst bevat tekens die niet kunnen worden afgedrukt.")
    if len(text) > MAX_SECTION_CHARS:
        raise ProseError(
            f"De tekst is te lang: hooguit {MAX_SECTION_CHARS} tekens per onderdeel."
        )
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _inline(text: str) -> str:
    out = escape(text, quote=False)
    out = _STRONG.sub(r"<strong>\1</strong>", out)
    return _EMPHASIS.sub(r"<em>\1</em>", out)


def to_html(text: str) -> str:
    """The text as HTML blocks: paragraphs, lists and small headings."""
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_tag = ""

    def close_paragraph() -> None:
        if paragraph:
            blocks.append("<p>" + "<br>".join(paragraph) + "</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if items:
            body = "".join(f"<li>{item}</li>" for item in items)
            blocks.append(f"<{list_tag}>{body}</{list_tag}>")
            items.clear()
        list_tag = ""

    for raw in clean(text).split("\n"):
        if not raw.strip():
            close_paragraph()
            close_list()
            continue
        heading = _SUBHEADING.match(raw)
        bullet = _BULLET.match(raw)
        numbered = _NUMBERED.match(raw)
        if heading:
            close_paragraph()
            close_list()
            blocks.append(f"<h3>{_inline(heading.group(1))}</h3>")
        elif bullet or numbered:
            close_paragraph()
            tag = "ul" if bullet else "ol"
            if list_tag and list_tag != tag:
                close_list()
            list_tag = tag
            match = bullet or numbered
            assert match is not None
            items.append(_inline(match.group(1)))
        elif items and raw.startswith((" ", "\t")):
            # A continuation line of the item above.
            items[-1] += " " + _inline(raw.strip())
        else:
            close_list()
            paragraph.append(_inline(raw.strip()))
    close_paragraph()
    close_list()
    return "\n".join(blocks)


def find_names(text: str, names: list[str]) -> list[str]:
    """The names from ``names`` that occur in the text, ignoring case and spacing.

    Names shorter than five characters are skipped: they would match
    ordinary words.
    """
    haystack = " ".join(text.split()).casefold()
    found: list[str] = []
    for name in names:
        needle = " ".join(name.split()).casefold()
        if len(needle) >= 5 and needle in haystack:
            found.append(name)
    return found
