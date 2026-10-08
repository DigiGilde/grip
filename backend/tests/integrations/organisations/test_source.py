"""Reading the export of the public register."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import httpx
import pytest

from grip.integrations.organisations.source import (
    RegistryFormatError,
    RegistryUnavailableError,
    build_source_url,
    fetch_registry,
    iter_root_organisations,
)


def _roots(content: bytes):
    return {o.name: o for o in iter_root_organisations(BytesIO(content))}


def test_reads_top_level_organisations_with_their_parts(export_bytes):
    roots = _roots(export_bytes)

    assert len(roots) == 9
    ministry = roots["Voorbeeldzaken"]
    assert ministry.registry_id == "9001"
    assert (
        ministry.tooi_uri
        == "https://identifier.overheid.nl/tooi/id/ministerie/mnre9001"
    )
    assert ministry.abbreviations == ["VZ", "MinVZ"]
    assert [c.name for c in ministry.children] == [
        "Directoraat-Generaal Proefbeleid",
        "Directie Communicatie",
    ]
    assert [c.name for c in ministry.children[0].children] == [
        "Directie Fictieve Zaken"
    ]
    assert ministry.children[0].tooi_uri is None


def test_type_of_a_contact_is_not_a_type_of_the_organisation(export_bytes):
    assert _roots(export_bytes)["Voorbeeldzaken"].organisation_types == ["Ministerie"]


def test_ministry_gets_its_label_once(export_bytes):
    roots = _roots(export_bytes)

    assert roots["Voorbeeldzaken"].label == "Ministerie van Voorbeeldzaken"
    already = roots["Ministerie van Denkbeeldige Financiën"]
    assert already.label == "Ministerie van Denkbeeldige Financiën"


def test_related_ministry_and_types(export_bytes):
    authority = _roots(export_bytes)["Fictieve Autoriteit"]

    assert authority.organisation_types == [
        "Zelfstandig bestuursorgaan",
        "Adviescollege",
    ]
    assert authority.related_ministry_tooi == (
        "https://identifier.overheid.nl/tooi/id/ministerie/mnre9002"
    )


def test_end_date_passes_to_the_parts(export_bytes):
    ended = _roots(export_bytes)["Opgeheven Bureau"]

    assert ended.end_date == date(2020, 1, 1)
    assert ended.children[0].end_date == date(2020, 1, 1)


def test_excluded_organisations_are_recognised(export_bytes):
    roots = _roots(export_bytes)

    assert roots["Algemene Inlichtingen- en Veiligheidsdienst"].excluded
    assert not roots["Voorbeeldstad"].excluded


def test_public_page_url():
    assert build_source_url("9001", "Voorbeeld & Zaken (VZ)") == (
        "https://organisaties.overheid.nl/9001/Voorbeeld_Zaken_VZ/"
    )
    assert build_source_url("", "Zonder id") is None


def test_the_schema_version_in_the_namespace_does_not_matter(export_bytes):
    other = export_bytes.replace(b"/export/9.9.9", b"/export/2.6.13")

    assert len(_roots(other)) == 9


def test_another_document_is_refused(export_bytes):
    wrong = export_bytes.replace(
        b"https://organisaties.overheid.nl/static/schema/oo/export/9.9.9",
        b"https://example.org/iets/anders",
    )
    with pytest.raises(RegistryFormatError):
        _roots(wrong)
    with pytest.raises(RegistryFormatError):
        _roots(b"<html><body>Storing</body></html>")
    with pytest.raises(RegistryFormatError):
        _roots(b"geen xml")


async def test_fetch_returns_the_whole_document(export_bytes):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=export_bytes)
    )

    assert await fetch_registry(
        "https://register.example/export.xml", transport=transport
    ) == (export_bytes)


async def test_outage_and_error_status_are_reported():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("geen verbinding")

    with pytest.raises(RegistryUnavailableError, match="niets gewijzigd"):
        await fetch_registry(
            "https://register.example/x", transport=httpx.MockTransport(down)
        )
    error = httpx.MockTransport(lambda request: httpx.Response(503))
    with pytest.raises(RegistryUnavailableError, match="503"):
        await fetch_registry("https://register.example/x", transport=error)
