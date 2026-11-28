"""Example dataset ``programma``: a programme team with a budget of a ministry.

The instance is "MOZa voorbeeld", an example after the MOZa programme; its
people and amounts are invented. The Ministerie van BZK voorbeeld, its parent,
funds it from the GDI with one assignment, "MOZa voorbeeld 2026", whose budget
is the programme's budget for the year. That assignment runs between the two
instances: BZK holds the client's half in its own dataset, from the same
description (``grip.dev.datasets.chain``). The programme in its turn gives work to two
suppliers: the Voorbeeldgilde (which runs grip, instance "DigiGilde
voorbeeld") and the Voorbeeldbeheerorganisatie (which does not). What it
spends on them and on meetings and travel are cost items on its own budget.

Written for October 2026, with fixed years like the default dataset: January
to September are closed, some invoices are in and some are still expected.

Load it with ``SEED_DATASET=programma`` or ``just seed --dataset programma``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core.config import Settings
from grip.dev.datasets import chain
from grip.dev.seed import (
    EXAMPLE_TOOI,
    ExamplePerson,
    SeedResult,
    _allocate,
    _at,
    _people,
    _rate_card,
)
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.role import AANVRAGER, BEHEERDER, LEZER, PLANNER, TEKENBEVOEGDE
from grip.services import assignments, costs, month_close, quote_sender, quotes, rates
from grip.services.canonical import snapshot_hash

# The other instances of the local setup (deploy/local), by base URI. A peer
# is found by the instance URI of an organisation, so these must equal the
# base_uri that the FSC bootstrap registers for them. Deployed example
# instances name theirs in EXAMPLE_INSTANCE_URIS.
DIGIGILDE_INSTANCE_URI = chain.INSTANCES["digigilde"].local_uri
MINISTRY_INSTANCE_URI = chain.INSTANCES["ministerie"].local_uri

PROFILE = "programma"
YEARS = (2026, 2027)

PEOPLE: tuple[ExamplePerson, ...] = (
    ExamplePerson("bram.beheer", "Bram Beheer", None, functions=(BEHEERDER,)),
    ExamplePerson(
        "mila.programma",
        "Mila Programma",
        16,
        functions=(AANVRAGER, TEKENBEVOEGDE),
        note="programmamanager",
    ),
    ExamplePerson(
        "fenna.financien",
        "Fenna Financien",
        14,
        manager="mila.programma",
        functions=(PLANNER, LEZER),
        note="financieel adviseur en budgethouder",
    ),
    ExamplePerson(
        "pieter.product",
        "Pieter Product",
        14,
        manager="mila.programma",
        note="productowner",
    ),
    ExamplePerson(
        "dirk.dienstverlening",
        "Dirk Dienstverlening",
        12,
        manager="mila.programma",
        note="adviseur dienstverlening",
    ),
    ExamplePerson(
        "chantal.communicatie",
        "Chantal Communicatie",
        12,
        manager="mila.programma",
        note="communicatieadviseur",
    ),
)

# The executor is the organisation that books and pays an item and keeps it
# (ADR 0052). Here the item is a reference with a request that waits: the
# seed sends nothing, the worker does once the guild's grip is connected.
COST_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "key": "zaalhuur",
        "description": "Zaalhuur bijeenkomst ondernemers november",
        "budgeted_cents": 1200000,
        "line": "events",
        "executor": "guild",
        "period": date(2026, 11, 1),
        "lines": (),
    },
    {
        "key": "hotel",
        "description": "Hotelovernachtingen werksessie september",
        "budgeted_cents": 400000,
        "line": "events",
        "executor": None,
        "lines": (("HOTEL-26-09", "actual", 386400, date(2026, 9, 1)),),
    },
    {
        "key": "portaal",
        "description": "Ontwikkeling ondernemersportaal (Voorbeeldgilde)",
        "budgeted_cents": 41500000,
        "line": "suppliers",
        "executor": None,
        "lines": (
            ("VG-26-Q1", "actual", 4150000, date(2026, 3, 1)),
            ("VG-26-Q2", "actual", 12450000, date(2026, 6, 1)),
            ("VG-26-Q3", "estimate", 12450000, date(2026, 9, 1)),
            ("VG-26-Q4", "estimate", 12450000, date(2026, 12, 1)),
        ),
    },
    {
        "key": "beheer",
        "description": "Beheer en hosting (Voorbeeldbeheerorganisatie)",
        "budgeted_cents": 18000000,
        "line": "suppliers",
        "executor": None,
        "lines": (
            ("VBO-26-Q1", "actual", 4500000, date(2026, 3, 1)),
            ("VBO-26-Q2", "actual", 4500000, date(2026, 6, 1)),
            ("VBO-26-Q3", "actual", 4500000, date(2026, 9, 1)),
            ("VBO-26-Q4", "estimate", 4500000, date(2026, 12, 1)),
        ),
    },
)


def _ref(organisation: Organisation) -> dict[str, Any]:
    return {"name": organisation.name, "tooi_uri": organisation.tooi_uri}


async def _person_details(db: AsyncSession, result: SeedResult, actor: Person) -> None:
    for example in PEOPLE:
        if example.scale is not None:
            await rates.set_person_scale(
                db,
                result.people[example.key].id,
                date(2025, 1, 1),
                example.scale,
                actor=actor,
            )


async def _received(
    db: AsyncSession,
    *,
    name: str,
    contractor: Organisation,
    own: Organisation,
    parent: Assignment,
    period: tuple[date, date],
    lines: tuple[dict[str, Any], ...],
    issued: date,
    accepted: date,
    signer: Person,
) -> Assignment:
    """An assignment this instance gave, on a quote it received and accepted.

    The quote came in as a document and was typed over: the content is built
    from temporary budget lines on this side, then those lines go again, as
    the client side holds no budget of its own. The signed quote is recorded
    as a pdf, so nothing is exchanged with the contractor's instance.
    """
    assignment = await assignments.create_assignment(
        db,
        name=name,
        kind="external",
        client_organisation_id=own.id,
        contractor_organisation_id=contractor.id,
        parent_assignment_uri=parent.uri,
        start_date=period[0],
        end_date=period[1],
        notes=f"Fictieve opdracht van het programma aan {contractor.name}.",
        actor=signer,
    )
    temporary = [
        await assignments.add_budget_line(db, assignment.id, actor=signer, **line)
        for line in lines
    ]
    snapshot = await quotes.build_snapshot(
        db, assignment, valid_until=date(issued.year, issued.month, 28)
    )
    for line in temporary:
        await assignments.delete_budget_line(db, line.id, actor=signer)
    snapshot["sender"] = contractor.name
    quote = await quotes.receive_quote(
        db,
        assignment.id,
        quote_id=uuid.uuid4(),
        uri=f"urn:uuid:{uuid.uuid4()}",
        snapshot=snapshot,
        claimed_hash=snapshot_hash(snapshot),
        issued_at=_at(issued),
    )
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=signer.name,
        signer_email=signer.email or "",
        signer_function="Programmamanager (fictief)",
        signer_person_id=signer.id,
        organisation=_ref(own),
        form="uploaded_pdf",
        # Stands in for the hash of a signed document; there is no document.
        document_sha256="0" * 64,
        document_ref="voorbeeld/getekende-offerte-leverancier.pdf",
        signed_at=_at(accepted),
        actor=signer,
    )
    await assignments.transition(db, assignment.id, "in_progress", actor=signer)
    return assignment


async def fill(db: AsyncSession, settings: Settings) -> SeedResult:
    result = SeedResult(examples=PEOPLE)
    beheerder = await _people(db, result, PEOPLE)
    # The rates of the default dataset: the received quote of the
    # Voorbeeldgilde is priced on this card, so it matches that instance.
    for year in YEARS:
        await _rate_card(db, year, beheerder)
    await _person_details(db, result, beheerder)
    await quote_sender.apply_profile(db, PROFILE, actor=beheerder)

    # MOZa is a unit of the ministry: its TOOI URI plus a key of its own.
    rows = await chain.organisations(
        db, settings, ("ministerie", "programma", "digigilde"), own="programma"
    )
    ministry, own, guild = rows["ministerie"], rows["programma"], rows["digigilde"]
    operator = await assignments.upsert_organisation(
        db,
        name="Voorbeeldbeheerorganisatie",
        tooi_uri=f"{EXAMPLE_TOOI}/oorg/oorg99003",
    )
    executors = {"guild": guild}

    mila = result.people["mila.programma"]
    fenna = result.people["fenna.financien"]

    # -- The programme budget: MOZa voorbeeld 2026 ------------------------
    programme, lines = await chain.as_contractor(
        db,
        settings,
        chain.SHARED["programme"],
        own=own,
        client=ministry,
        owner=mila,
        manager=fenna,
        actor=beheerder,
    )
    result.relate("mila.programma", f"eigenaar van {programme.name}")
    result.relate("fenna.financien", f"manager van {programme.name}")
    year_2026 = (date(2026, 1, 1), date(2026, 12, 31))
    manager_line = lines["Programmamanager"]
    finance_line = lines["Financieel adviseur"]
    product_line = lines["Productowner"]
    service_line = lines["Adviseur dienstverlening"]
    communication_line = lines["Communicatieadviseur"]
    events_line = lines["Bijeenkomsten en reizen"]
    suppliers_line = lines["Opdrachten aan leveranciers"]
    for line, person, pct in (
        (manager_line, "mila.programma", "100"),
        (finance_line, "fenna.financien", "50"),
        (product_line, "pieter.product", "100"),
        (service_line, "dirk.dienstverlening", "100"),
    ):
        await _allocate(db, result, line, person, *year_2026, pct, mila)
    communication = await _allocate(
        db, result, communication_line, "chantal.communicatie", *year_2026, "60", mila
    )
    for month in range(1, 10):
        # May deviates from the plan: the communicatieadviseur worked 40
        # instead of 60 percent.
        established = {communication.id: Decimal("40")} if month == 5 else None
        await month_close.close_month(
            db,
            programme.id,
            Month(2026, month),
            actor=fenna,
            established=established,
            closed_at=_at(date(2026, month + 1, 3)),
        )
    result.counts["closed_months"] = 9

    # -- What the programme gives to suppliers ---------------------------------
    portal = await _received(
        db,
        name="Ontwikkeling ondernemersportaal 2026",
        contractor=guild,
        own=own,
        parent=programme,
        period=(date(2026, 3, 1), date(2026, 12, 31)),
        lines=tuple(
            {
                "description": description,
                "kind": "personnel",
                "role": role,
                "fte": Decimal(fte),
                "rate_category": category,
                "start_date": date(2026, 3, 1),
                "end_date": date(2026, 12, 31),
            }
            for description, role, fte, category in (
                ("Productmanager", "Productmanager", "0.5", "D"),
                ("Developers", "Developer", "2", "B"),
                ("Ontwerper", "Ontwerper", "0.5", "C"),
            )
        ),
        issued=date(2026, 2, 2),
        accepted=date(2026, 2, 12),
        signer=mila,
    )
    hosting = await _received(
        db,
        name="Beheer en hosting 2026",
        contractor=operator,
        own=own,
        parent=programme,
        period=year_2026,
        lines=(
            {
                "description": "Hosting",
                "kind": "fixed",
                "amount_cents": 12000000,
                "year": 2026,
            },
            {
                "description": "Beheer en monitoring",
                "kind": "fixed",
                "amount_cents": 6000000,
                "year": 2026,
            },
        ),
        issued=date(2025, 12, 1),
        accepted=date(2025, 12, 12),
        signer=mila,
    )

    # -- Costs ------------------------------------------------------------------
    covering = {"events": events_line, "suppliers": suppliers_line}
    for spec in COST_ITEMS:
        executor = executors[spec["executor"]] if spec["executor"] else None
        item = await costs.create_cost_item(
            db,
            description=spec["description"],
            budgeted_cents=spec["budgeted_cents"],
            executor_organisation_id=executor.id if executor else None,
            period=spec.get("period"),
            require_connection=False,
            actor=fenna,
        )
        for reference, kind, cents, period in spec["lines"]:
            await costs.add_invoice_line(
                db,
                item.id,
                kind=kind,
                amount_cents=cents,
                reference=reference,
                description="Fictief",
                period=period,
                actor=fenna,
            )
        await costs.set_coverage(
            db, item.id, covering[spec["line"]].id, Decimal("100"), actor=fenna
        )
    await db.flush()
    result.counts.update(
        cost_items=len(COST_ITEMS),
        invoice_lines=sum(len(spec["lines"]) for spec in COST_ITEMS),
        coverages=len(COST_ITEMS),
        requests=sum(1 for spec in COST_ITEMS if spec["executor"]),
    )

    result.assignments = {
        "programme": programme,
        "portal": portal,
        "hosting": hosting,
    }
    result.lines = {
        "programme_manager": manager_line.id,
        "events": events_line.id,
        "suppliers": suppliers_line.id,
    }
    result.counts.update(
        people=len(PEOPLE),
        rate_cards=len(YEARS),
        assignments=len(result.assignments),
        organisations=4,
    )
    # The roles of the budget lines became catalogue entries on the way.
    await db.execute(
        text("UPDATE catalogue_role SET needs_review = false WHERE needs_review")
    )
    return result
