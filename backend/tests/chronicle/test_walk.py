"""The path of an assignment, walked for real and looked back at.

Every test goes through the routes as the roles that do it. After each step the
rows equal the fold; afterwards each look-back says what was seen live at that
step. All names and amounts are fictional.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy import inspect as sa_inspect

from grip.chronicle import ledger
from grip.chronicle.effects import Insert
from grip.chronicle.facts import effects_of
from grip.chronicle.verify import differences
from grip.chronicle.writer import MODELS, columns_of
from grip.core import clock
from grip.core.config import get_settings
from grip.dev import chronicle_walk
from grip.dev.seed import EMAIL_DOMAIN
from grip.events import stream
from grip.federation import signing
from grip.federation.bridge import register_bridge
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.bridge.settings import get_bridge_settings
from grip.federation.registry import clear_registries
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.role import PersonRole
from grip.repositories.chronicle import ChronicleRepository
from grip.services import assignments, quote_approval, quote_channels, rates
from grip.services.chronicle import _allocations
from grip.tasks.handlers import register_task_handlers
from tests.chronicle.walking import (
    PDF_BYTES,
    YEAR,
    Walk,
    add_rate_card,
    day,
    line_body,
    make_cast,
)
from tests.federation.conftest import (
    CLIENT_BASE,
    CLIENT_PEER_ID,
    CONTRACTOR_PEER_ID,
    as_peer,
    example,
    t,
)

BUDGET = 1800000 * 6  # 0.5 FTE in category D for twelve months
FEDERATED_ASSIGNMENT_ID = "3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f61"


@pytest.fixture(autouse=True)
def _handlers():
    # Other test files clear them: a step here runs as it does in the app.
    register_task_handlers()


@pytest.fixture
async def cast(db_session, create_person):
    return await make_cast(db_session, create_person)


@pytest.fixture
def walk(client, db_session, cast):
    return Walk(client, db_session, cast)


async def _mode(walk, mode="always", **more):
    await walk.call(
        walk.cast.beheerder,
        "patch",
        "/api/instance-settings",
        json={"values": {quote_approval.MODE.key: mode, **more}},
    )


async def _line(walk, on, label="regel", **changes):
    return await walk.step(
        label,
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=on,
        json=line_body(**changes),
    )


async def _quote(walk, on, label="offerte", **body):
    return await walk.step(
        label,
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/quotes",
        on=on,
        json=body,
    )


async def _ask(walk, on, quote):
    return await walk.step(
        "gevraagd",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/approval/request",
        on=on,
        json={"note": "Graag voor vrijdag."},
    )


async def _decide(walk, on, quote, decision="approve", note=None):
    return await walk.step(
        f"beslist: {decision}",
        walk.cast.approver,
        "post",
        f"/api/quotes/{quote['id']}/approval/decision",
        on=on,
        json={
            "decision": decision,
            "quote_hash": quote["snapshot_hash"],
            **({"note": note} if note else {}),
        },
    )


async def _offer(walk, on, quote, **body):
    return await walk.step(
        "aangeboden",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/offers",
        on=on,
        json=body or {"channel": "signing_link", "email": walk.cast.signer.email},
    )


async def _sign(walk, on, quote):
    return await walk.step(
        "getekend",
        walk.cast.signer,
        "post",
        f"/api/signing/quotes/{quote['id']}/accept",
        on=on,
        json={"quote_hash": quote["snapshot_hash"], "confirm_mandate": True},
    )


async def _start(walk, on):
    return await walk.step(
        "gestart",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/transition",
        on=on,
        json={"target": "in_progress"},
    )


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def test_the_main_path_with_approval(walk):
    await _mode(walk)
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _ask(walk, 3, quote)
    await _decide(walk, 4, quote)
    await _offer(walk, 5, quote)
    await walk.step(
        "geopend",
        walk.cast.signer,
        "get",
        f"/api/signing/quotes/{quote['id']}",
        on=6,
    )
    await _sign(walk, 7, quote)
    await _start(walk, 8)
    await walk.check_every_look_back()

    moments = await walk.moments(walk.cast.beheerder)
    assert [moment["fact"] for moment in moments] == [
        "assignment_created",
        "budget_line_added",
        "quote_issued",
        "approval_requested",
        "approval_approved",
        "quote_offered",
        "invitation_opened",
        "quote_accepted",
        "assignment_status_changed",
    ]
    assert [m["seq"] for m in moments] == sorted(m["seq"] for m in moments)
    by_fact = {moment["fact"]: moment for moment in moments}
    assert by_fact["approval_approved"]["decision"] is True
    assert by_fact["budget_line_added"]["decision"] is False
    assert by_fact["quote_issued"]["actor_name"] == "Priya Voorbeeld"
    assert {moment["actor_kind"] for moment in moments} == {"person"}
    assert "tekende via de tekenlink" in by_fact["quote_accepted"]["statement"]
    assert by_fact["approval_requested"]["lines"] == []

    seen = {item.label: item for item in walk.seen}
    asked = await walk.stand(seen["gevraagd"].seq)
    assert asked["course"]["current_key"] == "goedkeuring"
    assert asked["course"]["next"]["who"]
    assert asked["course"]["next"]["mine"] is False
    assert [a["status"] for a in asked["quotes"][0]["approvals"]] == ["requested"]
    assert asked["quotes"][0]["approvals"][0]["requested_by_name"] == "Priya Voorbeeld"
    assert asked["quotes"][0]["approvals"][0]["request_note"] == "Graag voor vrijdag."
    assert asked["quotes"][0]["changed"] is True
    for label in ("offerte", "beslist: approve", "aangeboden", "geopend", "getekend"):
        changed = (await walk.stand(seen[label].seq))["quotes"][0]["changed"]
        assert changed is True, f"{label} changed what hangs from the quote"
    assert (await walk.stand(seen["gestart"].seq))["quotes"][0]["changed"] is False
    assert asked["assignment"]["owner_name"] == "Priya Voorbeeld"
    assert asked["assignment"]["client_name"] == "Voorbeeldministerie"
    assert asked["assignment"]["status_label"] == "Offerte gemaakt"
    assert asked["quotes"][0]["status_label"] == "Offerte gemaakt"

    made = await walk.stand(seen["offerte"].seq)
    assert made["quotes"][0]["approvals"] == []
    assert made["quotes"][0]["offers"] == []
    assert made["previous_seq"] == seen["regel"].seq
    assert made["next_seq"] == seen["gevraagd"].seq

    first = await walk.stand(seen["gemaakt"].seq)
    assert first["previous_seq"] is None
    assert first["budget"]["lines"] == []
    last = await walk.stand(seen["gestart"].seq)
    assert last["quotes"][0]["approvals"][0]["request_note"] == "Graag voor vrijdag."
    assert last["next_seq"] is None
    assert last["course"]["next"] is None
    assert last["assignment"]["status_label"] == "In uitvoering"
    line_moment = await walk.stand(seen["regel"].seq)
    assert line_moment["budget"]["lines"][0]["change"] == "added"
    assert line_moment["budget"]["total_budgeted_cents"] == BUDGET
    assert line_moment["budget"]["previous_total_cents"] == 0


async def test_sent_back_then_a_new_quote(walk):
    await _mode(walk)
    await walk.begin(0)
    await _line(walk, 1)
    first = await _quote(walk, 2)
    await _ask(walk, 3, first)
    await _decide(walk, 4, first, "send_back", note="Tarief klopt niet.")
    second = await _quote(walk, 5, "nieuwe offerte")
    await _ask(walk, 6, second)
    await _decide(walk, 7, second)
    await _offer(walk, 8, second)
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    back = await walk.stand(seen["beslist: send_back"].seq)
    assert back["course"]["current_key"] == "offerte"
    assert back["moment"]["decision"] is True
    assert back["moment"]["lines"] == []
    assert back["quotes"][0]["changed"] is True
    assert back["quotes"][0]["approvals"][0]["decision_note"] == "Tarief klopt niet."
    again = await walk.stand(seen["nieuwe offerte"].seq)
    assert {q["id"]: q["status"] for q in again["quotes"]} == {
        first["id"]: "superseded",
        second["id"]: "issued",
    }
    assert again["quotes"][0]["id"] == second["id"]


async def test_rejected_then_a_new_quote(walk):
    await walk.begin(0)
    await _line(walk, 1)
    first = await _quote(walk, 2)
    await _offer(walk, 3, first, channel="document")
    await walk.step(
        "afgewezen",
        walk.cast.owner,
        "post",
        f"/api/quotes/{first['id']}/rejection",
        on=4,
        json={"reason": "Te duur."},
    )
    second = await _quote(walk, 5, "nieuwe offerte")
    await _offer(walk, 6, second)
    await _sign(walk, 7, second)
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    rejected = await walk.stand(seen["afgewezen"].seq)
    assert rejected["assignment"]["status"] == "rejected"
    assert rejected["quotes"][0]["rejection"]["reason"] == "Te duur."
    assert rejected["quotes"][0]["rejection"]["recorded_by_name"] == "Priya Voorbeeld"
    assert "legde vast" in rejected["moment"]["statement"]
    assert rejected["moment"]["decision"] is False
    assert rejected["moment"]["lines"] == []
    later = await walk.stand(seen["nieuwe offerte"].seq)
    assert later["quotes"][1]["rejection"]["reason"] == "Te duur."


async def test_a_signer_who_rejects_through_the_link_decides(walk):
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _offer(walk, 3, quote)
    await walk.step(
        "afgewezen",
        walk.cast.signer,
        "post",
        f"/api/signing/quotes/{quote['id']}/reject",
        on=4,
        json={"quote_hash": quote["snapshot_hash"], "reason": "Past niet."},
    )
    await walk.check_every_look_back()

    stand = await walk.stand(walk.seen[-1].seq)
    assert stand["moment"]["decision"] is True
    assert stand["moment"]["statement"] == "Voorbeeldministerie wees de offerte af."
    assert stand["moment"]["actor_name"] == "Tess Voorbeeld"
    assert stand["moment"]["lines"] == []
    rejection = stand["quotes"][0]["rejection"]
    assert rejection["recorded_by_name"] is None
    assert rejection["reason"] == "Past niet."


async def test_the_status_menu_says_what_happened(walk):
    await walk.begin(0)
    await _line(walk, 1)
    steps = (
        ("requested", None),
        ("quoted", None),
        ("verbally_agreed", "Telefonisch akkoord."),
        ("quoted", "Toch nog niet."),
        ("rejected", None),
        ("quoted", None),
        ("accepted", None),
    )
    for on, (target, reason) in enumerate(steps, start=2):
        await walk.step(
            f"{target} op dag {on}",
            walk.cast.owner,
            "post",
            f"/api/assignments/{walk.assignment_id}/transition",
            on=on,
            json={"target": target, **({"reason": reason} if reason else {})},
        )
    await walk.check_every_look_back()

    moments = await walk.moments(walk.cast.beheerder)
    assert [
        (moment["title"], moment["decision"], moment["lines"])
        for moment in moments
        if moment["fact"] == "assignment_status_changed"
    ] == [
        ("Offerte aangevraagd", False, []),
        ("Offerte als gemaakt gemarkeerd", False, []),
        ("Mondeling akkoord genoteerd", False, ["Telefonisch akkoord."]),
        ("Terug naar offerte", False, ["Toch nog niet."]),
        ("Afwijzing vastgelegd", False, []),
        ("Terug naar offerte", False, []),
        ("Akkoord vastgelegd", False, []),
    ]


async def test_a_closed_dossier_ends_the_course_in_its_look_back(walk):
    await walk.begin(0)
    await _line(walk, 1)
    targets = ("requested", "quoted", "accepted", "in_progress", "completed")
    for on, target in enumerate(targets, start=2):
        await walk.step(
            target,
            walk.cast.owner,
            "post",
            f"/api/assignments/{walk.assignment_id}/transition",
            on=on,
            json={"target": target},
        )
    await walk.step(
        "dossier gesloten",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/dossier/close",
        on=8,
        json={},
    )
    await walk.check_every_look_back()

    stand = await walk.stand(walk.seen[-1].seq)
    assert stand["course"]["ended"] == "Dossier gesloten"
    assert stand["moment"]["statement"].startswith("Dossier gesloten op ")


async def test_a_look_back_after_a_text_was_taken_out_is_whole(walk):
    name, notes = "Traject rond een zieke medewerker", "Hersteld na een operatie"
    await _mode(walk)
    await walk.begin(0, name=name, notes=notes)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _ask(walk, 3, quote)
    await _decide(walk, 4, quote)
    await _offer(walk, 5, quote)
    await _sign(walk, 6, quote)
    await _start(walk, 7)
    body = await walk.step(
        "tekst verwijderd",
        walk.cast.beheerder,
        "post",
        f"/api/assignments/{walk.assignment_id}/chronicle/{walk.seen[0].seq}/restate",
        on=8,
        json={"columns": ["assignment.name", "assignment.notes"]},
    )
    assert body["kept"] == [
        f"De tekst staat ook in offerte {quote['reference']}; "
        "die blijft zoals ze is gemaakt."
    ]
    # What was seen live, with the placeholder or nothing where the text stood.
    for seen in walk.seen:
        assert seen.assignment["name"] in (name, "Tekst verwijderd")
        seen.assignment = {**seen.assignment, "name": "Tekst verwijderd", "notes": None}
    await walk.check_every_look_back()

    moments = await walk.moments(walk.cast.beheerder)
    assert moments[-1]["title"] == "Tekst verwijderd"
    assert moments[-1]["actor_name"] == walk.cast.beheerder.name
    for moment in moments:
        stand = await walk.stand(moment["seq"])
        told = json.dumps({**stand, "quotes": None})
        assert name not in told and notes not in told, moment["fact"]
    first = await walk.stand(walk.seen[0].seq)
    assert [item["removed"] for item in first["restated"]] == [["Naam", "Notities"]]
    # A quote is a frozen snapshot: it keeps the name it was made with.
    last = await walk.stand(moments[-1]["seq"])
    assert name in json.dumps(last["quotes"][0]["content"])


async def test_a_changed_line_and_case_say_what_changed(walk):
    await walk.begin(0)
    line = (await _line(walk, 1))["lines"][0]
    await walk.step(
        "regel gewijzigd",
        walk.cast.owner,
        "patch",
        f"/api/budget-lines/{line['id']}",
        on=2,
        json={"fte": "0.25"},
    )
    await walk.step(
        "opdracht gewijzigd",
        walk.cast.owner,
        "patch",
        f"/api/assignments/{walk.assignment_id}",
        on=3,
        json={"name": "Geheime naam", "end_date": f"{YEAR}-11-30"},
    )
    await walk.step(
        "notitie",
        walk.cast.owner,
        "patch",
        f"/api/assignments/{walk.assignment_id}",
        on=4,
        json={"notes": "Geheime notitie"},
    )
    await walk.step(
        "regel verwijderd",
        walk.cast.owner,
        "delete",
        f"/api/budget-lines/{line['id']}",
        on=5,
    )
    await walk.check_every_look_back()

    said = [moment["statement"] for moment in await walk.moments(walk.cast.beheerder)]
    assert said[-4:] == [
        "Begrotingsregel Productmanager gewijzigd.",
        "Naam en einddatum van de opdracht gewijzigd.",
        "Opdracht gewijzigd.",
        "Begrotingsregel Productmanager verwijderd.",
    ]
    told = await walk.moments(walk.cast.planner)
    assert [moment["title"] for moment in told[-4:]] == [
        "Begrotingsregel gewijzigd",
        "Opdracht gewijzigd",
        "Opdracht gewijzigd",
        "Begrotingsregel verwijderd",
    ]
    assert all("statement" not in moment for moment in told)


async def test_taking_back_an_approval_and_a_request_say_which(walk, create_person):
    other_approver = await create_person(
        "tweede@example.org", name="Noor Voorbeeld", functions=["offertegoedkeurder"]
    )
    await _mode(walk)
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _ask(walk, 3, quote)
    await walk.step(
        "vraag ingetrokken",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/approval/withdrawal",
        on=4,
    )
    await _ask(walk, 5, quote)
    await _decide(walk, 6, quote)
    await walk.step(
        "goedkeuring ingetrokken",
        other_approver,
        "post",
        f"/api/quotes/{quote['id']}/approval/withdrawal",
        on=7,
    )
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    moments = {
        moment["seq"]: moment for moment in await walk.moments(walk.cast.beheerder)
    }
    assert moments[seen["vraag ingetrokken"].seq]["title"] == (
        "Vraag om goedkeuring ingetrokken"
    )
    assert moments[seen["goedkeuring ingetrokken"].seq]["title"] == (
        "Goedkeuring ingetrokken"
    )
    told = await walk.moments(walk.cast.planner)
    assert [moment["title"] for moment in told if "ingetrokken" in moment["title"]] == [
        "Vraag om goedkeuring ingetrokken",
        "Goedkeuring ingetrokken",
    ]

    request = await walk.stand(seen["vraag ingetrokken"].seq)
    [taken_back] = request["quotes"][0]["approvals"]
    assert taken_back["status"] == "withdrawn"
    assert taken_back["withdrawn_by_name"] == "Priya Voorbeeld"
    assert _instant(taken_back["withdrawn_at"]) == day(4)
    assert taken_back["decided_by_name"] is None and taken_back["decided_at"] is None
    assert request["quotes"][0]["changed"] is True

    approval = await walk.stand(seen["goedkeuring ingetrokken"].seq)
    taken_back = approval["quotes"][0]["approvals"][-1]
    assert taken_back["status"] == "withdrawn"
    assert taken_back["withdrawn_by_name"] == "Noor Voorbeeld"
    assert _instant(taken_back["withdrawn_at"]) == day(7)
    assert taken_back["decided_by_name"] == "Sem Voorbeeld", "the approval stays told"
    assert _instant(taken_back["decided_at"]) == day(6)

    decided = await walk.stand(seen["beslist: approve"].seq)
    not_yet = decided["quotes"][0]["approvals"][-1]
    assert not_yet["withdrawn_by_name"] is None and not_yet["withdrawn_at"] is None
    planner = await walk.stand(seen["goedkeuring ingetrokken"].seq, walk.cast.planner)
    assert "approvals" not in planner["quotes"][0]
    assert "withdrawn_at" not in json.dumps(planner)


async def test_approving_what_you_asked_yourself_is_told_as_that(walk, db_session):
    await _mode(walk, **{quote_approval.ALLOW_SELF.key: True})
    await walk.begin(0)
    await assignments.set_assignment_role(
        db_session,
        UUID(walk.assignment_id),
        walk.cast.approver.id,
        "manager",
        actor=walk.cast.owner,
    )
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await walk.step(
        "gevraagd",
        walk.cast.approver,
        "post",
        f"/api/quotes/{quote['id']}/approval/request",
        on=3,
        json={},
    )
    await _decide(walk, 4, quote)
    await walk.check_every_look_back()

    moment = (await walk.moments(walk.cast.beheerder))[-1]
    assert moment["statement"] == (
        "Offerte intern goedgekeurd door wie de goedkeuring zelf vroeg."
    )
    told = (await walk.moments(walk.cast.planner))[-1]
    assert told["title"] == "Offerte intern goedgekeurd"
    assert "statement" not in told


async def test_a_budget_change_after_a_quote_outdates_it(walk):
    await walk.begin(0)
    line = (await _line(walk, 1))["lines"][0]
    await _quote(walk, 2)
    changed = await walk.step(
        "gewijzigd",
        walk.cast.owner,
        "patch",
        f"/api/budget-lines/{line['id']}",
        on=3,
        json={"fte": "0.25"},
    )
    assert changed["total_budgeted_cents"] == BUDGET // 2
    await _quote(walk, 4, "nieuwe offerte")
    extra = await _line(
        walk,
        5,
        "tweede regel",
        role=None,
        description="Hosting",
        kind="fixed",
        fte=None,
        rate_category=None,
        start_date=None,
        end_date=None,
        amount_cents=150000,
        year=YEAR,
    )
    gone = next(item for item in extra["lines"] if item["kind"] == "fixed")
    await walk.step(
        "verwijderd",
        walk.cast.owner,
        "delete",
        f"/api/budget-lines/{gone['id']}",
        on=6,
    )
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    outdated = await walk.stand(seen["gewijzigd"].seq)
    assert outdated["course"]["current_key"] == "offerte"
    assert outdated["budget"]["lines"][0]["change"] == "changed"
    assert outdated["budget"]["previous_total_cents"] == BUDGET
    assert outdated["quotes"][0]["total_cents"] == BUDGET, "the quote stays frozen"
    assert outdated["quotes"][0]["changed"] is False
    removed = await walk.stand(seen["verwijderd"].seq)
    assert removed["budget"]["removed"] == ["Hosting"]
    assert [line["kind"] for line in removed["budget"]["lines"]] == ["personnel"]


async def test_a_verbal_agreement_on_the_way(walk):
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _offer(walk, 3, quote)
    await walk.step(
        "mondeling",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/transition",
        on=4,
        json={"target": "verbally_agreed", "reason": "Telefonisch akkoord."},
    )
    await _sign(walk, 5, quote)
    await _start(walk, 6)
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    verbal = await walk.stand(seen["mondeling"].seq)
    assert verbal["moment"]["title"] == "Mondeling akkoord genoteerd"
    assert verbal["assignment"]["status_label"] == "Mondeling akkoord"
    assert verbal["assignment"]["verbal_agreement_note"]
    assert verbal["moment"]["lines"] == ["Telefonisch akkoord."]


async def test_a_rate_card_between_two_steps(walk, db_session):
    await walk.begin(0)
    # Runs into next year, which has no active card yet: it cannot be priced.
    await _line(walk, 1, "regel over de jaargrens", end_date=f"{YEAR + 1}-06-30")
    waiting = walk.seen[-1].budget
    assert waiting["total_budgeted_cents"] is None and waiting["pricing_error"]
    await add_rate_card(db_session, YEAR + 1, walk.cast.beheerder)
    await _line(walk, 2, "tweede regel", role="Ontwikkelaar", rate_category="B")
    priced = walk.seen[-1].budget
    assert priced["total_budgeted_cents"] is not None
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    before = await walk.stand(seen["regel over de jaargrens"].seq)
    assert before["budget"]["total_budgeted_cents"] is None
    assert before["budget"]["pricing_error"] == waiting["pricing_error"]
    assert before["outside"] == [] and before["outside_values"] == []
    after = await walk.stand(seen["tweede regel"].seq)
    assert after["budget"]["total_budgeted_cents"] == priced["total_budgeted_cents"]
    assert after["outside"] == ["De tarieven zijn gewijzigd."]
    assert after["outside_values"] == [
        f"Tarievenkaart Tarieven {YEAR + 1} vastgesteld, geldt vanaf "
        f"1 januari {YEAR + 1}."
    ]


async def test_a_moment_before_the_first_card_stays_without_a_price(
    client, db_session, create_person
):
    cast = await make_cast(db_session, create_person, with_rate_card=False)
    walk = Walk(client, db_session, cast)
    await rates.create_rate_card(db_session, YEAR + 1, actor=cast.beheerder)
    repository = ChronicleRepository(db_session)
    assert await repository.rate_grams() == [], "a draft prices nothing"

    await walk.begin(0)
    await _line(walk, 1)
    waiting = walk.seen[-1].budget
    assert waiting["total_budgeted_cents"] is None and waiting["pricing_error"]

    await add_rate_card(db_session, YEAR, cast.beheerder)
    [rate_fact] = await repository.rate_grams()
    assert [card["status"] for card in rate_fact.fields["book"]["cards"]] == ["active"]
    await _line(walk, 2, "tweede regel", role="Ontwikkelaar", rate_category="B")
    assert walk.seen[-1].budget["total_budgeted_cents"] is not None
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    then = await walk.stand(seen["regel"].seq)
    assert then["budget"]["total_budgeted_cents"] is None
    assert then["budget"]["pricing_error"] == waiting["pricing_error"]
    assert [line["budgeted_cents"] for line in then["budget"]["lines"]] == [None]
    assert then["outside"] == []
    later = await walk.stand(seen["tweede regel"].seq)
    assert later["budget"]["previous_total_cents"] is None, "there was no total"
    assert later["outside"] == ["De tarieven zijn gewijzigd."]
    assert later["outside_values"] == [
        f"Tarievenkaart Tarieven {YEAR} vastgesteld, geldt vanaf 1 januari {YEAR}."
    ]


async def test_a_rate_change_leaves_the_earlier_total(walk):
    await walk.begin(0)
    await _line(walk, 1)
    total = walk.seen[-1].budget["total_budgeted_cents"]
    card = await walk.call(
        walk.cast.beheerder,
        "post",
        "/api/rates/cards",
        json={
            "valid_from": f"{YEAR}-07-01",
            "copy_previous": True,
            "increase_pct": "10",
        },
    )
    await walk.call(
        walk.cast.beheerder, "post", f"/api/rates/cards/{card['id']}/activate"
    )
    live = await walk.call(
        walk.cast.beheerder, "get", f"/api/assignments/{walk.assignment_id}/budget"
    )
    assert live["total_budgeted_cents"] > total
    await _line(walk, 2, "tweede regel", role="Ontwikkelaar", rate_category="B")
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    earlier = await walk.stand(seen["regel"].seq)
    assert earlier["budget"]["total_budgeted_cents"] == total
    assert earlier["outside"] == [] and earlier["outside_values"] == []
    later = await walk.stand(seen["tweede regel"].seq)
    assert (
        later["budget"]["lines"][0]["budgeted_cents"]
        == live["lines"][0]["budgeted_cents"]
    )
    assert later["budget"]["previous_total_cents"] == total
    assert later["outside"] == ["De tarieven zijn gewijzigd."], "one line, no card"
    assert len(later["outside_values"]) == 1
    assert later["outside_values"][0].startswith("Tarievenkaart ")
    assert "vastgesteld" in later["outside_values"][0]


async def test_a_change_of_the_approval_rule_is_named(walk):
    await walk.begin(0)
    await _line(walk, 1)
    await _mode(walk)
    await _line(walk, 2, "tweede regel", role="Ontwikkelaar", rate_category="B")
    await _mode(walk, "from_amount", **{quote_approval.THRESHOLD.key: 500000})
    await _line(walk, 3, "derde regel", role="Ontwerper", rate_category="C")
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    assert (await walk.stand(seen["regel"].seq))["outside"] == []
    always = await walk.stand(seen["tweede regel"].seq)
    assert always["outside"] == ["Interne goedkeuring is nu nodig voor elke offerte."]
    assert always["outside_values"] == always["outside"]
    from_amount = await walk.stand(seen["derde regel"].seq)
    assert from_amount["outside"] == [
        "Interne goedkeuring is nu nodig vanaf een bedrag."
    ]
    assert from_amount["outside_values"] == [
        "Interne goedkeuring is nu nodig vanaf € 5.000."
    ]
    as_planner = await walk.stand(seen["derde regel"].seq, walk.cast.planner)
    assert as_planner["outside"] == from_amount["outside"]
    assert "outside_values" not in as_planner


async def test_a_quote_that_expired_between_two_moments(walk):
    await walk.begin(0)
    await _line(walk, 1)
    valid_until = (day(3).date()).isoformat()
    quote = await _quote(walk, 2, valid_until=valid_until)
    await _offer(walk, 2, quote, channel="document")
    await walk.step(
        "na de geldigheid",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=6,
        json=line_body(role="Ontwikkelaar", rate_category="B"),
    )
    await walk.check_every_look_back()

    late = await walk.stand(walk.seen[-1].seq)
    assert late["outside"] == ["De offerte is verlopen."]
    assert len(late["outside_values"]) == 1
    assert late["outside_values"][0].startswith("De offerte is verlopen op ")
    planner = await walk.stand(walk.seen[-1].seq, walk.cast.planner)
    assert planner["outside"] == ["De offerte is verlopen."]
    assert "outside_values" not in planner


async def test_an_uploaded_pdf_recorded_late_and_corrected(walk):
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _offer(walk, 2, quote, channel="document")
    signed = day(3)
    await walk.step(
        "begroting op dag 5",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=5,
        json=line_body(role="Ontwikkelaar", rate_category="B"),
    )
    await walk.step(
        "vastgelegd op dag 10",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        on=10,
        data={
            "signer_name": "Directeur Voorbeeld",
            "signer_email": "directeur@opdrachtgever.example",
            "signed_at": signed.isoformat(),
        },
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )
    corrected = day(4)
    await walk.step(
        "gecorrigeerd",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/acceptance/correction",
        on=12,
        json={
            "signed_at": corrected.isoformat(),
            "reason": "Datum verkeerd overgenomen",
        },
    )
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    day_five = await walk.stand(seen["begroting op dag 5"].seq)
    assert day_five["quotes"][0]["status"] == "issued", "what was known then"
    assert day_five["quotes"][0]["acceptance"] is None
    known = {item["seq"]: item for item in day_five["later_known"]}
    recorded = seen["vastgelegd op dag 10"].seq
    assert recorded in known
    assert known[recorded]["effective_on"] == clock.local_date(signed).isoformat()
    assert known[recorded]["title"] == "Getekende pdf vastgelegd"
    assert "legde vast dat Directeur Voorbeeld" in known[recorded]["statement"]
    assert set(known) == {recorded, seen["gecorrigeerd"].seq}, (
        "corrected to a day already seen; nothing else counts from before"
    )
    made = await walk.stand(seen["offerte"].seq)
    assert made["later_known"] == [], "signed after this day"

    first = await walk.stand(recorded)
    assert first["quotes"][0]["acceptance"]["signed_at"].startswith(
        signed.date().isoformat()
    )
    assert first["quotes"][0]["acceptance"]["recorded_by_name"] == "Priya Voorbeeld"
    assert first["moment"]["decision"] is False, "noting a signature is no decision"
    assert first["moment"]["effective_on"] == clock.local_date(signed).isoformat()
    last = await walk.stand(seen["gecorrigeerd"].seq)
    assert last["quotes"][0]["acceptance"]["signed_at"].startswith(
        corrected.date().isoformat()
    )
    assert last["moment"]["lines"] == ["Datum verkeerd overgenomen"]
    assert last["quotes"][0]["changed"] is True


async def test_a_correction_stands_next_to_what_it_corrects(walk):
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _offer(walk, 2, quote, channel="document")
    await _line(walk, 3, "voor beide datums", role="Ontwikkelaar", rate_category="B")
    await _line(walk, 6, "tussen de datums", role="Ontwerper", rate_category="C")
    await walk.step(
        "vastgelegd op dag 10",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        on=10,
        data={
            "signer_name": "Directeur Voorbeeld",
            "signer_email": "directeur@opdrachtgever.example",
            "signed_at": day(5).isoformat(),
        },
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )
    await walk.step(
        "gecorrigeerd op dag 12",
        walk.cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/acceptance/correction",
        on=12,
        json={"signed_at": day(7).isoformat(), "reason": "Datum verkeerd overgenomen"},
    )
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    between = await walk.stand(seen["tussen de datums"].seq)
    recorded, corrected = between["later_known"]
    assert recorded["seq"] == seen["vastgelegd op dag 10"].seq
    assert corrected["seq"] == seen["gecorrigeerd op dag 12"].seq
    assert corrected["effective_on"] == clock.local_date(day(7)).isoformat()
    assert "corrigeerde de datum van tekenen van " in corrected["statement"]
    assert (await walk.stand(seen["voor beide datums"].seq))["later_known"] == []
    as_planner = await walk.stand(seen["tussen de datums"].seq, walk.cast.planner)
    assert [set(item) for item in as_planner["later_known"]] == [{"seq", "title"}] * 2


async def test_a_stand_tells_where_a_signing_link_stood(walk):
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    expires = day(20)
    await _offer(
        walk,
        3,
        quote,
        channel="signing_link",
        email=walk.cast.signer.email,
        expires_at=expires.isoformat(),
    )
    await walk.step(
        "geopend",
        walk.cast.signer,
        "get",
        f"/api/signing/quotes/{quote['id']}",
        on=4,
    )
    owner = walk.cast.owner
    live = (await walk.call(owner, "get", f"/api/quotes/{quote['id']}"))["offers"][0]
    invitation_id = live["invitation"]["id"]
    await walk.step(
        "ingetrokken",
        owner,
        "post",
        f"/api/quotes/{quote['id']}/invitations/{invitation_id}/withdraw",
        on=5,
    )
    await _line(walk, 6, "na het intrekken", role="Ontwikkelaar", rate_category="B")
    await walk.check_every_look_back()

    async def link_at(label):
        seen = next(item for item in walk.seen if item.label == label)
        stand = await walk.stand(seen.seq, owner)
        return stand["quotes"][0]["offers"][0]["invitation"]

    offered = await link_at("aangeboden")
    assert offered["state"] == "invited"
    assert _instant(offered["expires_at"]) == expires
    assert offered["opened_at"] is None and offered["withdrawn_at"] is None
    opened = await link_at("geopend")
    assert opened["state"] == "opened"
    assert _instant(opened["opened_at"]) == day(4)
    for label in ("ingetrokken", "na het intrekken"):
        withdrawn = await link_at(label)
        assert withdrawn["state"] == "withdrawn", label
        assert _instant(withdrawn["withdrawn_at"]) == day(5)
    now = (await walk.call(owner, "get", f"/api/quotes/{quote['id']}"))["offers"][0]
    then = await link_at("na het intrekken")
    assert set(then) == set(now["invitation"]) - {"id", "signing_path"}
    assert then["state"] == now["invitation"]["state"]
    assert _instant(then["withdrawn_at"]) == _instant(now["invitation"]["withdrawn_at"])


async def test_a_link_expired_at_the_moment_it_stood_expired(walk):
    await walk.begin(0)
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    expires = day(5)
    with stream.recording_at(day(3)):
        await _offer(
            walk,
            3,
            quote,
            channel="signing_link",
            email=walk.cast.signer.email,
            expires_at=expires.isoformat(),
        )
    with stream.recording_at(expires - timedelta(seconds=1)):
        await _line(walk, 5, "net ervoor", role="Ontwikkelaar", rate_category="B")
    with stream.recording_at(expires):
        await _line(walk, 5, "op het moment", role="Ontwerper", rate_category="C")
    with stream.recording_at(day(6)):
        await _line(walk, 6, "erna", role="Tester", rate_category="A")

    states = {}
    for seen in walk.seen:
        stand = await walk.stand(seen.seq, walk.cast.owner)
        offers = stand["quotes"][0]["offers"] if stand["quotes"] else []
        if offers:
            states[seen.label] = offers[0]["invitation"]["state"]
    assert states == {
        "aangeboden": "invited",
        "net ervoor": "invited",
        "op het moment": "expired",
        "erna": "expired",
    }


def _optional_columns() -> list[tuple[str, str]]:
    """What a migration can add to a read model: a column that may hold nothing,
    or that has a value of its own when nothing is said."""
    found = []
    for table, model in MODELS.items():
        for key in columns_of(model):
            column = sa_inspect(model).column_attrs[key].columns[0]
            default = column.default
            if column.nullable or (default is not None and default.is_scalar):
                found.append((table, key))
    return found


async def test_a_fact_from_before_a_column_still_reads(walk, monkeypatch):
    await _mode(walk)
    await walk.begin(0)
    await _line(walk, 1)
    first = await _quote(walk, 2)
    await _ask(walk, 3, first)
    await _decide(walk, 4, first)
    await _offer(walk, 5, first, channel="document")
    await walk.step(
        "afgewezen",
        walk.cast.owner,
        "post",
        f"/api/quotes/{first['id']}/rejection",
        on=6,
        json={"reason": "Te duur."},
    )
    second = await _quote(walk, 7, "nieuwe offerte")
    await _ask(walk, 8, second)
    await _decide(walk, 9, second)
    await _offer(walk, 10, second)
    await _sign(walk, 11, second)
    await _start(walk, 12)
    last = walk.seen[-1].seq
    case = UUID(walk.assignment_id)

    def said_before(table, key):
        def effects(name, fields):
            return tuple(
                replace(
                    effect,
                    values={k: v for k, v in effect.values.items() if k != key},
                )
                if isinstance(effect, Insert) and effect.table == table
                else effect
                for effect in effects_of(name, fields)
            )

        return effects

    columns = _optional_columns()
    assert ("assignment", "notes") in columns
    assert ("budget_line", "year") in columns
    assert ("quote_approval", "self_approved") in columns
    assert len(columns) > 50
    for table, key in columns:
        monkeypatch.setattr(ledger, "effects_of", said_before(table, key))
        stand = await walk.stand(last)
        assert stand["moment"]["seq"] == last, f"{table}.{key}"
        report = await differences(walk.db, case)
        assert report.differences == [], f"{table}.{key}"

    monkeypatch.setattr(ledger, "effects_of", said_before("assignment", "notes"))
    assert (await walk.stand(last))["assignment"]["notes"] is None


async def test_a_fact_of_the_same_day_is_not_known_later(walk):
    await walk.begin(0)
    await _line(walk, 0)
    await _quote(walk, 0)
    first = await walk.stand(walk.seen[0].seq)
    assert first["later_known"] == []


async def test_taking_over_a_step_changes_no_look_back(walk, db_session):
    await _mode(walk)
    await walk.begin(0)
    await assignments.set_assignment_role(
        db_session,
        UUID(walk.assignment_id),
        walk.cast.planner.id,
        "manager",
        actor=walk.cast.owner,
    )
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    course = await walk.call(
        walk.cast.planner,
        "get",
        f"/api/tasks/cases/assignment/{walk.assignment_id}/course",
    )
    task_id = course["course"]["next"]["task_id"]
    await walk.step(
        "overgenomen",
        walk.cast.planner,
        "post",
        f"/api/tasks/{task_id}/takeover",
        on=3,
    )
    await _ask(walk, 4, quote)
    await walk.check_every_look_back()
    seen = {item.label: item for item in walk.seen}
    taken = await walk.stand(seen["overgenomen"].seq)
    assert taken["course"]["next"]["who"] != walk.cast.planner.name


async def test_no_approver(walk, db_session):
    await _mode(walk)
    await db_session.execute(
        delete(PersonRole).where(PersonRole.person_id == walk.cast.approver.id)
    )
    await walk.begin(0)
    await _line(walk, 1)
    await _quote(walk, 2)
    await walk.check_every_look_back()
    stand = await walk.stand(walk.seen[-1].seq)
    live = walk.seen[-1].course
    assert stand["course"]["current_key"] == live["current_key"] == "goedkeuring"
    assert stand["course"]["next"]["headline"] == live["next"]["headline"]


async def test_who_is_on_a_line_counts_from_the_moment_after(walk):
    await walk.begin(0)
    budget = await _line(walk, 1)
    quote = await _quote(walk, 2)
    await _offer(walk, 3, quote)
    await _sign(walk, 4, quote)
    await walk.call(
        walk.cast.owner,
        "post",
        "/api/allocations",
        json={
            "budget_line_id": budget["lines"][0]["id"],
            "person_id": str(walk.cast.member.id),
            "fte_pct": "50",
        },
    )
    await _line(walk, 5, "tweede regel", role="Ontwikkelaar", rate_category="B")
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    signed, second = seen["getekend"], seen["tweede regel"]
    assert signed.course["more_waiting"] == 1, "the role is still open"
    then = await walk.stand(signed.seq)
    assert then["course"]["more_waiting"] == 1
    # Filled, and the new role open. Live also counts months to close, which a
    # look-back does not know of.
    later = await walk.stand(second.seq)
    assert later["course"]["more_waiting"] == 1


def test_who_is_on_a_line_follows_from_the_records():
    line = SimpleNamespace(
        id=uuid4(), start_date=date(2026, 3, 1), end_date=date(2026, 9, 30)
    )

    def record(subject, action="create", erased=None, **values):
        return SimpleNamespace(
            subject_id=subject, action=action, new_value=values, erased_at=erased
        )

    on_line = {"budget_line_id": str(line.id), "fte_pct": "50"}
    own = {"start_date": "2026-04-01", "end_date": "2026-05-31"}
    found, erased = _allocations(
        [
            record("volgt", period_source="line", **on_line),
            record("eigen", period_source="own", **on_line, **own),
            record("eigen", action="update", fte_pct="25"),
            record("weg", period_source="own", **on_line, **own),
            record("weg", action="delete"),
            record("elders", period_source="own", budget_line_id=str(uuid4()), **own),
        ],
        [line],
    )
    assert erased is False
    assert sorted(
        (item.start_date, item.end_date, item.fte_pct) for item in found[line.id]
    ) == [
        (date(2026, 3, 1), date(2026, 9, 30), Decimal(50)),
        (date(2026, 4, 1), date(2026, 5, 31), Decimal(25)),
    ]
    assert _allocations([record("x", erased=datetime.now(UTC))], [line]) == ({}, True)


async def test_the_dev_walk_takes_every_step(db_session, create_person):
    for key, name, functions in (
        ("bente.beheer", "Bente Beheer", ["beheerder"]),
        ("priya.product", "Priya Product", ["planner"]),
        ("sem.senior", "Sem Senior", ["offertegoedkeurder"]),
        ("tess.teken", "Tess Teken", ["tekenbevoegde"]),
    ):
        await create_person(f"{key}@{EMAIL_DOMAIN}", name=name, functions=functions)
    beheerder = await db_session.scalar(
        select(Person).where(Person.email == f"bente.beheer@{EMAIL_DOMAIN}")
    )
    await add_rate_card(db_session, YEAR, beheerder)
    case = await chronicle_walk.create(db_session, approval=True)
    taken = []
    while (step := await chronicle_walk.next_step(db_session, case.id)) is not None:
        await chronicle_walk._ACTIONS[step](db_session, case, None)
        taken.append(step)
        await db_session.flush()
        report = await differences(db_session, case.id)
        assert report.checked and report.differences == [], step
        assert len(taken) <= len(chronicle_walk.STEPS)
    assert tuple(taken) == chronicle_walk.STEPS
    assert case.status == "in_progress"


@pytest.fixture
def bridged(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    )
    clear_registries()
    register_bridge()
    get_bridge_settings.cache_clear()
    yield
    get_bridge_settings.cache_clear()
    clear_registries()
    quote_channels.clear()


async def test_an_acceptance_received_from_another_instance(
    walk, db_session, bridged, fed_client, make_peer, fed_settings
):
    settings = fed_settings.model_copy(
        update={"FEDERATION_SIGNING_KEY": signing.generate_private_key_pem()}
    )
    await make_peer(
        CLIENT_PEER_ID, base_uri=CLIENT_BASE, jwks=signing.own_jwks(settings)
    )
    client_org = await from_reference(
        db_session,
        {
            "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
            "name": "Voorbeeldministerie",
            "unit_key": "directie-voorbeeld",
            "instance_uri": CLIENT_BASE,
        },
    )
    own = await own_organisation(db_session)
    with clock.at(day(0)):
        case = await assignments.create_assignment(
            db_session,
            name="Opdracht Alfa",
            actor=walk.cast.owner,
            client_organisation_id=client_org.id,
            contractor_organisation_id=own.id,
            uri=f"{CLIENT_BASE}/id/opdracht/{FEDERATED_ASSIGNMENT_ID}",
            start_date=day(0).date().replace(month=1, day=1),
            end_date=day(0).date().replace(month=12, day=31),
        )
        await assignments.share_with_instance(db_session, case, CLIENT_BASE)
    walk.assignment_id = str(case.id)
    with clock.at(day(0)):
        await walk.look("gemaakt")
    await _line(walk, 1)
    quote = await _quote(walk, 2)
    body = example("acceptance")
    del body[t("jws")]
    body[t("quote_id")] = quote["id"]
    body[t("quote_hash")] = quote["snapshot_hash"]
    body[t("jws")] = signing.sign_acceptance(body, settings)
    with clock.at(day(3)):
        response = await fed_client.post(
            f"/v1/offertes/{quote['id']}/akkoorden",
            json=body,
            headers=as_peer(CLIENT_PEER_ID),
        )
        assert response.status_code == 201, response.text
        await walk.look("ontvangen")
    await walk.check_every_look_back()
    moment = (await walk.stand(walk.seen[-1].seq))["moment"]
    assert moment["fact"] == "quote_accepted"
    assert moment["decision"] is False, "what the other instance decided is received"
    assert moment["statement"].startswith("Ontvangen van ")


async def test_who_sent_a_quote_is_told_to_whom_the_case_tells_it(
    walk, db_session, bridged, fed_client, make_peer
):
    peer = await make_peer()
    body = example("quote")
    response = await fed_client.post(
        "/v1/offertes", json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    case = await db_session.scalar(
        select(Assignment).where(Assignment.uri == body[t("assignment_uri")])
    )
    walk.assignment_id = str(case.id)
    sender = body[t("contractor")][t("name")]
    title = f"Offerte ontvangen van {sender}"

    for reader in (walk.cast.beheerder, walk.cast.reader):
        moment = (await walk.moments(reader))[-1]
        assert moment["fact"] == "quote_received"
        assert moment["title"] == title
        assert moment["actor_kind"] == "peer"
        assert moment["actor_name"] is None
        assert f"ontvangen van {sender}, " in moment["statement"]

    planner = await walk.moments(walk.cast.planner)
    assert planner[-1]["title"] == title
    assert planner[-1]["actor_kind"] == "peer"
    assert "statement" not in planner[-1]
    live = await walk.call(walk.cast.planner, "get", f"/api/assignments/{case.id}")
    assert live["contractor_name"] == sender, "the title holds what the case holds"
    assert peer.peer_id not in json.dumps(planner)

    hidden = await walk.as_person(walk.cast.outsider).get(
        f"/api/assignments/{case.id}/chronicle"
    )
    assert hidden.status_code == 404
