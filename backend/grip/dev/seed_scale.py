"""Fictional data at the size of a real organisation, to measure speed.

Run from ``backend/``::

    uv run python -m grip.dev.seed_scale            # fill an empty database
    uv run python -m grip.dev.seed_scale --reset    # empty the database first

or ``just seed-scale`` from the repo root. Refused outside a local
development instance, like the example seed.

The example seed has 8 assignments and 14 people. This one makes an
organisation of about 150 people over four years: 400 assignments in every
phase, their budget lines and inzet, every past month closed, billing
periods delivered and invoiced, vacancies, cost items, rate cards with a
change halfway a year, promotions, and the events all of that leaves.

Everything goes in through the service layer, so the data is valid by
construction: amounts are priced by ``grip.calc``, events and audit rows are
written by the services themselves and the hash chain of the stream is
real. Two things are not made the way a person would make them, both for
time: the PDF of a quote and of a factuurverzoek is laid out once and those
bytes are kept for every later one (laying out a thousand documents takes
longer than everything else together, and what is measured is that the file
does not travel with the row), and the reads of sensitive data that normal
use would have left are appended to the stream directly, through the same
``stream.append`` the request hook uses.

Deterministic: the same arguments give the same data, apart from ids and
the day it runs (what is "past" follows today).
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core import clock
from grip.core.audit import CREATE, record_audit
from grip.core.bootstrap import (
    DEV_BEHEERDER_EMAIL,
    DEV_BEHEERDER_NAME,
    ensure_beheerder,
)
from grip.core.config import Settings, get_settings
from grip.dev.seed import (
    EMAIL_DOMAIN,
    EXAMPLE_TOOI,
    SCALES,
    SeedRefusedError,
    ensure_local_instance,
    reset_database,
)
from grip.events import stream
from grip.models.assignment import Assignment, BudgetLine
from grip.models.person import Person
from grip.models.role import PersonRole
from grip.services import (
    assignments,
    billing_deliveries,
    billing_document,
    costs,
    month_close,
    quote_files,
    quotes,
    rates,
)
from grip.services.errors import DomainError
from grip.services.vacancies import service as vacancy_services

FIRST_YEAR = 2023
BASE_RATES = {"A": 950000, "B": 1150000, "C": 1380000, "D": 1670000, "E": 1950000}
YEARLY_INCREASE = Decimal("1.05")
ROLES = (
    ("Developer", "B"),
    ("Developer", "C"),
    ("Ontwerper", "C"),
    ("Analist", "C"),
    ("Adviseur", "D"),
    ("Productmanager", "D"),
    ("Product owner", "D"),
    ("Programmamanager", "E"),
)
FIRST_NAMES = (
    "Anna Bram Carla Daan Eva Finn Guus Hanna Ilse Joost Kim Lars Mila Niels Olaf "
    "Priya Quinten Roos Sem Tess Umar Vera Wout Xena Yara Zoe Bente Dewi Emre Fleur"
).split()
SURNAMES = (
    "Developer Ontwerp Analist Advies Product Planner Leiding Bouwer Tester "
    "Schrijver Onderzoek Architect Beheer Regie Proces"
).split()
CLIENTS = (
    "Voorbeeldministerie",
    "Voorbeelddienst Uitvoering",
    "Voorbeeldagentschap Noord",
    "Voorbeeldagentschap Zuid",
    "Voorbeeldinspectie",
    "Voorbeeldregister",
    "Voorbeeldraad",
    "Voorbeeldbureau Statistiek",
    "Voorbeelddienst Vergunningen",
    "Voorbeeldloket",
    "Voorbeeldfonds",
    "Voorbeeldautoriteit",
)
COST_KINDS = ("Hosting", "Licenties", "Onderzoek", "Training")
THEMES = (
    "Vergunningen Subsidies Toezicht Register Portaal Aanvragen Meldingen Inzage "
    "Archief Koppelvlak Dashboard Formulieren Regels Bouwstenen Notificaties"
).split()


@dataclass
class ScaleResult:
    counts: dict[str, int] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def skip(self, key: str) -> None:
        self.skipped[key] = self.skipped.get(key, 0) + 1


def _at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _month_end(day: date) -> date:
    return _add_months(_month_start(day), 1) - timedelta(days=1)


def _months(start: date, end: date) -> list[Month]:
    months = []
    day = _month_start(start)
    while day <= end:
        months.append(Month(day.year, day.month))
        day = _add_months(day, 1)
    return months


class _KeptPdf:
    """Lay a document out once and hand out the same bytes after that."""

    def __init__(self, render: Any) -> None:
        self._render = render
        self._bytes: bytes | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> bytes:
        if self._bytes is None:
            self._bytes = self._render(*args, **kwargs)
        return self._bytes


async def _people(db: AsyncSession, rng: random.Random, count: int) -> list[Person]:
    names = [f"{first} {last}" for last in SURNAMES for first in FIRST_NAMES]
    rng.shuffle(names)
    people = []
    for index, name in enumerate(names[:count]):
        local = name.lower().replace(" ", ".")
        person = Person(name=name, email=f"{local}.{index}@{EMAIL_DOMAIN}")
        db.add(person)
        people.append(person)
    await db.flush()
    for person in people:
        record_audit(
            db,
            actor=None,
            action=CREATE,
            entity="person",
            entity_id=person.id,
            new_value={"email": person.email, "source": "seed-scale"},
        )
    return people


async def _grant(db: AsyncSession, person: Person, function: str, by: Person) -> None:
    grant = PersonRole(
        person_id=person.id,
        role_id=function,
        start_date=date(FIRST_YEAR, 1, 1),
        granted_by_id=by.id,
    )
    db.add(grant)
    await db.flush()
    record_audit(
        db,
        actor=by,
        action=CREATE,
        entity="person_role",
        entity_id=grant.id,
        new_value={
            "person_id": str(person.id),
            "role_id": function,
            "source": "seed-scale",
        },
    )


async def _rate_cards(db: AsyncSession, actor: Person, last_year: int) -> None:
    amounts = dict(BASE_RATES)
    for year in range(FIRST_YEAR, last_year + 1):
        await rates.create_rate_card(db, year, actor=actor)
        for category, cents in amounts.items():
            await rates.set_rate_band(db, year, category, cents, actor=actor)
        for scale, category in SCALES.items():
            await rates.set_scale_band(db, year, scale, category, actor=actor)
        await rates.set_rate_card_status(db, year, "active", actor=actor)
        amounts = {
            category: int(Decimal(cents) * YEARLY_INCREASE / 100) * 100
            for category, cents in amounts.items()
        }


async def _midyear_card(db: AsyncSession, actor: Person, year: int) -> bool:
    """A card that starts on 1 July: rates change halfway a calendar year."""
    try:
        card = await rates.create_card(
            db,
            valid_from=date(year, 7, 1),
            valid_to=date(year, 12, 31),
            actor=actor,
            copy_previous=True,
        )
        for category in BASE_RATES:
            band = next(b for b in card.rate_bands if b.category == category)
            await rates.set_rate_band(
                db,
                card.id,
                category,
                int(band.monthly_rate_cents * Decimal("1.02") / 100) * 100,
                actor=actor,
            )
        await rates.set_rate_card_status(db, card.id, "active", actor=actor)
    except (DomainError, StopIteration, AttributeError, TypeError):
        await db.rollback()
        return False
    return True


@dataclass
class _Plan:
    name: str
    phase: str  # closed, running, potential
    start: date
    end: date
    client: int
    owner: int
    manager: int | None
    internal: bool = False


def _plans(rng: random.Random, today: date, total: int) -> list[_Plan]:
    running = round(total * 0.15)
    potential = round(total * 0.10)
    closed = total - running - potential
    this_month = _month_start(today)
    first = date(FIRST_YEAR, 1, 1)
    span = (this_month.year - first.year) * 12 + this_month.month - first.month
    plans: list[_Plan] = []

    def name(start: date, number: int) -> str:
        first, second = rng.choice(THEMES), rng.choice(THEMES).lower()
        return f"{first} {second} {start.year}-{number:03d}"

    for number in range(total):
        if number < closed:
            length = rng.randint(3, 14)
            begin = _add_months(first, rng.randint(0, max(0, span - length - 1)))
            end = _add_months(begin, length) - timedelta(days=1)
            phase = "closed"
        elif number < closed + running:
            begin = _add_months(this_month, -rng.randint(1, 10))
            end = _add_months(this_month, rng.randint(2, 10)) - timedelta(days=1)
            phase = "running"
        else:
            begin = _add_months(this_month, rng.randint(1, 5))
            end = _add_months(begin, rng.randint(3, 12)) - timedelta(days=1)
            phase = "potential"
        plans.append(
            _Plan(
                name=name(begin, number),
                phase=phase,
                start=begin,
                end=end,
                client=rng.randrange(len(CLIENTS)),
                owner=rng.randrange(25),
                manager=rng.randrange(3) if rng.random() < 0.6 else None,
                internal=rng.random() < 0.06,
            )
        )
    return plans


async def _assignment(
    db: AsyncSession,
    rng: random.Random,
    plan: _Plan,
    *,
    today: date,
    people: list[Person],
    owners: list[Person],
    planners: list[Person],
    beheerder: Person,
    clients: list[Any],
    own: Any,
    result: ScaleResult,
    fixed_lines: list[UUID],
    open_lines: list[UUID],
) -> None:
    owner = owners[plan.owner]
    client = clients[plan.client]
    assignment = await assignments.create_assignment(
        db,
        name=plan.name,
        kind="internal" if plan.internal else "external",
        traffic_form=None if plan.internal else "document",
        client_organisation_id=None if plan.internal else client.id,
        contractor_organisation_id=own.id,
        client_contact=None if plan.internal else f"Contactpersoon {client.name}",
        start_date=plan.start,
        end_date=plan.end,
        notes="Fictieve opdracht voor de snelheidsmeting.",
        actor=owner,
    )
    result.add("assignments")
    await assignments.set_assignment_role(
        db, assignment.id, owner.id, "owner", actor=beheerder
    )
    if plan.manager is not None and planners[plan.manager].id != owner.id:
        await assignments.set_assignment_role(
            db, assignment.id, planners[plan.manager].id, "manager", actor=beheerder
        )

    lines: list[BudgetLine] = []
    for index in range(rng.randint(2, 6)):
        role, category = rng.choice(ROLES)
        lines.append(
            await assignments.add_budget_line(
                db,
                assignment.id,
                description=f"{role} #{index + 1}",
                kind="personnel",
                role=role,
                fte=Decimal(rng.choice(["0.2", "0.4", "0.5", "0.6", "0.8", "1"])),
                rate_category=category,
                start_date=plan.start,
                end_date=plan.end,
                actor=owner,
            )
        )
    for index in range(rng.randint(1, 2)):
        fixed = await assignments.add_budget_line(
            db,
            assignment.id,
            description=rng.choice(
                ["Hosting en licenties", "Reiskosten", "Opleiding", "Onderzoek"]
            )
            + (f" {index + 1}" if index else ""),
            kind="fixed",
            amount_cents=rng.randrange(2, 40) * 100000,
            year=plan.start.year,
            actor=owner,
        )
        fixed_lines.append(fixed.id)
    result.add("budget_lines", len(lines) + 1)

    if plan.phase == "potential" and rng.random() < 0.4:
        open_lines.extend(line.id for line in lines[:1])
        return
    if plan.internal:
        await assignments.transition(db, assignment.id, "accepted", actor=owner)
    else:
        quote = await quotes.issue_quote(
            db,
            assignment.id,
            actor=owner,
            issued_at=_at(min(today, plan.start) - timedelta(days=40)),
        )
        result.add("quotes")
        if plan.phase == "potential":
            open_lines.extend(line.id for line in lines[:1])
            return
        await quotes.accept_quote(
            db,
            quote.id,
            quote_hash=quote.snapshot_hash,
            signer_name=f"Opdrachtgever {client.name}",
            signer_email=f"opdrachtgever@{EMAIL_DOMAIN}",
            signer_function="Opdrachtgever (fictief)",
            organisation={"name": client.name, "tooi_uri": client.tooi_uri},
            form="uploaded_pdf",
            document_sha256="0" * 64,
            document_ref="voorbeeld/getekende-offerte.pdf",
            signed_at=_at(min(today, plan.start) - timedelta(days=20)),
            actor=owner,
        )
    await assignments.transition(db, assignment.id, "in_progress", actor=owner)

    allocations = []
    for line in lines:
        if rng.random() < 0.12:
            open_lines.append(line.id)
            continue
        person = rng.choice(people)
        allocations.append(
            await assignments.add_allocation(
                db,
                line.id,
                person.id,
                start_date=plan.start,
                end_date=plan.end,
                fte_pct=(line.fte or Decimal("1")) * 100,
                actor=owner,
            )
        )
    result.add("allocations", len(allocations))

    last_past = _month_start(today) - timedelta(days=1)
    closable = _months(plan.start, min(plan.end, last_past))
    # A running assignment is a month or two behind, as in real use.
    if plan.phase == "running" and closable:
        closable = closable[: max(1, len(closable) - rng.randint(0, 2))]
    for month in closable:
        established = None
        if allocations and rng.random() < 0.05:
            chosen = rng.choice(allocations)
            established = {chosen.id: chosen.fte_pct * Decimal("0.5")}
        await month_close.close_month(
            db,
            assignment.id,
            month,
            actor=owner,
            established=established,
            closed_at=_at(_add_months(month.first_day, 1) + timedelta(days=3)),
        )
    result.add("closed_months", len(closable))

    if not plan.internal and closable:
        await billing_deliveries.set_terms(
            db,
            assignment.id,
            actor=owner,
            rhythm="month" if rng.random() < 0.3 else "quarter",
            details={
                "organisation": client.name,
                "address": "Voorbeeldstraat 1",
                "postcode_city": "1234 AB Voorbeeldstad",
                "reference": f"VB-{plan.start.year}-{rng.randrange(1000):03d}",
            },
        )
        state = await billing_deliveries.overview(db, assignment.id, today=today)
        number = 0
        for view in state.periods:
            if view.months_to_close or view.state not in (
                billing_deliveries.READY,
                getattr(billing_deliveries, "CORRECTION", billing_deliveries.READY),
            ):
                continue
            try:
                await billing_deliveries.deliver(
                    db, assignment.id, view.period.key, via="self", actor=owner
                )
            except DomainError:
                result.skip("deliveries")
                continue
            result.add("deliveries")
            if rng.random() < 0.9:
                number += 1
                fresh = await billing_deliveries.overview(
                    db, assignment.id, today=today
                )
                now = next(v for v in fresh.periods if v.period.key == view.period.key)
                try:
                    await billing_deliveries.record_invoice_for_period(
                        db,
                        assignment.id,
                        view.period.key,
                        invoice_number=f"F{plan.start.year}-{str(assignment.id)[:8]}-{number}",
                        invoice_date=today,
                        amount_cents=getattr(now, "delivered_cents", 0)
                        or getattr(now, "amount_cents", 0),
                        note=None,
                        actor=owner,
                        today=today,
                    )
                    result.add("invoices")
                except DomainError:
                    result.skip("invoices")

        # A few percent get a correction after delivery: a month reopened and
        # closed again with other facts.
        if allocations and rng.random() < 0.04:
            month = closable[0]
            try:
                await month_close.reopen_month(
                    db,
                    assignment.id,
                    month,
                    actor=beheerder,
                    reason="Fictieve correctie voor de snelheidsmeting.",
                )
                chosen = allocations[0]
                await month_close.close_month(
                    db,
                    assignment.id,
                    month,
                    actor=owner,
                    established={chosen.id: chosen.fte_pct * Decimal("0.75")},
                )
                result.add("corrections")
            except DomainError:
                result.skip("corrections")

    if plan.phase == "closed":
        await assignments.transition(db, assignment.id, "completed", actor=owner)
        if rng.random() < 0.5:
            await assignments.issue_final_report(
                db,
                assignment.id,
                {
                    "delivered": ["Fictief resultaat"],
                    "not_delivered": [],
                    "summary": "Fictief eindrapport voor de snelheidsmeting.",
                },
                actor=owner,
            )


async def _vacancies(
    db: AsyncSession,
    rng: random.Random,
    lines: list[UUID],
    owners: list[Person],
    approver: Person,
    count: int,
    result: ScaleResult,
) -> None:
    today = clock.today()
    for index, line_id in enumerate(lines[:count]):
        actor = owners[index % len(owners)]
        stage = index % 5
        try:
            vacancy = await vacancy_services.create_vacancy_from_budget_line(
                db,
                actor=actor,
                budget_line_id=line_id,
                contract_type="temporary_project",
                fgr_function_name="Medewerker (fictief)",
                scale=rng.choice([10, 11, 12, 13, 14]),
                addressee_name=approver.name,
            )
            result.add("vacancies")
            if stage >= 1:
                text = await vacancy_services.add_text(
                    db,
                    vacancy.id,
                    "motivation",
                    actor=actor,
                    body="Fictieve motivatie voor de snelheidsmeting.",
                )
                await vacancy_services.establish_text(db, text.id, actor=actor)
                await vacancy_services.submit_request(
                    db,
                    vacancy.id,
                    actor=actor,
                    requested_on=today - timedelta(days=60),
                )
            if stage >= 2:
                for kind, name in (
                    ("hr_advice", "Adviseur HR (fictief)"),
                    ("control_advice", "Adviseur concern control (fictief)"),
                ):
                    await vacancy_services.record_decision(
                        db,
                        vacancy.id,
                        kind,
                        actor=approver,
                        person_name=name,
                        agreed=True,
                        decided_on=today - timedelta(days=50),
                    )
                await vacancy_services.record_decision(
                    db,
                    vacancy.id,
                    "approval",
                    actor=approver,
                    person_name=approver.name,
                    person_id=approver.id,
                    agreed=True,
                    decided_on=today - timedelta(days=45),
                )
            if stage >= 3:
                text = await vacancy_services.add_text(
                    db,
                    vacancy.id,
                    "vacancy_text",
                    actor=actor,
                    body=(
                        "Fictieve vacaturetekst.\n\n## Dit ga je doen\n\n"
                        "Je bouwt mee aan een voorbeeldproduct.\n\n- samen\n- open"
                    ),
                )
                await vacancy_services.establish_text(db, text.id, actor=actor)
                await vacancy_services.publish_vacancy(
                    db,
                    vacancy.id,
                    actor=actor,
                    channels=["internal"],
                    opened_on=today - timedelta(days=30),
                )
            await db.commit()
        except DomainError:
            await db.rollback()
            result.skip("vacancies")


async def _cost_items(
    db: AsyncSession,
    rng: random.Random,
    fixed_lines: list[UUID],
    owners: list[Person],
    count: int,
    result: ScaleResult,
) -> None:
    today = clock.today()
    for index in range(count):
        actor = owners[index % len(owners)]
        budget = rng.randrange(5, 60) * 100000
        try:
            item = await costs.create_cost_item(
                db,
                description=f"{rng.choice(COST_KINDS)} {index + 1:03d}",
                budgeted_cents=budget,
                actor=actor,
            )
            for part in range(rng.randint(2, 4)):
                past = part < 2
                await costs.add_invoice_line(
                    db,
                    item.id,
                    kind="actual" if past else "estimate",
                    amount_cents=budget // 4,
                    reference=f"KP-{index + 1:03d}-{part + 1}",
                    description="Fictieve factuur",
                    period=_add_months(_month_start(today), -6 + part * 3),
                    actor=actor,
                )
                result.add("invoice_lines")
            share = rng.choice([30, 50, 80, 100])
            await costs.set_coverage(
                db, item.id, rng.choice(fixed_lines), Decimal(share), actor=actor
            )
            result.add("cost_items")
            await db.commit()
        except DomainError:
            await db.rollback()
            result.skip("cost_items")


async def _reads(
    db: AsyncSession, rng: random.Random, people: list[Person], count: int
) -> None:
    """The reads of sensitive data that daily use would have left."""
    batch = 2000
    for done in range(0, count, batch):
        for _ in range(min(batch, count - done)):
            reader = rng.choice(people)
            if rng.random() < 0.5:
                about = rng.choice(people)
                stream.append(
                    db,
                    "data.read",
                    subject=("person", about.id),
                    person_id=about.id,
                    actor_person_id=reader.id,
                    new={"classes": ["person_rate"]},
                    purpose="GET /api/people/{id}",
                    existence_class="person_rate",
                    field_classes={"*": "person_rate"},
                )
            else:
                seen = rng.sample(people, k=min(40, len(people)))
                stream.append(
                    db,
                    "data.read",
                    subject=("data", "list"),
                    actor_person_id=reader.id,
                    new={"classes": ["person_rate"], "persons": len(seen)},
                    payload={"person_ids": [str(p.id) for p in seen]},
                    purpose="GET /api/people",
                    existence_class=None,
                    field_classes={"*": None},
                )
        await db.commit()


async def seed_scale(
    *,
    settings: Settings | None = None,
    reset: bool = False,
    people_count: int = 150,
    assignment_count: int = 400,
    vacancy_count: int = 150,
    cost_item_count: int = 300,
    read_count: int = 300000,
    random_seed: int = 2026,
) -> ScaleResult:
    from grip.core.database import async_session

    settings = settings or get_settings()
    ensure_local_instance(settings)
    rng = random.Random(random_seed)
    result = ScaleResult()
    today = clock.today()
    quote_files.render_quote_pdf = _KeptPdf(quote_files.render_quote_pdf)
    billing_document.render_pdf = _KeptPdf(billing_document.render_pdf)

    def lap(key: str, started: float) -> float:
        now = time.monotonic()
        result.seconds[key] = round(now - started, 1)
        print(f"  {key}: {result.seconds[key]} s", flush=True)
        return now

    async with async_session() as db:
        existing = (
            await db.execute(select(func.count()).select_from(Assignment))
        ).scalar_one()
        if existing:
            if not reset:
                raise SeedRefusedError(
                    "De database bevat al opdrachten. Gebruik --reset om hem eerst "
                    "leeg te maken; daarmee verdwijnen alle gegevens."
                )
            await reset_database(db)
        elif reset:
            await reset_database(db)
        started = time.monotonic()
        beheerder = await ensure_beheerder(db, DEV_BEHEERDER_EMAIL, DEV_BEHEERDER_NAME)
        people = await _people(db, rng, people_count)
        owners = people[:25]
        planners = people[25:28]
        leads = people[30:42]
        for planner in planners:
            await _grant(db, planner, "planner", beheerder)
        for lezer in people[28:30]:
            await _grant(db, lezer, "lezer", beheerder)
        await _grant(db, people[42], "offertegoedkeurder", beheerder)
        for index, person in enumerate(people[43:]):
            person.manager_id = leads[index % len(leads)].id
        await db.commit()
        result.add("people", len(people))

        await _rate_cards(db, beheerder, today.year + 2)
        await db.commit()
        if await _midyear_card(db, beheerder, today.year - 1):
            await db.commit()
            result.add("midyear_cards")
        for person in people:
            scale = rng.choice([9, 10, 11, 12, 13, 14, 15])
            first_day = date(FIRST_YEAR, 1, 1)
            if rng.random() < 0.15:
                change = date(rng.randint(FIRST_YEAR + 1, today.year), 7, 1)
                await rates.set_person_scale(
                    db,
                    person.id,
                    first_day,
                    scale,
                    actor=beheerder,
                    valid_to=change - timedelta(days=1),
                )
                await rates.set_person_scale(
                    db, person.id, change, scale + 1, actor=beheerder
                )
                result.add("promotions")
            else:
                await rates.set_person_scale(
                    db, person.id, first_day, scale, actor=beheerder
                )
            if rng.random() < 0.7:
                for year in (today.year - 1, today.year):
                    await rates.set_billability_target(
                        db, person.id, year, Decimal("80"), actor=beheerder
                    )
        await db.commit()
        started = lap("people and rates", started)

        clients = []
        for index, name in enumerate(CLIENTS):
            clients.append(
                await assignments.upsert_organisation(
                    db, name=name, tooi_uri=f"{EXAMPLE_TOOI}/oorg/oorg98{index:03d}"
                )
            )
        own = await assignments.upsert_organisation(
            db,
            name="Voorbeeldgilde",
            tooi_uri=f"{EXAMPLE_TOOI}/oorg/oorg99002",
            unit_key="voorbeeldgilde",
            instance_uri=settings.INSTANCE_BASE_URI,
        )
        await db.commit()

        fixed_lines: list[UUID] = []
        open_lines: list[UUID] = []
        plans = _plans(rng, today, assignment_count)
        for number, plan in enumerate(plans, start=1):
            try:
                await _assignment(
                    db,
                    rng,
                    plan,
                    today=today,
                    people=people,
                    owners=owners,
                    planners=planners,
                    beheerder=beheerder,
                    clients=clients,
                    own=own,
                    result=result,
                    fixed_lines=fixed_lines,
                    open_lines=open_lines,
                )
                await db.commit()
            except DomainError as exc:
                await db.rollback()
                result.skip("assignments")
                print(f"  overgeslagen: {plan.name}: {exc}", flush=True)
            if number % 25 == 0:
                print(f"  {number} van {len(plans)} opdrachten", flush=True)
        started = lap("assignments", started)

        rng.shuffle(open_lines)
        await _vacancies(db, rng, open_lines, owners, beheerder, vacancy_count, result)
        started = lap("vacancies", started)
        if fixed_lines:
            await _cost_items(db, rng, fixed_lines, owners, cost_item_count, result)
        started = lap("cost items", started)
        await _reads(db, rng, people, read_count)
        result.add("reads", read_count)
        started = lap("reads", started)

    from grip.tasks import backfill

    outcome = await backfill.run()
    result.counts["task_outcome"] = getattr(outcome, "created", 0)
    lap("tasks", started)
    return result


def describe(result: ScaleResult) -> str:
    lines = ["Gegevens op ware grootte geladen:"]
    lines += [f"  {key}: {value}" for key, value in sorted(result.counts.items())]
    if result.skipped:
        lines.append("Overgeslagen (door een regel van het domein geweigerd):")
        lines += [f"  {key}: {value}" for key, value in sorted(result.skipped.items())]
    lines.append(f"Duur: {round(sum(result.seconds.values()))} seconden")
    return "\n".join(lines)


async def _main(args: argparse.Namespace) -> int:
    from grip.core.database import close_db

    try:
        try:
            result = await seed_scale(
                reset=args.reset,
                people_count=args.people,
                assignment_count=args.assignments,
                vacancy_count=args.vacancies,
                cost_item_count=args.cost_items,
                read_count=args.reads,
            )
        except SeedRefusedError as exc:
            print(f"Geweigerd: {exc}")
            return 1
        print(describe(result))
        return 0
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fictieve gegevens op ware grootte laden, voor de snelheidsmeting."
    )
    parser.add_argument(
        "--reset", action="store_true", help="maak de database eerst leeg"
    )
    parser.add_argument("--people", type=int, default=150)
    parser.add_argument("--assignments", type=int, default=400)
    parser.add_argument("--vacancies", type=int, default=150)
    parser.add_argument("--cost-items", type=int, default=300, dest="cost_items")
    parser.add_argument("--reads", type=int, default=300000)
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
