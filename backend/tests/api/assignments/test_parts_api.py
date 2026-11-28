"""What each reader gets from the rows of an assignment, over HTTP.

Each test reads the whole body, so a sentence of a class the reader may not see
fails it wherever in the answer that sentence turns up.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from grip.calc import Month
from grip.core import clock
from grip.federation.bridge.organisations import own_organisation
from grip.models.assignment import Assignment
from grip.models.stream_event import StreamEvent
from grip.services import (
    assignment_parts,
    assignments,
    month_close,
    quotes,
    rates,
)
from grip.services.overview_attention import CorrectionDue
from grip.services.reports.labels import day
from tests.lifecycle import accept

ORDER = ["close", "budget", "quote", "team", "report", "details", "history"]
ORG = {"name": "Voorbeeldministerie"}


@pytest.fixture(autouse=True)
def _april():
    with clock.at(datetime(2026, 4, 15, 12, 0, tzinfo=UTC)):
        yield


@pytest.fixture
async def running(world, db_session):
    """In progress, with a colleague in another scale and one who stops in
    September; the owner takes over that part of the role."""
    await accept(db_session, world.assignment.id)
    await assignments.transition(
        db_session,
        world.assignment.id,
        "in_progress",
        actor=world.owner,
        enforce_readiness=False,
    )
    world.colleague_allocation.end_date = date(2026, 9, 30)
    await rates.set_person_scale(
        db_session, world.owner.id, date(2026, 1, 1), 14, actor=world.beheerder
    )
    await assignments.add_allocation(
        db_session,
        world.line.id,
        world.owner.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("40"),
        actor=world.owner,
    )
    await db_session.flush()
    return world


def _url(world) -> str:
    return f"/api/assignments/{world.assignment.id}/parts"


async def _body(as_person, world, reader) -> dict:
    response = await as_person(reader).get(_url(world))
    assert response.status_code == 200, response.text
    return response.json()


def _said(body: dict) -> dict:
    return {part["key"]: part["notice"] for part in body["parts"]}


async def test_the_owner_gets_every_row_and_every_notice(running, as_person):
    body = await _body(as_person, running, running.owner)
    assert body["assignment_id"] == str(running.assignment.id)
    assert body["parts"] == [
        {
            "key": "close",
            "label": "Afsluiten en factureren",
            "notice": "3 maanden af te sluiten",
        },
        {
            "key": "budget",
            "label": "Begroting",
            "notice": "1 regel over de begroting",
        },
        {"key": "quote", "label": "Offerte", "notice": "Nog geen offerte"},
        {
            "key": "team",
            "label": "Team",
            "notice": "1 persoon in een andere schaal",
        },
        {
            "key": "details",
            "label": "Gegevens",
            "notice": "Eigenaar Eva Eigenaar",
        },
        {"key": "history", "label": "Geschiedenis", "notice": None},
    ]
    assert body["tasks_link"] is True
    assert body["own_line"] == "Productmanager, 40%, tot 31 dec 2026"


async def test_a_member_gets_no_date_of_another_and_no_scale(running, as_person):
    body = await _body(as_person, running, running.member)
    assert _said(body) == {
        "team": None,
        "details": "Eigenaar Eva Eigenaar",
        "history": None,
    }
    assert body["tasks_link"] is False
    assert body["own_line"] == "Productmanager, 50%, tot 31 dec 2026"
    text = json.dumps(body).lower()
    for word in ("open", "sep", "okt", "cas", "collega", "schaal", "regel", "maand"):
        assert word not in text


async def test_the_loader_reads_only_the_classes_it_is_given(running, db_session):
    from grip.access import DataClass

    basic, money_class, staffing_class = (
        DataClass.ASSIGNMENT_BASIC,
        DataClass.ASSIGNMENT_FINANCIAL,
        DataClass.STAFFING,
    )
    roster_class, signal_class = (
        DataClass.STAFFING_ROSTER,
        DataClass.RATE_MISMATCH_SIGNAL,
    )
    load = assignment_parts.load_facts

    roster = await load(db_session, running.assignment.id, {basic, roster_class})
    assert roster.has_personnel_line is True
    for fact in (
        roster.open_roles,
        roster.other_scale,
        roster.months,
        roster.budget,
        roster.quote,
        roster.billing,
        roster.report_issued,
    ):
        assert fact is None

    signal = await load(
        db_session, running.assignment.id, {basic, roster_class, signal_class}
    )
    assert signal.other_scale == 1
    assert signal.open_roles is None and signal.budget is None

    money = await load(db_session, running.assignment.id, {basic, money_class})
    assert money.budget is not None and money.months is not None
    assert money.open_roles is None and money.other_scale is None

    staffing = await load(db_session, running.assignment.id, {basic, staffing_class})
    assert staffing.open_roles is not None
    assert staffing.budget is None and staffing.other_scale is None


async def test_a_member_is_not_told_about_a_colleague_who_stops(
    running, as_person, db_session
):
    # With this stop, the role opens in October. The owner is told, the member not.
    await assignments.update_allocation(
        db_session,
        running.member_allocation.id,
        actor=running.owner,
        end_date=date(2026, 9, 30),
    )
    owner = await _body(as_person, running, running.owner)
    assert _said(owner)["team"].startswith("1 rol open")
    member = await _body(as_person, running, running.member)
    assert _said(member)["team"] is None
    assert member["own_line"] == "Productmanager, 50%, tot 30 sep 2026"


async def test_a_planner_gets_no_billing_period_and_no_amount(
    running, as_person, db_session
):
    for month in (1, 2, 3):
        await month_close.close_month(
            db_session,
            running.assignment.id,
            Month.of(date(2026, month, 1)),
            actor=running.owner,
        )
    owner = await _body(as_person, running, running.owner)
    assert _said(owner)["close"] == "Eerste kwartaal 2026 aan te leveren"

    body = await _body(as_person, running, running.planner)
    assert _said(body) == {
        "close": None,
        "team": "1 persoon in een andere schaal",
        "details": "Eigenaar Eva Eigenaar",
        "history": None,
    }
    # A planner may add and change tasks of the assignment, so gets the link.
    assert body["tasks_link"] is True
    assert body["own_line"] is None
    text = json.dumps(body, ensure_ascii=False).lower()
    for word in ("€", "kwartaal", "aan te leveren", "factuur", "regel", "offerte"):
        assert word not in text


async def test_a_planner_reads_how_many_months_are_to_be_closed(running, as_person):
    body = await _body(as_person, running, running.planner)
    assert body["parts"][0] == {
        "key": "close",
        "label": "Afsluiten",
        "notice": "3 maanden af te sluiten",
    }


async def test_the_row_is_there_as_soon_as_months_may_be_closed(
    world, as_person, db_session
):
    await accept(db_session, world.assignment.id)
    assert _said(await _body(as_person, world, world.owner))["close"] == (
        "3 maanden af te sluiten"
    )


async def test_a_lezer_gets_no_team(running, as_person):
    body = await _body(as_person, running, running.lezer)
    assert [part["key"] for part in body["parts"]] == [
        "close",
        "budget",
        "quote",
        "details",
        "history",
    ]
    assert _said(body)["budget"] == "1 regel over de begroting"
    assert body["tasks_link"] is False
    assert body["own_line"] is None
    text = json.dumps(body).lower()
    for word in ("rol", "schaal", "cas", "lot"):
        assert word not in text


async def test_a_beheerder_reads_all_and_edits_nothing(running, as_person):
    body = await _body(as_person, running, running.beheerder)
    assert list(_said(body)) == [
        "close",
        "budget",
        "quote",
        "team",
        "details",
        "history",
    ]
    assert body["tasks_link"] is False


async def test_nobody_gets_a_category_a_rate_or_an_amount(running, as_person):
    for reader in (
        running.owner,
        running.member,
        running.planner,
        running.lezer,
        running.beheerder,
    ):
        body = await _body(as_person, running, reader)
        text = json.dumps(body, ensure_ascii=False)
        for word in ("€", "cents", "categorie", "category", "tarief", "rate"):
            assert word not in text, reader.name
        # No amount as a bare number either: only the counts and dates above.
        assert "1800000" not in text
        assert "18.000" not in text


async def test_a_stranger_gets_404(world, as_person):
    response = await as_person(world.outsider).get(_url(world))
    assert response.status_code == 404


async def test_a_member_whose_inzet_ended_gets_404(world, as_person, db_session):
    world.member_allocation.end_date = date(2026, 3, 31)
    await db_session.flush()
    response = await as_person(world.member).get(_url(world))
    assert response.status_code == 404


async def test_an_assignment_that_does_not_exist_gets_404(world, as_person):
    response = await as_person(world.beheerder).get(f"/api/assignments/{uuid4()}/parts")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "status",
    [
        "draft",
        "requested",
        "quoted",
        "verbally_agreed",
        "rejected",
        "accepted",
        "in_progress",
        "completed",
        "accounted",
        "cancelled",
    ],
)
async def test_the_order_is_always_the_same(world, as_person, db_session, status):
    row = await db_session.get(Assignment, world.assignment.id)
    row.status = status
    await db_session.flush()
    for reader in (
        world.owner,
        world.member,
        world.planner,
        world.lezer,
        world.beheerder,
    ):
        keys = [
            part["key"] for part in (await _body(as_person, world, reader))["parts"]
        ]
        assert keys == [key for key in ORDER if key in keys]
        assert keys[-2:] == ["details", "history"]


async def test_reading_the_rows_writes_no_read_of_sensitive_data(
    running, as_person, db_session
):
    async def reads() -> int:
        await db_session.flush()
        return await db_session.scalar(
            select(func.count())
            .select_from(StreamEvent)
            .where(StreamEvent.type == "data.read")
        )

    before = await reads()
    for reader in (
        running.owner,
        running.member,
        running.planner,
        running.lezer,
        running.beheerder,
    ):
        await _body(as_person, running, reader)
    assert await reads() == before


async def test_a_potential_assignment(world, as_person):
    body = await _body(as_person, world, world.owner)
    assert _said(body) == {
        "budget": "2 regels",
        "quote": "Nog geen offerte",
        "team": "1 persoon in een andere schaal",
        "details": "Eigenaar Eva Eigenaar",
        "history": None,
    }


async def test_an_assignment_without_a_personnel_line_has_no_team(
    world, as_person, db_session
):
    other = world.other_assignment
    response = await as_person(world.beheerder).get(
        f"/api/assignments/{other.id}/parts"
    )
    assert [part["key"] for part in response.json()["parts"]] == [
        "budget",
        "quote",
        "details",
        "history",
    ]


async def test_an_internal_assignment(world, as_person, db_session):
    row = await db_session.get(Assignment, world.assignment.id)
    row.kind = "internal"
    row.status = "in_progress"
    await db_session.flush()
    for month in (1, 2, 3):
        await month_close.close_month(
            db_session,
            world.assignment.id,
            Month.of(date(2026, month, 1)),
            actor=world.owner,
        )
    body = await _body(as_person, world, world.owner)
    assert body["parts"][0] == {"key": "close", "label": "Afsluiten", "notice": None}
    assert "quote" not in _said(body)


async def test_a_correction_is_for_who_reads_money(
    running, as_person, monkeypatch, db_session
):
    async def due(_session, _assignment_id, _differences):
        return CorrectionDue(months=(date(2026, 1, 1),), amount_cents=1234, cause=None)

    monkeypatch.setattr(assignment_parts, "correction_due", due)
    for reader in (running.owner, running.lezer):
        said = _said(await _body(as_person, running, reader))
        assert said["close"] == "3 maanden af te sluiten, naverrekening aan te leveren"
    said = _said(await _body(as_person, running, running.planner))
    assert said["close"] == "3 maanden af te sluiten"


async def test_a_completed_assignment_still_owes_its_report(
    running, as_person, db_session
):
    await assignments.transition(
        db_session,
        running.assignment.id,
        "completed",
        actor=running.owner,
        enforce_readiness=False,
    )
    assert (
        _said(await _body(as_person, running, running.owner))["report"]
        == "Nog niet opgeleverd"
    )
    assert "report" not in _said(await _body(as_person, running, running.member))
    assert "report" not in _said(await _body(as_person, running, running.planner))

    await assignments.issue_final_report(
        db_session, running.assignment.id, {"summary": "Klaar"}, actor=running.owner
    )
    assert _said(await _body(as_person, running, running.owner))["report"] is None


async def test_the_quote_row_follows_the_quote(world, as_person, db_session):
    async def said() -> str | None:
        return _said(await _body(as_person, world, world.owner))["quote"]

    quote = await quotes.issue_quote(db_session, world.assignment.id, actor=world.owner)
    assert await said() == "Gemaakt, nog niet aangeboden"

    offer = await quotes.offer_quote(
        db_session, quote.id, "document", actor=world.owner
    )
    offered_on = day(clock.local_date(offer.offered_at))
    assert await said() == f"Bij de opdrachtgever sinds {offered_on}"

    await quotes.accept_quote(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name="Tess Teken",
        signer_email="teken@example.org",
        organisation=ORG,
        form="uploaded_pdf",
        document_sha256="0" * 64,
        document_ref="getekend.pdf",
        signed_at=datetime(2025, 12, 18, 10, 0, tzinfo=UTC),
        actor=world.owner,
    )
    assert await said() == "Getekend op 18 dec 2025"


async def test_a_rejected_quote_says_so(world, as_person, db_session):
    quote = await quotes.issue_quote(db_session, world.assignment.id, actor=world.owner)
    await quotes.offer_quote(db_session, quote.id, "document", actor=world.owner)
    await quotes.reject_quote(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        actor=world.owner,
        rejected_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    said = _said(await _body(as_person, world, world.owner))
    assert said["quote"] == "Afgewezen op 2 mrt 2026"


async def test_a_verbal_agreement_says_so(world, as_person, db_session):
    quote = await quotes.issue_quote(db_session, world.assignment.id, actor=world.owner)
    await quotes.offer_quote(db_session, quote.id, "document", actor=world.owner)
    row = await db_session.get(Assignment, world.assignment.id)
    row.status = "verbally_agreed"
    row.verbal_agreement_at = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
    await db_session.flush()
    said = _said(await _body(as_person, world, world.owner))
    assert said["quote"] == "Mondeling akkoord op 1 apr 2026"


@pytest.fixture
async def asked(world, db_session):
    """An assignment this instance asked another one for, as the client."""
    own = await own_organisation(db_session)
    contractor = await assignments.upsert_organisation(
        db_session, name="Voorbeeldleverancier"
    )
    assignment, _ = await assignments.create_assignment_request(
        db_session,
        name="Aanvraag Zeta 2026",
        contractor_organisation_id=contractor.id,
        client_organisation_id=own.id,
        actor=world.owner,
    )
    return assignment


async def test_is_client_tells_which_side_this_instance_is(world, asked, as_person):
    for reader in (world.owner, world.lezer, world.planner, world.beheerder):
        on_client_side = await as_person(reader).get(
            f"/api/assignments/{asked.id}/parts"
        )
        assert on_client_side.json()["is_client"] is True, reader.name
        on_own_side = await as_person(reader).get(_url(world))
        assert on_own_side.json()["is_client"] is False, reader.name


async def test_an_assignment_of_the_client_side_is_in_the_list(world, asked, as_person):
    for reader in (world.owner, world.lezer, world.planner, world.beheerder):
        listed = (await as_person(reader).get("/api/assignments")).json()
        assert str(asked.id) in [item["id"] for item in listed["items"]], reader.name


async def test_the_client_side_has_no_rows_for_the_work_of_the_contractor(
    world, asked, as_person, db_session
):
    url = f"/api/assignments/{asked.id}/parts"

    async def said(reader) -> dict:
        response = await as_person(reader).get(url)
        assert response.status_code == 200, response.text
        return response.json()

    expected = {
        "quote": "Nog geen offerte",
        "details": "Eigenaar Eva Eigenaar",
        "history": None,
    }
    assert _said(await said(world.owner)) == expected
    assert _said(await said(world.lezer)) == expected
    without_money = {key: expected[key] for key in ("details", "history")}
    assert _said(await said(world.planner)) == without_money

    line = await assignments.add_budget_line(
        db_session,
        asked.id,
        description="Regel",
        kind="fixed",
        amount_cents=100000,
        year=2026,
        actor=world.owner,
    )
    assert line is not None
    quote = await quotes.issue_quote(db_session, asked.id, actor=world.owner)
    received = day(clock.local_date(quote.created_at))
    assert _said(await said(world.owner))["quote"] == f"Ontvangen op {received}"

    row = await db_session.get(Assignment, asked.id)
    row.status = "completed"
    await db_session.flush()
    assert [part["key"] for part in (await said(world.owner))["parts"]] == [
        "quote",
        "details",
        "history",
    ]
