"""Fictional example data for a local development instance.

Run from ``backend/``::

    uv run python -m grip.dev.seed            # fill an empty database
    uv run python -m grip.dev.seed --reset    # empty the database first

or ``just seed`` and ``just seed --reset`` from the repo root.

Everything is invented and meant to look invented: the assignments carry the
names of the domain description (Opdracht Alfa 2026 and so on), people have
a surname that says what they are for, organisations and email addresses use
the reserved ``.example`` domain, and the amounts follow the worked examples
(category D bills 18,000 per month in 2026).

The data goes in through the service layer, so it is valid by construction
and the audit log is filled. Two things have no service yet and are written
directly, each with an audit row: creating a person and granting a function.

Acting as an example person
---------------------------
Local development has no identity provider (``DEV_NO_AUTH=1``). Every request
then runs as the first active beheerder, unless the browser sends the cookie
``grip_dev_person`` with the id of a person. The seed prints the ids. In the
browser console, on the frontend origin::

    document.cookie = "grip_dev_person=<id>; path=/"

and reload. Remove the cookie to be the beheerder again::

    document.cookie = "grip_dev_person=; path=/; max-age=0"

With curl: ``curl -b grip_dev_person=<id> http://localhost:8010/api/auth/status``.

The seed refuses to run when the database already holds assignments (pass
``reset=True`` or ``--reset`` to empty it first) and when the settings do not
describe a local development instance.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.core.bootstrap import (
    DEV_BEHEERDER_EMAIL,
    DEV_BEHEERDER_NAME,
    ensure_beheerder,
)
from grip.core.config import Settings, get_settings
from grip.core.database import Base
from grip.dev import corpus_standin
from grip.federation.contract_loader import SERVICE_CORPUS_CONTEXT
from grip.federation.models import PEER_ROLE_CORPUS, Peer
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.role import (
    AANVRAGER,
    BEHEERDER,
    LEZER,
    PLANNER,
    TEKENBEVOEGDE,
    PersonRole,
)
from grip.services import assignments, costs, month_close, quotes, rates
from grip.services.vacancies import service as vacancies

EMAIL_DOMAIN = "voorbeeld.example"

# Monthly rate per FTE in cents. Category D in 2026 is the worked example.
RATES: dict[int, dict[str, int]] = {
    2025: {"A": 1000000, "B": 1200000, "C": 1450000, "D": 1750000, "E": 2050000},
    2026: {"A": 1050000, "B": 1250000, "C": 1500000, "D": 1800000, "E": 2150000},
    2027: {"A": 1102500, "B": 1312500, "C": 1575000, "D": 1890000, "E": 2257500},
}
# Every category covers two scales.
SCALES: dict[int, str] = {
    8: "A",
    9: "A",
    10: "B",
    11: "B",
    12: "C",
    13: "C",
    14: "D",
    15: "D",
    16: "E",
    17: "E",
}
DRAFT_YEAR = 2028


@dataclass(frozen=True)
class ExamplePerson:
    key: str
    name: str
    scale: int
    manager: str | None = None
    functions: tuple[str, ...] = ()
    target_pct: int | None = None
    note: str = ""

    @property
    def email(self) -> str:
        return f"{self.key}@{EMAIL_DOMAIN}"


PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("bente.beheer", "Bente Beheer", 13, functions=(BEHEERDER,)),
    ExamplePerson(
        "pim.planner",
        "Pim Planner",
        13,
        functions=(PLANNER,),
        target_pct=50,
    ),
    ExamplePerson(
        "lotte.leiding",
        "Lotte Leiding",
        14,
        target_pct=50,
    ),
    ExamplePerson("lars.lezer", "Lars Lezer", 11, functions=(LEZER,)),
    ExamplePerson("anouk.aanvraag", "Anouk Aanvraag", 12, functions=(AANVRAGER,)),
    ExamplePerson("tess.teken", "Tess Teken", 15, functions=(TEKENBEVOEGDE,)),
    ExamplePerson(
        "priya.product",
        "Priya Product",
        14,
        manager="lotte.leiding",
        target_pct=80,
    ),
    ExamplePerson(
        "daan.developer", "Daan Developer", 11, manager="pim.planner", target_pct=90
    ),
    ExamplePerson(
        "dewi.developer",
        "Dewi Developer",
        11,
        manager="pim.planner",
        target_pct=90,
        note="schaal 12 vanaf juli 2026: declareert dan in een andere categorie",
    ),
    ExamplePerson(
        "olaf.ontwerp", "Olaf Ontwerp", 12, manager="pim.planner", target_pct=90
    ),
    ExamplePerson(
        "anna.analist", "Anna Analist", 12, manager="pim.planner", target_pct=90
    ),
    ExamplePerson(
        "sem.senior", "Sem Senior", 15, manager="lotte.leiding", target_pct=90
    ),
    ExamplePerson(
        "ilse.inhuur",
        "Ilse Inhuur",
        13,
        manager="lotte.leiding",
        target_pct=90,
        note="ingehuurd",
    ),
)


class SeedRefusedError(RuntimeError):
    """The seed will not run in this situation. The message says why."""


@dataclass
class SeedResult:
    people: dict[str, Person] = field(default_factory=dict)
    assignments: dict[str, Assignment] = field(default_factory=dict)
    # Budget lines the tests and the listing refer to, by a short key.
    lines: dict[str, UUID] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    relations: dict[str, list[str]] = field(default_factory=dict)

    def relate(self, key: str, what: str) -> None:
        self.relations.setdefault(key, []).append(what)


def ensure_local_instance(settings: Settings) -> None:
    """Refuse anything that is not a local development instance."""
    if not settings.DEV_NO_AUTH or settings.PUBLIC_HOST or settings.OIDC_ISSUER:
        raise SeedRefusedError(
            "Voorbeeldgegevens kunnen alleen in een lokale ontwikkelinstantie "
            "(DEV_NO_AUTH=1, zonder PUBLIC_HOST en zonder OIDC_ISSUER)."
        )


async def _assignment_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Assignment))).scalar_one()


async def reset_database(db: AsyncSession) -> None:
    """Empty every table except the functions that the migration seeded."""
    tables = [t.name for t in Base.metadata.sorted_tables if t.name != "role"]
    quoted = ", ".join(f'"{name}"' for name in tables)
    await db.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))


def _d(value: str) -> Decimal:
    return Decimal(value)


def _at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)


async def _rate_card(db: AsyncSession, year: int, actor: Person) -> None:
    await rates.create_rate_card(db, year, actor=actor)
    for category, cents in RATES[year].items():
        await rates.set_rate_band(db, year, category, cents, actor=actor)
    for scale, category in SCALES.items():
        await rates.set_scale_band(db, year, scale, category, actor=actor)
    await rates.set_rate_card_status(db, year, "active", actor=actor)


async def _people(db: AsyncSession, result: SeedResult) -> Person:
    """Create the example persons and their functions.

    There is no service for either yet, so these rows are written here, with
    an audit row each.
    """
    for example in PEOPLE:
        person = Person(name=example.name, email=example.email)
        db.add(person)
        await db.flush()
        record_audit(
            db,
            actor=None,
            action=CREATE,
            entity="person",
            entity_id=person.id,
            new_value={"email": example.email, "source": "seed"},
        )
        result.people[example.key] = person
    beheerder = result.people["bente.beheer"]
    for example in PEOPLE:
        person = result.people[example.key]
        if example.manager is not None:
            person.manager_id = result.people[example.manager].id
            result.relate(example.manager, f"leidinggevende van {example.name}")
        for function in example.functions:
            grant = PersonRole(
                person_id=person.id,
                role_id=function,
                start_date=date(2025, 1, 1),
                granted_by_id=None if person is beheerder else beheerder.id,
            )
            db.add(grant)
            await db.flush()
            record_audit(
                db,
                actor=None if person is beheerder else beheerder,
                action=CREATE,
                entity="person_role",
                entity_id=grant.id,
                new_value={
                    "person_id": str(person.id),
                    "role_id": function,
                    "source": "seed",
                },
            )
    await db.flush()
    return beheerder


async def _person_details(db: AsyncSession, result: SeedResult, actor: Person) -> None:
    for example in PEOPLE:
        person = result.people[example.key]
        if example.key == "dewi.developer":
            # A promotion halfway through the year: category B until June,
            # category C from July.
            await rates.set_person_scale(
                db,
                person.id,
                date(2025, 1, 1),
                11,
                actor=actor,
                valid_to=date(2026, 6, 30),
            )
            await rates.set_person_scale(
                db, person.id, date(2026, 7, 1), 12, actor=actor
            )
        else:
            await rates.set_person_scale(
                db, person.id, date(2025, 1, 1), example.scale, actor=actor
            )
        if example.target_pct is not None:
            for year in (2026, 2027):
                await rates.set_billability_target(
                    db, person.id, year, Decimal(example.target_pct), actor=actor
                )
    await rates.add_hire(
        db,
        result.people["ilse.inhuur"].id,
        supplier="Voorbeeld Detachering B.V.",
        cost_monthly_rate_cents=1350000,
        valid_from=date(2026, 3, 1),
        valid_to=date(2026, 12, 31),
        contract_reference="INH-26-001",
        notes="Fictieve inhuur voor Opdracht Beta 2026.",
        actor=actor,
    )


async def _roles(
    db: AsyncSession,
    result: SeedResult,
    assignment: Assignment,
    *,
    owner: str,
    manager: str | None,
    actor: Person,
) -> None:
    await assignments.set_assignment_role(
        db, assignment.id, result.people[owner].id, "owner", actor=actor
    )
    result.relate(owner, f"eigenaar van {assignment.name}")
    if manager is not None:
        await assignments.set_assignment_role(
            db, assignment.id, result.people[manager].id, "manager", actor=actor
        )
        result.relate(manager, f"manager van {assignment.name}")


async def _personnel(
    db: AsyncSession,
    assignment: Assignment,
    description: str,
    role: str,
    fte: str,
    category: str,
    start: date,
    end: date,
    actor: Person,
):
    return await assignments.add_budget_line(
        db,
        assignment.id,
        description=description,
        kind="personnel",
        role=role,
        fte=_d(fte),
        rate_category=category,
        start_date=start,
        end_date=end,
        actor=actor,
    )


async def _fixed(
    db: AsyncSession,
    assignment: Assignment,
    description: str,
    amount_cents: int,
    year: int,
    actor: Person,
):
    return await assignments.add_budget_line(
        db,
        assignment.id,
        description=description,
        kind="fixed",
        amount_cents=amount_cents,
        year=year,
        actor=actor,
    )


async def _allocate(
    db: AsyncSession,
    result: SeedResult,
    line,
    person: str,
    start: date,
    end: date,
    pct: str,
    actor: Person,
):
    result.counts["allocations"] = result.counts.get("allocations", 0) + 1
    return await assignments.add_allocation(
        db,
        line.id,
        result.people[person].id,
        start_date=start,
        end_date=end,
        fte_pct=_d(pct),
        actor=actor,
    )


async def _accept_by_pdf(
    db: AsyncSession, quote, organisation: dict, signer: str, day: date, actor: Person
) -> None:
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=signer,
        signer_email=f"opdrachtgever@{EMAIL_DOMAIN}",
        signer_function="Opdrachtgever (fictief)",
        organisation=organisation,
        form="uploaded_pdf",
        # Stands in for the hash of a signed document; there is no document.
        document_sha256="0" * 64,
        document_ref="voorbeeld/getekende-offerte.pdf",
        signed_at=_at(day),
        actor=actor,
    )


async def seed(
    db: AsyncSession, *, settings: Settings | None = None, reset: bool = False
) -> SeedResult:
    """Fill the database with the example data. The caller commits."""
    settings = settings or get_settings()
    ensure_local_instance(settings)
    if await _assignment_count(db):
        if not reset:
            raise SeedRefusedError(
                "De database bevat al opdrachten. Gebruik --reset om hem eerst "
                "leeg te maken; daarmee verdwijnen alle gegevens."
            )
        await reset_database(db)
    elif reset:
        await reset_database(db)

    result = SeedResult()
    # The stand-in beheerder of dev mode stays the default person.
    await ensure_beheerder(db, DEV_BEHEERDER_EMAIL, DEV_BEHEERDER_NAME)
    beheerder = await _people(db, result)

    for year in RATES:
        await _rate_card(db, year, beheerder)
    await rates.create_rate_card(db, DRAFT_YEAR, actor=beheerder, copy_from=2027)
    await _person_details(db, result, beheerder)

    ministry = await assignments.upsert_organisation(
        db,
        name="Voorbeeldministerie",
        tooi_uri=f"https://organisaties.{EMAIL_DOMAIN}/id/voorbeeldministerie",
    )
    agency = await assignments.upsert_organisation(
        db,
        name="Voorbeelddienst Uitvoering",
        tooi_uri=f"https://organisaties.{EMAIL_DOMAIN}/id/voorbeelddienst",
    )
    own = await assignments.upsert_organisation(
        db,
        name="Voorbeeldgilde",
        tooi_uri=f"https://organisaties.{EMAIL_DOMAIN}/id/voorbeeldorganisatie",
        unit_key="voorbeeldgilde",
        instance_uri=settings.INSTANCE_BASE_URI,
    )
    ministry_ref = {"name": ministry.name, "tooi_uri": ministry.tooi_uri}
    agency_ref = {"name": agency.name, "tooi_uri": agency.tooi_uri}

    priya = result.people["priya.product"]
    lotte = result.people["lotte.leiding"]

    # -- Opdracht Gamma 2025: completed, in a year that is closed afterwards --
    gamma = await assignments.create_assignment(
        db,
        name="Opdracht Gamma 2025",
        kind="external",
        traffic_form="document",
        client_organisation_id=agency.id,
        contractor_organisation_id=own.id,
        client_contact="Contactpersoon Voorbeelddienst",
        start_date=date(2025, 7, 1),
        end_date=date(2025, 12, 31),
        notes="Fictieve opdracht, afgerond in 2025.",
        actor=priya,
    )
    await _roles(
        db, result, gamma, owner="priya.product", manager=None, actor=beheerder
    )
    gamma_adviser = await _personnel(
        db,
        gamma,
        "Adviseur",
        "Adviseur",
        "1",
        "D",
        date(2025, 7, 1),
        date(2025, 12, 31),
        priya,
    )
    await _fixed(db, gamma, "Reiskosten", 250000, 2025, priya)
    quote = await quotes.issue_quote(
        db, gamma.id, actor=priya, issued_at=_at(date(2025, 6, 2))
    )
    await _accept_by_pdf(
        db, quote, agency_ref, "Opdrachtgever Voorbeelddienst", date(2025, 6, 16), priya
    )
    await assignments.transition(db, gamma.id, "in_progress", actor=priya)
    await _allocate(
        db,
        result,
        gamma_adviser,
        "sem.senior",
        date(2025, 7, 1),
        date(2025, 12, 31),
        "100",
        priya,
    )
    await assignments.transition(db, gamma.id, "completed", actor=priya)
    await assignments.issue_final_report(
        db,
        gamma.id,
        {
            "delivered": ["Advies over de inrichting van het voorbeeldproces"],
            "not_delivered": [],
            "summary": "Fictief eindrapport: alles is geleverd binnen de begroting.",
        },
        actor=priya,
    )
    await rates.set_rate_card_status(db, 2025, "closed", actor=beheerder)

    # -- Opdracht Alfa 2026 ---------------------------------------------------
    alfa = await assignments.create_assignment(
        db,
        name="Opdracht Alfa 2026",
        kind="external",
        traffic_form="document",
        client_organisation_id=ministry.id,
        contractor_organisation_id=own.id,
        client_contact="Contactpersoon Voorbeeldministerie",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        notes="Fictieve opdracht uit de domeinbeschrijving.",
        actor=priya,
    )
    await _roles(
        db, result, alfa, owner="priya.product", manager="pim.planner", actor=beheerder
    )
    year_2026 = (date(2026, 1, 1), date(2026, 12, 31))
    # 0.8 FTE in category D for twelve months: the worked example of R4.
    alfa_pm = await _personnel(
        db, alfa, "Productmanager", "Productmanager", "0.8", "D", *year_2026, priya
    )
    alfa_dev1 = await _personnel(
        db, alfa, "Developer #1", "Developer", "1", "B", *year_2026, priya
    )
    alfa_dev2 = await _personnel(
        db,
        alfa,
        "Developer #2 (vanaf Q2)",
        "Developer",
        "1",
        "B",
        date(2026, 4, 1),
        date(2026, 12, 31),
        priya,
    )
    alfa_design = await _personnel(
        db, alfa, "Ontwerper", "Ontwerper", "0.6", "C", *year_2026, priya
    )
    alfa_fixed = await _fixed(db, alfa, "Hosting en licenties", 3000000, 2026, priya)
    quote = await quotes.issue_quote(
        db,
        alfa.id,
        actor=priya,
        issued_at=_at(date(2025, 12, 8)),
        valid_until=date(2026, 1, 31),
    )
    await _accept_by_pdf(
        db,
        quote,
        ministry_ref,
        "Opdrachtgever Voorbeeldministerie",
        date(2025, 12, 18),
        priya,
    )
    await assignments.transition(db, alfa.id, "in_progress", actor=priya)
    await _allocate(db, result, alfa_pm, "priya.product", *year_2026, "80", priya)
    await _allocate(db, result, alfa_dev1, "daan.developer", *year_2026, "100", priya)
    # Dewi moves to category C in July while the line assumes B: an R14 signal.
    await _allocate(
        db,
        result,
        alfa_dev2,
        "dewi.developer",
        date(2026, 4, 1),
        date(2026, 12, 31),
        "100",
        priya,
    )
    # The designer leaves the role at the end of September: unfilled after that.
    olaf_alfa = await _allocate(
        db,
        result,
        alfa_design,
        "olaf.ontwerp",
        date(2026, 1, 1),
        date(2026, 9, 30),
        "60",
        priya,
    )
    await month_close.close_month(
        db, alfa.id, Month(2026, 1), actor=priya, closed_at=_at(date(2026, 2, 3))
    )
    # February deviates from the plan: the designer worked 40 instead of 60 percent.
    await month_close.close_month(
        db,
        alfa.id,
        Month(2026, 2),
        actor=priya,
        established={olaf_alfa.id: Decimal("40")},
        closed_at=_at(date(2026, 3, 3)),
    )
    result.counts["closed_months"] = 2

    # -- Opdracht Beta 2026 ---------------------------------------------------
    beta = await assignments.create_assignment(
        db,
        name="Opdracht Beta 2026",
        kind="external",
        traffic_form="document",
        client_organisation_id=agency.id,
        contractor_organisation_id=own.id,
        client_contact="Contactpersoon Voorbeelddienst",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 12, 31),
        notes="Fictieve opdracht uit de domeinbeschrijving.",
        actor=lotte,
    )
    await _roles(
        db, result, beta, owner="lotte.leiding", manager="pim.planner", actor=beheerder
    )
    beta_period = (date(2026, 3, 1), date(2026, 12, 31))
    beta_adviser = await _personnel(
        db, beta, "Adviseur", "Adviseur", "1", "D", *beta_period, lotte
    )
    beta_analyst = await _personnel(
        db, beta, "Analist", "Analist", "0.5", "C", *beta_period, lotte
    )
    beta_hire = await _personnel(
        db, beta, "Developer (inhuur)", "Developer", "1", "C", *beta_period, lotte
    )
    await _fixed(db, beta, "Opleiding en reiskosten", 750000, 2026, lotte)
    quote = await quotes.issue_quote(
        db, beta.id, actor=lotte, issued_at=_at(date(2026, 2, 2))
    )
    await _accept_by_pdf(
        db, quote, agency_ref, "Opdrachtgever Voorbeelddienst", date(2026, 2, 16), lotte
    )
    await assignments.transition(db, beta.id, "in_progress", actor=lotte)
    await _allocate(db, result, beta_adviser, "sem.senior", *beta_period, "100", lotte)
    await _allocate(db, result, beta_analyst, "anna.analist", *beta_period, "50", lotte)
    await _allocate(db, result, beta_hire, "ilse.inhuur", *beta_period, "100", lotte)

    # -- Opdracht Delta 2026-2027: runs across the year boundary --------------
    delta = await assignments.create_assignment(
        db,
        name="Opdracht Delta 2026-2027",
        kind="external",
        traffic_form="document",
        client_organisation_id=ministry.id,
        contractor_organisation_id=own.id,
        client_contact="Contactpersoon Voorbeeldministerie",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        notes="Fictieve opdracht die over de jaargrens loopt.",
        actor=priya,
    )
    await _roles(
        db, result, delta, owner="priya.product", manager=None, actor=beheerder
    )
    delta_period = (date(2026, 7, 1), date(2027, 6, 30))
    # Nobody is staffed on this line: the open role that became a vacancy.
    delta_dev = await _personnel(
        db, delta, "Developer", "Developer", "1", "B", *delta_period, priya
    )
    delta_analyst = await _personnel(
        db, delta, "Analist", "Analist", "0.5", "C", *delta_period, priya
    )
    delta_fixed_2026 = await _fixed(db, delta, "Hosting 2026", 1000000, 2026, priya)
    await _fixed(db, delta, "Hosting 2027", 1000000, 2027, priya)
    quote = await quotes.issue_quote(
        db, delta.id, actor=priya, issued_at=_at(date(2026, 6, 1))
    )
    signer_email = f"tekenaar.ministerie@{EMAIL_DOMAIN}"
    await quotes.invite_signer(db, quote.id, signer_email, actor=priya)
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name="Tekenaar Voorbeeldministerie",
        signer_email=signer_email,
        signer_function="Tekenbevoegde (fictief)",
        organisation=ministry_ref,
        form="signing_link",
    )
    await assignments.transition(db, delta.id, "in_progress", actor=priya)
    await _allocate(
        db, result, delta_analyst, "anna.analist", *delta_period, "50", priya
    )

    # -- Internal assignment --------------------------------------------------
    internal = await assignments.create_assignment(
        db,
        name="Interne opdracht Kennisdeling 2026",
        kind="internal",
        traffic_form="none",
        contractor_organisation_id=own.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        notes="Fictieve interne opdracht, betaald uit eigen middelen.",
        actor=lotte,
    )
    await _roles(
        db, result, internal, owner="lotte.leiding", manager=None, actor=beheerder
    )
    internal_line = await _personnel(
        db,
        internal,
        "Community en kennisdeling",
        "Ontwerper",
        "0.2",
        "C",
        *year_2026,
        lotte,
    )
    await _fixed(db, internal, "Bijeenkomsten", 500000, 2026, lotte)
    await assignments.transition(db, internal.id, "accepted", actor=lotte)
    await assignments.transition(db, internal.id, "in_progress", actor=lotte)
    await _allocate(db, result, internal_line, "olaf.ontwerp", *year_2026, "20", lotte)

    # -- Opdracht Epsilon 2027: quote issued, waiting for the client ----------
    epsilon = await assignments.create_assignment(
        db,
        name="Opdracht Epsilon 2027",
        kind="external",
        traffic_form="document",
        client_organisation_id=agency.id,
        contractor_organisation_id=own.id,
        client_contact="Contactpersoon Voorbeelddienst",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
        notes="Fictieve opdracht: de offerte ligt bij de opdrachtgever.",
        actor=lotte,
    )
    await _roles(
        db,
        result,
        epsilon,
        owner="lotte.leiding",
        manager="pim.planner",
        actor=beheerder,
    )
    year_2027 = (date(2027, 1, 1), date(2027, 12, 31))
    epsilon_pm = await _personnel(
        db, epsilon, "Productmanager", "Productmanager", "0.5", "D", *year_2027, lotte
    )
    await _personnel(
        db, epsilon, "Developer #1", "Developer", "1", "B", *year_2027, lotte
    )
    await _personnel(
        db, epsilon, "Developer #2", "Developer", "1", "B", *year_2027, lotte
    )
    await _fixed(db, epsilon, "Licenties", 600000, 2027, lotte)
    await quotes.issue_quote(
        db,
        epsilon.id,
        actor=lotte,
        issued_at=_at(date(2026, 10, 1)),
        valid_until=date(2026, 11, 30),
    )

    result.assignments = {
        "gamma": gamma,
        "alfa": alfa,
        "beta": beta,
        "delta": delta,
        "internal": internal,
        "epsilon": epsilon,
    }
    result.lines = {
        "alfa_productmanager": alfa_pm.id,
        "alfa_fixed": alfa_fixed.id,
        "alfa_designer": alfa_design.id,
        "delta_developer": delta_dev.id,
    }

    # -- Costs ----------------------------------------------------------------
    hosting = await costs.create_cost_item(
        db, description="Hostingcontract", budgeted_cents=1500000, actor=priya
    )
    for reference, kind, cents, period in (
        ("HOST-26-01", "actual", 375000, date(2026, 1, 1)),
        ("HOST-26-02", "actual", 375000, date(2026, 4, 1)),
        ("HOST-26-03", "estimate", 750000, date(2026, 10, 1)),
    ):
        await costs.add_invoice_line(
            db,
            hosting.id,
            kind=kind,
            amount_cents=cents,
            reference=reference,
            description="Hosting, fictief",
            period=period,
            actor=priya,
        )
    # 30 percent of a forecast of 15,000 is 4,500: the worked example of R7.
    # The item is covered by lines of two assignments; 20 percent stays uncovered.
    await costs.set_coverage(db, hosting.id, alfa_fixed.id, Decimal("30"), actor=priya)
    await costs.set_coverage(
        db, hosting.id, delta_fixed_2026.id, Decimal("50"), actor=priya
    )
    tooling = await costs.create_cost_item(
        db, description="Licenties ontwerptooling", budgeted_cents=600000, actor=priya
    )
    for reference, kind, cents, period in (
        ("LIC-26-01", "actual", 240000, date(2026, 2, 1)),
        ("LIC-26-02", "estimate", 360000, date(2026, 9, 1)),
    ):
        await costs.add_invoice_line(
            db,
            tooling.id,
            kind=kind,
            amount_cents=cents,
            reference=reference,
            description="Licenties, fictief",
            period=period,
            actor=priya,
        )
    await costs.set_coverage(db, tooling.id, alfa_fixed.id, Decimal("100"), actor=priya)
    result.counts["cost_items"] = 2
    result.counts["invoice_lines"] = 5
    result.counts["coverages"] = 3

    # -- Vacancies --------------------------------------------------------------
    tess = result.people["tess.teken"]

    async def decide(
        vacancy_id: UUID, kind: str, name: str, day: date, **kwargs
    ) -> None:
        await vacancies.record_decision(
            db,
            vacancy_id,
            kind,
            actor=priya,
            person_name=name,
            agreed=True,
            decided_on=day,
            **kwargs,
        )

    # 1. The open role on Delta: approved, with an established human text, open.
    open_role = await vacancies.create_vacancy_from_budget_line(
        db,
        actor=priya,
        budget_line_id=delta_dev.id,
        contract_type="temporary_before_permanent",
        fgr_function_name="Senior Medewerker ICT (fictief)",
        scale=11,
        addressee_name=tess.name,
    )
    await vacancies.submit_request(
        db, open_role.id, actor=priya, requested_on=date(2026, 9, 1)
    )
    await decide(open_role.id, "hr_advice", "Adviseur HR (fictief)", date(2026, 9, 3))
    await decide(
        open_role.id,
        "control_advice",
        "Adviseur concern control (fictief)",
        date(2026, 9, 4),
    )
    await decide(
        open_role.id, "approval", tess.name, date(2026, 9, 8), person_id=tess.id
    )
    motivation = await vacancies.add_text(
        db,
        open_role.id,
        "motivation",
        actor=priya,
        body=(
            "Fictief voorbeeld. Op Opdracht Delta 2026-2027 staat een "
            "begrotingsregel voor een developer van 1 FTE die sinds de start "
            "niet is ingevuld. Met deze vacature vullen we die rol in."
        ),
    )
    await vacancies.establish_text(db, motivation.id, actor=priya)
    vacancy_text = await vacancies.add_text(
        db,
        open_role.id,
        "vacancy_text",
        actor=priya,
        body=(
            "Fictieve vacaturetekst. Als developer bouw je mee aan een "
            "voorbeeldproduct voor het Voorbeeldministerie. Je werkt in een "
            "klein team, dicht op de gebruiker, en je hebt ervaring met het "
            "bouwen en beheren van webapplicaties."
        ),
    )
    await vacancies.establish_text(db, vacancy_text.id, actor=priya)
    await vacancies.publish_vacancy(
        db,
        open_role.id,
        actor=priya,
        channels=["internal"],
        opened_on=date(2026, 9, 21),
    )

    # 2. Not declarable, no budget line: requested, control has not decided yet.
    pending = await vacancies.create_vacancy(
        db,
        actor=lotte,
        function_title="Communicatieadviseur",
        fte=Decimal("0.6"),
        declarable=False,
        contract_type="temporary_project",
        fgr_function_name="Adviseur (fictief)",
        scale=11,
        addressee_name=tess.name,
    )
    await vacancies.submit_request(
        db, pending.id, actor=lotte, requested_on=date(2026, 10, 1)
    )
    await decide(pending.id, "hr_advice", "Adviseur HR (fictief)", date(2026, 10, 5))
    await vacancies.record_decision(
        db,
        pending.id,
        "control_advice",
        actor=lotte,
        person_name="Adviseur concern control (fictief)",
    )

    # 3. The designer role on Alfa that is unfilled from October: still a draft.
    await vacancies.create_vacancy_from_budget_line(
        db,
        actor=priya,
        budget_line_id=alfa_design.id,
        fgr_function_name="Medewerker Ontwerp (fictief)",
        scale=12,
        addressee_name=tess.name,
    )

    # 4. A ready candidate: approved, and never opened (separate procedure).
    ready = await vacancies.create_vacancy_from_budget_line(
        db,
        actor=lotte,
        budget_line_id=epsilon_pm.id,
        vacancy_type="gerede",
        contract_type="temporary_before_permanent",
        fgr_function_name="Coordinerend Adviseur (fictief)",
        scale=14,
        addressee_name=tess.name,
    )
    await vacancies.submit_request(
        db, ready.id, actor=lotte, requested_on=date(2026, 9, 14)
    )
    await decide(ready.id, "hr_advice", "Adviseur HR (fictief)", date(2026, 9, 16))
    await decide(
        ready.id,
        "control_advice",
        "Adviseur concern control (fictief)",
        date(2026, 9, 17),
    )
    await decide(ready.id, "approval", tess.name, date(2026, 9, 22), person_id=tess.id)
    result.counts["vacancies"] = 4

    result.counts.update(
        people=len(PEOPLE),
        rate_cards=len(RATES) + 1,
        assignments=len(result.assignments),
        organisations=3,
        hires=1,
    )
    await db.flush()
    extended = await extend(db, settings=settings)
    result.counts.update(corpus_peers=extended["peers"], context_refs=extended["refs"])
    return result


# The context of the example assignments: nodes of the fictional corpus that
# the stand-in serves (grip.dev.corpus_standin), as (corpus key, node key).
# The internal assignment has none: empty context is allowed.
CONTEXT: dict[str, tuple[tuple[str, str], ...]] = {
    # An instrument and the goal it implements: one chain.
    "Opdracht Alfa 2026": (
        ("voorbeeldministerie", "opdracht_alfa"),
        ("voorbeeldministerie", "doel_bouwstenen"),
    ),
    "Opdracht Beta 2026": (("voorbeeldministerie", "opdracht_beta"),),
    # One node from each corpus: the multi-corpus case.
    "Opdracht Delta 2026-2027": (
        ("voorbeeldministerie", "maatregel"),
        ("anderministerie", "opdracht_delta"),
    ),
    "Opdracht Epsilon 2027": (("voorbeeldministerie", "voorlichting"),),
}
# A draft left behind in the shared development database by a manual check.
STRAY_DRAFT_NAME = "s"


async def extend(
    db: AsyncSession, *, settings: Settings | None = None
) -> dict[str, int]:
    """Register the stand-in corpora and give the example assignments context.

    Idempotent, and safe on a database that was seeded earlier: it only adds
    what is missing. Part of a fresh seed as well. The caller commits.

    A peer has no service yet, so those rows are written here with an audit
    row; the context goes through ``assignments.update_assignment``.
    """
    settings = settings or get_settings()
    ensure_local_instance(settings)
    counts = {"peers": 0, "refs": 0, "changed": 0, "removed": 0}

    for corpus in corpus_standin.corpora():
        counts["peers"] += 1
        grants = {SERVICE_CORPUS_CONTEXT: corpus.grant_hash}
        peer = (
            await db.execute(select(Peer).where(Peer.peer_id == corpus.peer_id))
        ).scalar_one_or_none()
        if peer is None:
            peer = Peer(
                peer_id=corpus.peer_id,
                name=corpus.name,
                organisation_tooi_uri=corpus.organisation["tooi_uri"],
                base_uri=corpus.base,
                role=PEER_ROLE_CORPUS,
                grant_hashes=grants,
            )
            db.add(peer)
            await db.flush()
            record_audit(
                db,
                actor=None,
                action=CREATE,
                entity="peer",
                entity_id=peer.id,
                new_value={
                    "peer_id": corpus.peer_id,
                    "role": PEER_ROLE_CORPUS,
                    "base_uri": corpus.base,
                    "source": "seed",
                },
            )
            counts["changed"] += 1
        elif (
            peer.grant_hashes != grants
            or peer.base_uri != corpus.base
            or not peer.is_active
        ):
            peer.grant_hashes = grants
            peer.base_uri = corpus.base
            peer.is_active = True
            await db.flush()
            record_audit(
                db,
                actor=None,
                action=UPDATE,
                entity="peer",
                entity_id=peer.id,
                new_value={"base_uri": corpus.base, "source": "seed"},
            )
            counts["changed"] += 1

    for name, nodes in CONTEXT.items():
        refs = [corpus_standin.node_uri(corpus, node) for corpus, node in nodes]
        counts["refs"] += len(refs)
        assignment = (
            (
                await db.execute(
                    select(Assignment)
                    .where(Assignment.name == name)
                    .order_by(Assignment.created_at)
                )
            )
            .scalars()
            .first()
        )
        if assignment is None or list(assignment.context_refs or []) == refs:
            continue
        await assignments.update_assignment(
            db, assignment.id, actor=None, context_refs=refs
        )
        counts["changed"] += 1

    strays = (
        (
            await db.execute(
                select(Assignment).where(
                    Assignment.name == STRAY_DRAFT_NAME, Assignment.status == "draft"
                )
            )
        )
        .scalars()
        .all()
    )
    for stray in strays:
        record_audit(
            db,
            actor=None,
            action=DELETE,
            entity="assignment",
            entity_id=stray.id,
            old_value={"name": stray.name, "status": stray.status, "source": "seed"},
        )
        await db.delete(stray)
        counts["removed"] += 1
        counts["changed"] += 1
    await db.flush()
    return counts


def describe(result: SeedResult) -> str:
    """The example persons with their function and relations, for the terminal."""
    lines = ["Voorbeeldgegevens geladen.", ""]
    lines.append(", ".join(f"{k}: {v}" for k, v in sorted(result.counts.items())))
    lines.append("")
    lines.append("Personen (zet het id in de cookie grip_dev_person):")
    for example in PEOPLE:
        person = result.people[example.key]
        parts = [
            f"functie: {', '.join(example.functions)}" if example.functions else ""
        ]
        parts.extend(result.relations.get(example.key, []))
        if example.note:
            parts.append(example.note)
        detail = "; ".join(p for p in parts if p) or "medewerker"
        lines.append(f"  {person.id}  {example.name:<16} {detail}")
    lines.append("")
    lines.append(
        "Zonder cookie ben je de eerste actieve beheerder. Zie de docstring van "
        "grip.dev.seed voor het zetten van de cookie."
    )
    return "\n".join(lines)


async def _main(reset: bool, extend_only: bool) -> int:
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            try:
                if extend_only:
                    counts = await extend(db)
                else:
                    result = await seed(db, reset=reset)
            except SeedRefusedError as exc:
                print(f"Geweigerd: {exc}")
                return 1
            await db.commit()
        if extend_only:
            print(
                "Voorbeeldgegevens aangevuld: "
                f"{counts['peers']} corpora als peer, {counts['refs']} context-URI's "
                f"op de voorbeeldopdrachten, {counts['changed']} wijzigingen "
                f"(waarvan {counts['removed']} verwijderd)."
            )
        else:
            print(describe(result))
        return 0
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fictieve voorbeeldgegevens laden.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="maak de database eerst leeg (alle gegevens verdwijnen)",
    )
    parser.add_argument(
        "--extend",
        action="store_true",
        help=(
            "vul bestaande voorbeeldgegevens aan met het voorbeeldcorpus en de "
            "context van de opdrachten; herhaalbaar, verwijdert niets anders"
        ),
    )
    args = parser.parse_args()
    if args.reset and args.extend:
        parser.error("--reset en --extend gaan niet samen")
    raise SystemExit(asyncio.run(_main(args.reset, args.extend)))


if __name__ == "__main__":
    main()
