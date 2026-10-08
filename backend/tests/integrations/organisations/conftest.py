"""Fixtures for the organisation register. Every organisation is fictional."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "export.xml"
TODAY = date(2026, 10, 8)
MINISTRY_TOOI = "https://identifier.overheid.nl/tooi/id/ministerie/mnre9001"
AGENCY_TOOI = "https://identifier.overheid.nl/tooi/id/oorg/oorg99001"
# Organisations in the fixture that are current and not excluded.
EXPECTED_CREATED = 11


@pytest.fixture
def export_bytes() -> bytes:
    return FIXTURE.read_bytes()


def without(content: bytes, registry_id: str) -> bytes:
    """The export with one top-level organisation (and its parts) taken out."""
    text = content.decode()
    start = text.index(f'<p:organisatie p:systeemId="{registry_id}"')
    depth = 0
    position = start
    while True:
        opening = text.find("<p:organisatie ", position)
        closing = text.find("</p:organisatie>", position)
        if opening != -1 and opening < closing:
            depth += 1
            position = opening + 1
        else:
            depth -= 1
            position = closing + len("</p:organisatie>")
            if depth == 0:
                break
    return (text[:start] + text[position:]).encode()
