"""The example chain: the seven example instances and what runs between them.

Not a dataset (it is not in ``NAMES``). Each example instance fills itself on
its own, from its own dataset. An assignment between two of them must then be
the same on both sides: the client mints its URI, the contractor finds the
row by the last part of that URI and answers only when it is shared with the
caller. One description here, with fixed uuids, is what makes the two sides
agree; ``tests/dev/test_chain.py`` keeps them so.

Organisations carry their real name with "voorbeeld"; the TOOI codes are
invented. A unit that is not registered itself has the TOOI URI of the
organisation above it plus a key of its own (docs/organisaties.md).

This module imports nothing from ``grip.dev.seed``, which imports it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.core.config import Settings
from grip.models.assignment import Assignment, BudgetLine
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.services import assignments, quotes
from grip.services.canonical import snapshot_hash
from grip.services.pricing import DEFAULT_OPTIONS
from grip.services.quote_content import QuoteLineSource, check_content

TOOI = "https://identifier.overheid.nl/tooi/id"
EMAIL_DOMAIN = "voorbeeld.example"


@dataclass(frozen=True)
class Instance:
    # The key in EXAMPLE_INSTANCE_URIS.
    key: str
    # The organisation as the datasets name it.
    name: str
    tooi_uri: str
    unit_key: str | None
    # The base URI in the local setup (deploy/local), when the setting does
    # not name one.
    local_uri: str
    dataset: str
    parent: str | None = None


INSTANCES: dict[str, Instance] = {
    instance.key: instance
    for instance in (
        Instance(
            "gdi",
            "GDI voorbeeld",
            f"{TOOI}/oorg/oorg99004",
            None,
            "http://localhost:9005",
            "gdi",
        ),
        Instance(
            "ministerie",
            "Ministerie van BZK voorbeeld",
            f"{TOOI}/ministerie/mnre9001",
            None,
            "http://localhost:9002",
            "bzk",
        ),
        Instance(
            "programma",
            "MOZa voorbeeld",
            f"{TOOI}/ministerie/mnre9001",
            "programma",
            "http://localhost:9003",
            "programma",
            parent="ministerie",
        ),
        Instance(
            "odi",
            "ODI voorbeeld",
            f"{TOOI}/oorg/oorg99002",
            None,
            "http://localhost:9006",
            "odi",
        ),
        # The name of the default dataset: an instance is recognised by its
        # instance URI, not by its name.
        Instance(
            "digigilde",
            "Voorbeeldgilde",
            f"{TOOI}/oorg/oorg99002",
            "voorbeeldgilde",
            "http://localhost:9001",
            "voorbeeld",
            parent="odi",
        ),
        Instance(
            "ezk",
            "Ministerie van EZK voorbeeld",
            f"{TOOI}/ministerie/mnre9002",
            None,
            "http://localhost:9007",
            "ezk",
        ),
        Instance(
            "nldd",
            "NLDD voorbeeld",
            f"{TOOI}/ministerie/mnre9002",
            "nldd",
            "http://localhost:9004",
            "nldd",
            parent="ezk",
        ),
    )
}


def base_uri(settings: Settings, key: str, *, own: str) -> str:
    """The base URI of an instance as the instance ``own`` knows it."""
    if key == own:
        return settings.INSTANCE_BASE_URI.rstrip("/")
    return settings.example_instance_uris.get(key, INSTANCES[key].local_uri)


async def organisations(
    db: AsyncSession, settings: Settings, keys: Iterable[str], *, own: str
) -> dict[str, Organisation]:
    """The rows of these instances, each with its parent when that is one of them."""
    wanted = list(keys)
    # A parent before its child, so the child can name it.
    ordered = sorted(
        wanted, key=lambda key: 1 if INSTANCES[key].parent in wanted else 0
    )
    rows: dict[str, Organisation] = {}
    for key in ordered:
        instance = INSTANCES[key]
        parent = rows.get(instance.parent) if instance.parent else None
        rows[key] = await assignments.upsert_organisation(
            db,
            name=instance.name,
            tooi_uri=instance.tooi_uri,
            unit_key=instance.unit_key,
            instance_uri=base_uri(settings, key, own=own),
            parent_id=parent.id if parent is not None else None,
        )
    return rows


@dataclass(frozen=True)
class Line:
    description: str
    kind: str
    role: str | None = None
    fte: str | None = None
    category: str | None = None
    start: date | None = None
    end: date | None = None
    amount_cents: int | None = None
    year: int | None = None

    def budget_line(self) -> dict[str, Any]:
        """The arguments of ``assignments.add_budget_line``."""
        if self.kind == "fixed":
            return {
                "description": self.description,
                "kind": "fixed",
                "amount_cents": self.amount_cents,
                "year": self.year,
            }
        return {
            "description": self.description,
            "kind": "personnel",
            "role": self.role,
            "fte": Decimal(self.fte or "0"),
            "rate_category": self.category,
            "start_date": self.start,
            "end_date": self.end,
        }


@dataclass(frozen=True)
class Shared:
    """An assignment between two example instances."""

    key: str
    # The last part of its URI, which the client mints.
    id: UUID
    name: str
    client: str
    contractor: str
    start: date
    end: date
    lines: tuple[Line, ...]
    issued: date
    valid_until: date
    accepted: date
    # The key of the shared assignment this one falls under.
    parent: str | None = None
    notes: str = ""
    extra: Mapping[str, str] = field(default_factory=dict)


def _personnel(
    description: str, role: str, fte: str, category: str, start: date, end: date
) -> Line:
    return Line(description, "personnel", role, fte, category, start, end)


def _fixed(description: str, cents: int, year: int) -> Line:
    return Line(description, "fixed", amount_cents=cents, year=year)


_2026 = (date(2026, 1, 1), date(2026, 12, 31))
_NLDD = (date(2026, 8, 1), date(2027, 7, 31))

SHARED: dict[str, Shared] = {
    shared.key: shared
    for shared in (
        # GDI approves the programme and leaves the commissioning to BZK.
        Shared(
            "delegation",
            UUID("7c1f4a52-2b0e-4d1b-9a77-0e5b6c1d2a01"),
            "Gedelegeerd opdrachtgeverschap MOZa voorbeeld 2026",
            client="gdi",
            contractor="ministerie",
            start=_2026[0],
            end=_2026[1],
            lines=(
                _fixed("Programmabudget MOZa voorbeeld 2026", 158_000_000, 2026),
                _fixed("Uitvoering via ODI voorbeeld 2026", 30_000_000, 2026),
            ),
            issued=date(2025, 10, 20),
            valid_until=date(2025, 11, 30),
            accepted=date(2025, 11, 10),
            notes=(
                "Fictief: GDI voorbeeld keurt het programma MOZa voorbeeld goed en "
                "legt het opdrachtgeverschap bij het Ministerie van BZK voorbeeld."
            ),
        ),
        # The programme budget: BZK funds MOZa, from the GDI.
        Shared(
            "programme",
            UUID("7c1f4a52-2b0e-4d1b-9a77-0e5b6c1d2a02"),
            "MOZa voorbeeld 2026",
            client="ministerie",
            contractor="programma",
            start=_2026[0],
            end=_2026[1],
            lines=(
                _personnel("Programmamanager", "Programmamanager", "1", "E", *_2026),
                _personnel(
                    "Financieel adviseur", "Financieel adviseur", "0.5", "D", *_2026
                ),
                _personnel("Productowner", "Productowner", "1", "D", *_2026),
                _personnel("Adviseur dienstverlening", "Adviseur", "1", "C", *_2026),
                _personnel(
                    "Communicatieadviseur", "Communicatieadviseur", "0.6", "C", *_2026
                ),
                _fixed("Bijeenkomsten en reizen", 6_000_000, 2026),
                _fixed("Opdrachten aan leveranciers", 65_000_000, 2026),
            ),
            issued=date(2025, 11, 17),
            valid_until=date(2025, 12, 31),
            accepted=date(2025, 12, 11),
            parent="delegation",
            notes=(
                "Voorbeeldprogramma, gefinancierd uit de GDI door het Ministerie van "
                "BZK voorbeeld."
            ),
        ),
        # BZK gives ODI the execution; ODI has it done by DigiGilde, which
        # is not in grip yet.
        Shared(
            "execution",
            UUID("7c1f4a52-2b0e-4d1b-9a77-0e5b6c1d2a03"),
            "Uitvoering MOZa voorbeeld 2026",
            client="ministerie",
            contractor="odi",
            start=_2026[0],
            end=_2026[1],
            lines=(
                _fixed("Inzet DigiGilde voorbeeld via ODI voorbeeld", 30_000_000, 2026),
            ),
            issued=date(2025, 12, 1),
            valid_until=date(2025, 12, 31),
            accepted=date(2025, 12, 15),
            parent="programme",
            notes=(
                "Fictief: ODI voorbeeld is opdrachtnemer en contractpartij en laat "
                "het werk uitvoeren door DigiGilde voorbeeld."
            ),
        ),
        Shared(
            "fundament",
            UUID("7c1f4a52-2b0e-4d1b-9a77-0e5b6c1d2a04"),
            "Fundament 2026-2027",
            client="nldd",
            contractor="digigilde",
            start=_NLDD[0],
            end=_NLDD[1],
            lines=(
                _personnel("Productmanager", "Productmanager", "0.2", "D", *_NLDD),
                _personnel("Platformengineer #1", "Platformengineer", "1", "C", *_NLDD),
                _personnel("Platformengineer #2", "Platformengineer", "1", "C", *_NLDD),
                _fixed("Hosting testomgeving 2026", 500_000, 2026),
                _fixed("Hosting testomgeving 2027", 700_000, 2027),
            ),
            issued=date(2026, 7, 6),
            valid_until=date(2026, 7, 31),
            accepted=date(2026, 7, 20),
            notes="Fictieve opdracht van NLDD voorbeeld aan Voorbeeldgilde.",
        ),
        Shared(
            "regelrecht",
            UUID("7c1f4a52-2b0e-4d1b-9a77-0e5b6c1d2a05"),
            "RegelRecht 2026-2027",
            client="nldd",
            contractor="digigilde",
            start=_NLDD[0],
            end=_NLDD[1],
            lines=(
                _personnel("Juridisch analist", "Juridisch analist", "1", "C", *_NLDD),
                _personnel("Developer #1", "Developer", "1", "B", *_NLDD),
                _personnel("Developer #2 (inhuur)", "Developer", "1", "C", *_NLDD),
            ),
            issued=date(2026, 7, 6),
            valid_until=date(2026, 7, 31),
            accepted=date(2026, 7, 20),
            notes="Fictieve opdracht van NLDD voorbeeld aan Voorbeeldgilde.",
        ),
    )
}


def assignment_uri(settings: Settings, shared: Shared, *, own: str) -> str:
    return f"{base_uri(settings, shared.client, own=own)}/id/opdracht/{shared.id}"


def parent_uri(settings: Settings, shared: Shared, *, own: str) -> str | None:
    if shared.parent is None:
        return None
    return assignment_uri(settings, SHARED[shared.parent], own=own)


def rate_book(rates: Mapping[int, Mapping[str, int]], scales: Mapping[int, str]):
    """The rate cards of the default dataset as the calculation module reads them.

    The client side holds no rate card: it prices the lines of a received
    quote with this, so they come out as the contractor issued them.
    """
    return calc.RateBook(
        cards=tuple(
            calc.RateCard(
                valid_from=date(year, 1, 1),
                valid_to=date(year, 12, 31),
                status=calc.RateCardStatus.ACTIVE,
                rate_bands=tuple(
                    calc.RateBand(category=category, monthly_rate_cents=cents)
                    for category, cents in bands.items()
                ),
                scale_bands=tuple(
                    calc.ScaleBand(scale=scale, category=category)
                    for scale, category in scales.items()
                ),
                name=f"Tarieven {year}",
            )
            for year, bands in rates.items()
        )
    )


def priced(shared: Shared, book: calc.RateBook) -> dict[str, Any]:
    """Lines, subtotals and total of the quote, priced without a database."""
    placeholder = uuid.uuid5(uuid.NAMESPACE_URL, str(shared.id))
    sources = []
    for position, line in enumerate(shared.lines, start=1):
        values = line.budget_line()
        sources.append(
            QuoteLineSource(
                id=uuid.uuid5(placeholder, str(position)),
                assignment_id=placeholder,
                position=position,
                description=line.description,
                kind=line.kind,
                role=values.get("role"),
                fte=values.get("fte"),
                rate_category=values.get("rate_category"),
                start_date=values.get("start_date"),
                end_date=values.get("end_date"),
                amount_cents=values.get("amount_cents"),
                year=values.get("year"),
            )
        )
    return quotes.budget_part(sources, book, DEFAULT_OPTIONS)


def _at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)


def _ref(organisation: Organisation) -> dict[str, Any]:
    return {"name": organisation.name, "tooi_uri": organisation.tooi_uri}


async def as_client(
    db: AsyncSession,
    settings: Settings,
    shared: Shared,
    *,
    own: Organisation,
    contractor: Organisation,
    owner: Person,
    signer: Person,
    signer_function: str,
    book: calc.RateBook,
) -> Assignment:
    """The client's side: the assignment it gave, on the quote it signed.

    The quote came in as a signed document, typed over: the client side keeps
    no budget of the contractor, and nothing goes out to the contractor's
    instance, which holds its own side.
    """
    me = shared.client
    assignment = await assignments.create_assignment(
        db,
        name=shared.name,
        kind="external",
        client_organisation_id=own.id,
        contractor_organisation_id=contractor.id,
        parent_assignment_uri=parent_uri(settings, shared, own=me),
        start_date=shared.start,
        end_date=shared.end,
        notes=shared.notes,
        actor=owner,
        uri=assignment_uri(settings, shared, own=me),
    )
    await assignments.share_with_instance(
        db, assignment, base_uri(settings, shared.contractor, own=me)
    )
    snapshot = check_content(
        {
            "name": shared.name,
            "context_refs": [],
            **priced(shared, book),
            "valid_until": shared.valid_until.isoformat(),
            "sender": contractor.name,
        }
    )
    quote = await quotes.receive_quote(
        db,
        assignment.id,
        quote_id=uuid.uuid4(),
        uri=f"urn:uuid:{uuid.uuid4()}",
        snapshot=snapshot,
        claimed_hash=snapshot_hash(snapshot),
        issued_at=_at(shared.issued),
    )
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=signer.name,
        signer_email=signer.email or "",
        signer_function=signer_function,
        signer_person_id=signer.id,
        organisation=_ref(own),
        form="uploaded_pdf",
        # Stands in for the hash of a signed document; there is no document.
        document_sha256="0" * 64,
        document_ref="voorbeeld/getekende-offerte-opdrachtnemer.pdf",
        signed_at=_at(shared.accepted),
        actor=signer,
    )
    await assignments.transition(db, assignment.id, "in_progress", actor=signer)
    return assignment


async def as_contractor(
    db: AsyncSession,
    settings: Settings,
    shared: Shared,
    *,
    own: Organisation,
    client: Organisation,
    owner: Person,
    manager: Person | None,
    actor: Person,
) -> tuple[Assignment, dict[str, BudgetLine]]:
    """The contractor's side, up to in progress: the request came in from the
    client's instance, so it is shared with that instance as real traffic
    would make it; the quote was issued here and signed on paper.

    Returns the assignment and its budget lines by description, for the
    dataset to staff and close months on.
    """
    me = shared.contractor
    assignment = await assignments.receive_assignment_request(
        db,
        uri=assignment_uri(settings, shared, own=me),
        name=shared.name,
        client_organisation_id=client.id,
        contractor_organisation_id=own.id,
        description=shared.notes,
        parent_assignment_uri=parent_uri(settings, shared, own=me),
        start_date=shared.start,
        end_date=shared.end,
    )
    await assignments.set_assignment_role(
        db, assignment.id, owner.id, "owner", actor=actor
    )
    if manager is not None:
        await assignments.set_assignment_role(
            db, assignment.id, manager.id, "manager", actor=actor
        )
    lines = {
        line.description: await assignments.add_budget_line(
            db, assignment.id, actor=owner, **line.budget_line()
        )
        for line in shared.lines
    }
    quote = await quotes.issue_quote(
        db,
        assignment.id,
        actor=owner,
        issued_at=_at(shared.issued),
        valid_until=shared.valid_until,
    )
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=f"Opdrachtgever {client.name}",
        signer_email=f"opdrachtgever@{EMAIL_DOMAIN}",
        signer_function="Opdrachtgever (fictief)",
        organisation=_ref(client),
        form="uploaded_pdf",
        # Stands in for the hash of a signed document; there is no document.
        document_sha256="0" * 64,
        document_ref="voorbeeld/getekende-offerte.pdf",
        signed_at=_at(shared.accepted),
        actor=owner,
    )
    await assignments.transition(db, assignment.id, "in_progress", actor=owner)
    return assignment, lines
