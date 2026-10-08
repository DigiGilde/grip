"""Reads the organisation export of organisaties.overheid.nl.

Ported from the organisation sync of Wies (wies/core/services/organizations.py,
RijksICTGilde, licensed under the EUPL v. 1.2): which fields are read, how a
ministry gets its label, how an end date passes from an organisation to its
parts, how the public page URL is built, and which organisations are left
out. Changed here: the namespace is read from the document instead of being
fixed to one schema version, because the version in the namespace changes
with the export and a fixed one then reads zero organisations.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import IO

import httpx

REGISTRY_URL = "https://organisaties.overheid.nl/archive/exportOO.xml"
_NAMESPACE_PREFIX = "https://organisaties.overheid.nl/static/schema/oo/export/"

# Left out of the list (intelligence services), with everything below them.
# Compared without regard to case.
EXCLUDED_NAMES = frozenset(
    {
        "algemene inlichtingen- en veiligheidsdienst",
        "militaire inlichtingen- en veiligheidsdienst",
    }
)
EXCLUDED_ABBREVIATIONS = frozenset({"aivd", "mivd"})


class RegistryUnavailableError(RuntimeError):
    """The register could not be fetched."""


class RegistryFormatError(RuntimeError):
    """What came back is not the export this module can read."""


@dataclass
class RegistryOrganisation:
    name: str
    label: str
    registry_id: str
    tooi_uri: str | None
    abbreviations: list[str]
    organisation_types: list[str]
    related_ministry_tooi: str | None
    source_url: str | None
    end_date: date | None
    children: list[RegistryOrganisation] = field(default_factory=list)

    @property
    def excluded(self) -> bool:
        if self.name.strip().lower() in EXCLUDED_NAMES:
            return True
        return any(
            a.strip().lower() in EXCLUDED_ABBREVIATIONS for a in self.abbreviations
        )


def build_source_url(registry_id: str, name: str) -> str | None:
    """The public page of an organisation in the register."""
    if not registry_id:
        return None
    slug = re.sub(r"[^\w\-]", "_", name)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"https://organisaties.overheid.nl/{registry_id}/{slug}/"


def _namespace(tag: str) -> str:
    if not tag.startswith("{"):
        raise RegistryFormatError("De export heeft geen naamruimte.")
    namespace = tag[1 : tag.index("}")]
    if not namespace.startswith(_NAMESPACE_PREFIX):
        raise RegistryFormatError(
            "De export heeft een onbekende naamruimte; dit is niet de "
            "organisatie-export van organisaties.overheid.nl."
        )
    return namespace


def _parse(element: ET.Element, ns: str) -> RegistryOrganisation:
    def q(name: str) -> str:
        return f"{{{ns}}}{name}"

    name = (element.findtext(q("naam")) or "").strip()
    abbreviations = [
        a.text.strip()
        for a in element.findall(q("afkorting"))
        if a.text and a.text.strip()
    ]

    end_date: date | None = None
    raw_end = (element.findtext(q("eindDatum")) or "").strip()
    if raw_end:
        try:
            end_date = datetime.fromisoformat(raw_end).date()
        except ValueError:
            # An unreadable date is treated as no end date, as Wies does.
            end_date = None

    types = [
        t.text.strip()
        for t in element.findall(f"{q('types')}/{q('type')}")
        if t.text and t.text.strip()
    ]

    tooi = element.get(q("resourceIdentifierTOOI")) or None
    registry_id = element.get(q("systeemId")) or element.get("systeemId") or ""

    label = name
    if any(t.lower() == "ministerie" for t in types) and not name.startswith(
        "Ministerie"
    ):
        label = f"Ministerie van {name}"

    related = element.find(q("relatieMetMinisterie"))
    related_ministry_tooi = (
        related.get(q("resourceIdentifierTOOI")) or None
        if related is not None
        else None
    )

    children = []
    for child_element in element.findall(f"{q('organisaties')}/{q('organisatie')}"):
        child = _parse(child_element, ns)
        # A part does not outlive the organisation it belongs to.
        if end_date is not None and (
            child.end_date is None or child.end_date > end_date
        ):
            _set_end_date(child, end_date)
        children.append(child)

    return RegistryOrganisation(
        name=name,
        label=label,
        registry_id=registry_id,
        tooi_uri=tooi,
        abbreviations=abbreviations,
        organisation_types=types,
        related_ministry_tooi=related_ministry_tooi,
        source_url=build_source_url(registry_id, name),
        end_date=end_date,
        children=children,
    )


def _set_end_date(organisation: RegistryOrganisation, end_date: date) -> None:
    organisation.end_date = end_date
    for child in organisation.children:
        if child.end_date is None or child.end_date > end_date:
            _set_end_date(child, end_date)


def iter_root_organisations(xml_source: IO[bytes]) -> Iterator[RegistryOrganisation]:
    """Stream the top-level organisations, each with its parts nested.

    Parsed subtrees are dropped as soon as they are yielded, so memory stays
    bounded to one organisation instead of the whole export of 30+ MB.
    """
    # Input is the government's own export, not user input.
    context = ET.iterparse(xml_source, events=("start", "end"))  # noqa: S314
    namespace: str | None = None
    organisation_tag = ""
    wrapper_tag = ""
    wrapper: ET.Element | None = None
    depth = 0

    try:
        for event, element in context:
            if namespace is None:
                namespace = _namespace(element.tag)
                organisation_tag = f"{{{namespace}}}organisatie"
                wrapper_tag = f"{{{namespace}}}organisaties"
            if event == "start":
                if element.tag == wrapper_tag and wrapper is None:
                    wrapper = element
                if element.tag == organisation_tag:
                    depth += 1
                continue
            if element.tag != organisation_tag:
                continue
            depth -= 1
            if depth != 0:
                continue
            yield _parse(element, namespace)
            element.clear()
            if wrapper is not None:
                wrapper.remove(element)
    except ET.ParseError as exc:
        raise RegistryFormatError("De export is geen leesbare XML.") from exc

    if namespace is None:
        raise RegistryFormatError("De export is leeg.")


async def fetch_registry(
    url: str = REGISTRY_URL, *, transport: httpx.AsyncBaseTransport | None = None
) -> bytes:
    """Download the whole export before anything is changed.

    ``transport`` is for tests.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180, connect=20),
            follow_redirects=True,
            transport=transport,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise RegistryUnavailableError(
            "organisaties.overheid.nl is niet bereikbaar. Er is niets gewijzigd."
        ) from exc
    if response.status_code != httpx.codes.OK:
        raise RegistryUnavailableError(
            f"organisaties.overheid.nl gaf status {response.status_code}. "
            "Er is niets gewijzigd."
        )
    return response.content
