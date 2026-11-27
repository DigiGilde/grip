"""Who sees what of a moment. All names and amounts are fictional."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select

from grip.access import DataClass, schema_classes
from grip.access.fields import unclassified_fields
from grip.chronicle.verify import differences, rebuild
from grip.chronicle.writer import SUBJECT_KIND
from grip.core import clock
from grip.events.check import verify_stream
from grip.events.reading import READ_TYPE
from grip.events.retention import (
    RETENTION_DAYS,
    _erase,
    apply_retention,
)
from grip.models.stream_event import StreamEvent
from grip.repositories.chronicle import ChronicleRepository
from grip.schema.chronicle import MomentsOut, StandOut
from grip.services import assignments, instance_settings, quote_approval, rates
from tests.chronicle.walking import (
    PDF_BYTES,
    YEAR,
    Walk,
    comparable,
    day,
    line_body,
    make_cast,
)

NOTE = "Graag voor vrijdag."
_MONEY_AND_CONTENT = {
    "statement",
    "total_cents",
    "amount_cents",
    "budgeted_cents",
    "total_budgeted_cents",
    "previous_total_cents",
    "subtotals_by_year",
    "pricing_error",
    "rate_category",
    "year",
    "quoted_amount_cents",
    "snapshot_hash",
    "document_sha256",
    "has_document",
    "valid_until",
    "issued_at",
    "content",
    "approvals",
    "offers",
    "invitation",
    "acceptance",
    "rejection",
    "outside_values",
}
_LINE_FIELDS = (
    "id",
    "description",
    "kind",
    "position",
    "role",
    "fte",
    "start_date",
    "end_date",
    "rate_category",
    "amount_cents",
    "year",
    "budgeted_cents",
)


def _keys(value: Any) -> set[str]:
    """Every key in a response, however deep."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


@pytest.fixture
async def cast(db_session, create_person):
    return await make_cast(db_session, create_person)


@pytest.fixture
async def walked(client, db_session, cast):
    """A case signed through a link, with someone staffed on it."""
    walk = Walk(client, db_session, cast)
    await walk.call(
        cast.beheerder,
        "patch",
        "/api/instance-settings",
        json={"values": {quote_approval.MODE.key: "always"}},
    )
    await walk.begin(0)
    budget = await walk.step(
        "regel",
        cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=1,
        json=line_body(),
    )
    await assignments.add_allocation(
        db_session,
        UUID(budget["lines"][0]["id"]),
        cast.member.id,
        start_date=day(0).date().replace(month=1, day=1),
        end_date=day(0).date().replace(month=12, day=31),
        fte_pct=50,
        actor=cast.owner,
    )
    quote = await walk.step(
        "offerte",
        cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/quotes",
        on=2,
        json={},
    )
    await walk.step(
        "gevraagd",
        cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/approval/request",
        on=3,
        json={"note": NOTE},
    )
    await walk.step(
        "goedgekeurd",
        cast.approver,
        "post",
        f"/api/quotes/{quote['id']}/approval/decision",
        on=4,
        json={"decision": "approve", "quote_hash": quote["snapshot_hash"]},
    )
    await walk.step(
        "aangeboden",
        cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/offers",
        on=5,
        json={"channel": "signing_link", "email": cast.signer.email},
    )
    await walk.step(
        "getekend",
        cast.signer,
        "post",
        f"/api/signing/quotes/{quote['id']}/accept",
        on=6,
        json={"quote_hash": quote["snapshot_hash"], "confirm_mandate": True},
    )
    walk.quote = quote  # type: ignore[attr-defined]
    return walk


def test_every_field_has_one_class_and_nothing_personal_is_in_it():
    assert unclassified_fields(StandOut) == []
    assert unclassified_fields(MomentsOut) == []
    assert schema_classes(StandOut) <= {
        DataClass.ASSIGNMENT_BASIC,
        DataClass.ASSIGNMENT_FINANCIAL,
        DataClass.STAFFING,
    }


async def test_who_reads_only_the_basics_gets_titles(walked):
    member = walked.cast.member
    moments = await walked.moments(member)
    assert moments, "a member may know what happened"
    assert all(moment["title"] for moment in moments)
    assert {key for moment in moments for key in moment} == {
        "seq",
        "occurred_at",
        "fact",
        "title",
        "decision",
        "actor_name",
        "actor_kind",
        "erased",
    }
    assert "statement" not in str(moments) and NOTE not in str(moments)

    for seen in walked.seen:
        stand = await walked.stand(seen.seq, member)
        dumped = json.dumps(stand)
        assert not _keys(stand) & _MONEY_AND_CONTENT, seen.label
        assert "lines" not in stand["moment"], seen.label
        for line in stand["budget"]["lines"]:
            assert set(line) == {"id", "description", "kind", "position", "change"}
        for quote in stand["quotes"]:
            assert set(quote) == {
                "id",
                "reference",
                "status",
                "status_label",
                "changed",
            }
        assert stand["course"]["steps"], seen.label
        assert stand["assignment"]["name"] == "Voorbeeldtraject"
        for secret in (NOTE, walked.cast.signer.email, "10800000", "1800000"):
            assert secret not in dumped, f"{seen.label}: {secret}"
        assert walked.cast.signer.name not in json.dumps(stand["quotes"])


async def test_who_did_it_is_told_as_the_history_tells_it(walked):
    member = walked.cast.member
    client = walked.as_person(member)
    history = await client.get(
        "/api/events", params={"limit": 200, "case_id": walked.assignment_id}
    )
    assert history.status_code == 200, history.text
    told = {item["actor_name"] for item in history.json()["items"]}
    named = {moment["actor_name"] for moment in await walked.moments(member)}
    assert walked.cast.signer.name in named
    assert named - {None} <= told


@pytest.mark.parametrize("who", ["member", "planner", "reader", "beheerder", "owner"])
async def test_each_reader_sees_lines_and_amounts_of_any_moment_by_their_live_class(
    walked, who
):
    person = getattr(walked.cast, who)
    aid = walked.assignment_id
    budget = await walked.call(person, "get", f"/api/assignments/{aid}/budget")
    listed = await walked.call(person, "get", f"/api/assignments/{aid}/quotes")
    assignment = await walked.call(person, "get", f"/api/assignments/{aid}")
    stand = await walked.stand(walked.seen[-1].seq, person)

    live_line, then_line = budget["lines"][0], stand["budget"]["lines"][0]
    for name in _LINE_FIELDS:
        assert (name in then_line) == (name in live_line), f"{who}: line.{name}"
    for name in ("subtotals_by_year", "total_budgeted_cents", "pricing_error"):
        assert (name in stand["budget"]) == (name in budget), f"{who}: budget.{name}"

    live_quote, then_quote = listed["quotes"][0], stand["quotes"][0]
    for name in (
        "id",
        "reference",
        "status",
        "total_cents",
        "snapshot_hash",
        "valid_until",
        "document_sha256",
    ):
        assert (name in then_quote) == (name in live_quote), f"{who}: quote.{name}"
    for name in ("name", "status", "kind", "notes", "quoted_amount_cents"):
        assert (name in stand["assignment"]) == (name in assignment), f"{who}: {name}"

    # Stricter on purpose: dates, acceptance and approvals of a quote take B here.
    reads_values = who in ("reader", "beheerder", "owner")
    for name in ("issued_at", "acceptance"):
        assert name in live_quote, f"{who}: {name}"
        assert (name in then_quote) == reads_values, f"{who}: {name}"

    # The class of a field holds at every moment: who may read the name of a line
    # now reads the name it had then, and the name of a line that is gone.
    aid = walked.assignment_id
    owner = walked.cast.owner
    old, new, gone = "Voorbeeldrol van toen", "Voorbeeldrol van nu", "Eenmalige post"
    await walked.step(
        "oude naam",
        owner,
        "post",
        f"/api/assignments/{aid}/budget-lines",
        on=7,
        json=line_body(role=old, rate_category="B"),
    )
    added = await walked.step(
        "losse post",
        owner,
        "post",
        f"/api/assignments/{aid}/budget-lines",
        on=8,
        json=line_body(
            role=None,
            description=gone,
            kind="fixed",
            fte=None,
            rate_category=None,
            start_date=None,
            end_date=None,
            amount_cents=150000,
            year=YEAR,
        ),
    )
    line_ids = {line["description"]: line["id"] for line in added["lines"]}
    await walked.step(
        "hernoemd",
        owner,
        "patch",
        f"/api/budget-lines/{line_ids[old]}",
        on=9,
        json={"role": new},
    )
    await walked.step(
        "weg", owner, "delete", f"/api/budget-lines/{line_ids[gone]}", on=10
    )

    seen = {item.label: item for item in walked.seen}

    async def names_at(label):
        then = await walked.stand(seen[label].seq, person)
        return [line["description"] for line in then["budget"]["lines"]]

    assert old in await names_at("losse post") and gone in await names_at("losse post")
    assert old not in await names_at("hernoemd") and new in await names_at("hernoemd")
    removal = await walked.stand(seen["weg"].seq, person)
    assert removal["budget"]["removed"] == [gone]
    assert gone not in await names_at("weg")
    live = await walked.call(person, "get", f"/api/assignments/{aid}/budget")
    live_names = [line["description"] for line in live["lines"]]
    assert new in live_names and old not in live_names and gone not in live_names
    # The history is stricter, and stays so: it keeps these for who reads class B.
    history = await walked.call(
        person, "get", "/api/events", params={"limit": 200, "case_id": aid}
    )
    told = json.dumps(history)
    assert (old in told) == reads_values, who
    assert (gone in told) == reads_values, who


async def test_a_planner_sees_staffing_and_no_money(walked):
    planner = walked.cast.planner
    stand = await walked.stand(walked.seen[-1].seq, planner)
    line = stand["budget"]["lines"][0]
    assert line["role"] == "Productmanager"
    assert line["fte"] == "0.5"
    assert line["start_date"] == f"{YEAR}-01-01"
    for hidden in ("rate_category", "amount_cents", "year", "budgeted_cents"):
        assert hidden not in line
    for hidden in ("total_budgeted_cents", "subtotals_by_year"):
        assert hidden not in stand["budget"]
    assert not {"total_cents", "snapshot_hash", "content"} & set(stand["quotes"][0])
    assert "statement" not in stand["moment"]


async def test_who_reads_the_money_sees_no_staffing(walked):
    stand = await walked.stand(walked.seen[-1].seq, walked.cast.reader)
    line = stand["budget"]["lines"][0]
    assert line["budgeted_cents"] == 10800000
    assert "role" not in line and "fte" not in line
    assert stand["moment"]["statement"]
    assert stand["quotes"][0]["content"]["total_cents"] == 10800000


async def test_the_address_of_a_signing_link_is_for_who_manages(walked):
    email = walked.cast.signer.email
    offered = next(item for item in walked.seen if item.label == "aangeboden").seq
    owner = await walked.stand(offered, walked.cast.owner)
    assert owner["quotes"][0]["offers"][0]["recipient"] == email
    assert email in owner["moment"]["statement"]
    for person in (walked.cast.reader, walked.cast.beheerder):
        stand = await walked.stand(offered, person)
        assert stand["quotes"][0]["offers"][0]["recipient"] is None
        assert email not in json.dumps(stand)
        assert stand["moment"]["statement"] == "Offerte aangeboden met een tekenlink."
        moments = await walked.moments(person)
        assert email not in json.dumps(moments)


async def test_where_a_signing_link_stood_is_for_who_manages(walked):
    seen = {item.label: item for item in walked.seen}
    owner = walked.cast.owner
    offered = await walked.stand(seen["aangeboden"].seq, owner)
    link = offered["quotes"][0]["offers"][0]["invitation"]
    assert set(link) == {
        "state",
        "expires_at",
        "opened_at",
        "used_at",
        "withdrawn_at",
    }
    assert link["state"] == "invited"
    assert link["used_at"] is None
    signed = await walked.stand(seen["getekend"].seq, owner)
    link = signed["quotes"][0]["offers"][0]["invitation"]
    assert link["state"] == "signed"
    assert link["used_at"] is not None

    for person in (walked.cast.reader, walked.cast.beheerder):
        stand = await walked.stand(seen["getekend"].seq, person)
        assert stand["quotes"][0]["offers"][0]["invitation"] is None
        assert "used_at" not in json.dumps(stand)
    for person in (walked.cast.member, walked.cast.planner):
        stand = await walked.stand(seen["getekend"].seq, person)
        assert "offers" not in stand["quotes"][0]
        assert "used_at" not in json.dumps(stand)


async def test_what_changed_around_a_case_takes_its_values_to_who_reads_them(
    walked, db_session
):
    cast = walked.cast
    await walked.call(
        cast.beheerder,
        "patch",
        "/api/instance-settings",
        json={
            "values": {
                quote_approval.MODE.key: "from_amount",
                quote_approval.THRESHOLD.key: 12345600,
            }
        },
    )
    await rates.set_rate_band(db_session, YEAR, "A", 950000, actor=cast.beheerder)
    await walked.step(
        "regel",
        cast.owner,
        "post",
        f"/api/assignments/{walked.assignment_id}/budget-lines",
        on=7,
        json=line_body(role="Ontwikkelaar", rate_category="B"),
    )
    seq = walked.seen[-1].seq

    without_values = [
        "De tarieven zijn gewijzigd.",
        "Interne goedkeuring is nu nodig vanaf een bedrag.",
    ]
    for person in (cast.member, cast.planner):
        stand = await walked.stand(seq, person)
        assert stand["outside"] == without_values
        assert "outside_values" not in stand
        told = json.dumps(stand["outside"], ensure_ascii=False)
        assert "123.456" not in told and "categorie" not in told
    for person in (cast.reader, cast.owner, cast.beheerder):
        stand = await walked.stand(seq, person)
        assert stand["outside"] == without_values
        assert stand["outside_values"] == [
            f"Tarief van categorie A op Tarieven {YEAR} gewijzigd.",
            "Interne goedkeuring is nu nodig vanaf € 123.456.",
        ]


async def test_an_outsider_is_told_nothing(walked):
    outsider = walked.cast.outsider
    aid = walked.assignment_id
    client = walked.as_person(outsider)
    for path in (
        f"/api/assignments/{aid}/chronicle",
        f"/api/assignments/{aid}/chronicle/{walked.seen[-1].seq}",
    ):
        response = await client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_seq_that_is_no_moment_of_this_chronicle_is_not_found(
    walked, db_session
):
    other = Walk(walked.client, db_session, walked.cast)
    await other.begin(0)
    await other.step(
        "regel",
        walked.cast.owner,
        "post",
        f"/api/assignments/{other.assignment_id}/budget-lines",
        on=1,
        json=line_body(),
    )
    client = walked.as_person(walked.cast.beheerder)
    aid = walked.assignment_id
    audit_row = await db_session.scalar(
        select(func.max(StreamEvent.seq)).where(
            StreamEvent.case_id == UUID(aid), StreamEvent.action.is_not(None)
        )
    )
    for seq in (other.seen[-1].seq, audit_row, 0, 999999999999):
        response = await client.get(f"/api/assignments/{aid}/chronicle/{seq}")
        assert response.status_code == 404, seq
        assert response.headers["content-type"].startswith("application/problem+json")


async def test_an_assignment_that_does_not_exist_is_not_found(walked):
    client = walked.as_person(walked.cast.beheerder)
    missing = "00000000-0000-4000-8000-000000000001"
    for path in (
        f"/api/assignments/{missing}/chronicle",
        f"/api/assignments/{missing}/chronicle/1",
    ):
        assert (await client.get(path)).status_code == 404, path


async def test_reading_writes_nothing(walked, db_session):
    async def count() -> int:
        await db_session.flush()
        return await db_session.scalar(
            select(func.count())
            .select_from(StreamEvent)
            .where(StreamEvent.type != READ_TYPE)
        )

    async def facts() -> int:
        return len(
            await ChronicleRepository(db_session).grams(UUID(walked.assignment_id))
        )

    before, before_facts = await count(), await facts()
    for person in (walked.cast.beheerder, walked.cast.owner, walked.cast.member):
        await walked.moments(person)
        for seen in walked.seen:
            await walked.stand(seen.seq, person)
    assert await count() == before
    assert await facts() == before_facts


async def test_a_fact_is_no_line_in_the_history(walked):
    aid = walked.assignment_id

    async def events(person, **params):
        client = walked.as_person(person)
        response = await client.get(
            "/api/events", params={"limit": 200, "case_id": aid, **params}
        )
        assert response.status_code == 200, response.text
        return response.json()["items"]

    for person in (walked.cast.reader, walked.cast.owner, walked.cast.planner):
        kinds = {item["subject_kind"] for item in await events(person, kind="all")}
        assert kinds, "the history itself stays readable"
        assert SUBJECT_KIND not in kinds
    # The one who keeps the instance reads the stream as it is, not the history.
    kept = await events(walked.cast.beheerder, kind="all")
    assert SUBJECT_KIND in {item["subject_kind"] for item in kept}
    changes = await events(walked.cast.beheerder, kind="changes")
    assert SUBJECT_KIND not in {item["subject_kind"] for item in changes}


async def test_erased_values_leave_the_stand_incomplete_and_the_chain_whole(
    walked, db_session
):
    case = UUID(walked.assignment_id)
    seen = {item.label: item for item in walked.seen}
    erased = seen["offerte"].seq
    assert await _erase(db_session, StreamEvent.seq == erased, reason="test", about={})
    await db_session.flush()

    assert (await verify_stream(db_session)).intact
    report = await differences(db_session, case)
    assert report.checked is False and report.reason == "er zijn waarden gewist"
    with pytest.raises(ValueError, match="niet te herstellen: er zijn waarden gewist"):
        await rebuild(db_session, case)

    stand = await walked.stand(erased)
    assert stand["incomplete"] is True
    assert stand["moment"]["erased"] is True
    assert stand["moment"]["title"] == "Offerte gemaakt"
    assert stand["moment"]["statement"] == "Offerte gemaakt."
    assert stand["moment"]["effective_on"] is None
    assert stand["course"] is None, "nobody is told whose turn it was on half a story"
    assert stand["quotes"] == []

    later = await walked.stand(seen["gevraagd"].seq)
    assert later["incomplete"] is True
    earlier = await walked.stand(seen["regel"].seq)
    assert earlier["incomplete"] is False
    assert earlier["course"] is not None
    # What is left of the moment the reader may know, in the list too.
    moments = {item["seq"]: item for item in await walked.moments(walked.cast.member)}
    assert moments[erased]["erased"] is True
    assert moments[erased]["title"] == "Offerte gemaakt"


async def test_a_stand_on_half_a_story_states_no_total_and_no_status(
    walked, db_session
):
    await walked.step(
        "tweede regel",
        walked.cast.owner,
        "post",
        f"/api/assignments/{walked.assignment_id}/budget-lines",
        on=7,
        json=line_body(role="Ontwikkelaar", rate_category="B"),
    )
    seen = {item.label: item for item in walked.seen}
    whole = await walked.stand(seen["tweede regel"].seq)
    assert whole["budget"]["total_budgeted_cents"] > 10800000
    assert await _erase(
        db_session, StreamEvent.seq == seen["regel"].seq, reason="test", about={}
    )

    for label in ("regel", "offerte", "getekend", "tweede regel"):
        stand = await walked.stand(seen[label].seq)
        budget = stand["budget"]
        assert stand["incomplete"] is True, label
        assert budget["total_budgeted_cents"] is None, label
        assert budget["subtotals_by_year"] == {}, label
        assert budget["previous_total_cents"] is None, label
        assert budget["pricing_error"] is None, label
        assert all(line["budgeted_cents"] is None for line in budget["lines"]), label
        assert stand["assignment"]["status"] == "", label
        assert stand["assignment"]["status_label"] == "Onbekend", label
        assert stand["course"] is None, label
    after = await walked.stand(seen["tweede regel"].seq)
    assert [line["description"] for line in after["budget"]["lines"]] == [
        "Ontwikkelaar"
    ], "what is left of the lines is still told"
    assert after["quotes"], "a quote keeps its own frozen values"

    before = await walked.stand(seen["gemaakt"].seq)
    assert before["incomplete"] is False
    assert before["assignment"]["status_label"] == "In voorbereiding"


async def test_an_erased_allocation_of_the_case_makes_its_stand_incomplete(
    walked, client, db_session
):
    seen = {item.label: item for item in walked.seen}
    other = Walk(client, db_session, walked.cast)
    await other.begin(0)
    await other.step(
        "regel",
        walked.cast.owner,
        "post",
        f"/api/assignments/{other.assignment_id}/budget-lines",
        on=1,
        json=line_body(),
    )
    erased = await _erase(
        db_session, StreamEvent.subject_kind == "allocation", reason="test", about={}
    )
    assert erased == 1

    after = await walked.stand(seen["offerte"].seq)
    assert after["incomplete"] is True
    assert after["course"] is None
    assert after["budget"]["total_budgeted_cents"] is None
    assert after["assignment"]["status_label"] == "Onbekend"
    assert after["moment"]["erased"] is False
    before = await walked.stand(seen["regel"].seq)
    assert before["incomplete"] is False, "that record came after this moment"
    assert before["budget"]["total_budgeted_cents"] == 10800000
    await other.check_every_look_back()


async def test_after_retention_a_new_case_stands_whole_and_an_erased_one_says_it_is_not(
    client, db_session, cast
):
    old = Walk(client, db_session, cast)
    await old.call(
        cast.beheerder,
        "patch",
        "/api/instance-settings",
        json={"values": {quote_approval.MODE.key: "always"}},
    )
    await old.begin(0)
    await old.step(
        "regel",
        cast.owner,
        "post",
        f"/api/assignments/{old.assignment_id}/budget-lines",
        on=1,
        json=line_body(),
    )
    await instance_settings.set_values(
        db_session, {RETENTION_DAYS.key: 365}, actor=cast.beheerder
    )
    await db_session.flush()
    later = datetime.now(UTC) + timedelta(days=400)
    await apply_retention(db_session, now=later)
    kept = await old.stand(old.seen[-1].seq)
    assert kept["incomplete"] is False, "erasing by age leaves an assignment alone"
    # A case goes whole at the end of its own period (ADR 0057).
    assert await _erase(
        db_session,
        StreamEvent.case_id == UUID(old.assignment_id),
        reason="retention",
        about={},
    )

    await rates.set_rate_band(db_session, YEAR, "D", 1900000, actor=cast.beheerder)
    new = Walk(client, db_session, cast)
    await new.begin(0)
    await new.step(
        "regel",
        cast.owner,
        "post",
        f"/api/assignments/{new.assignment_id}/budget-lines",
        on=1,
        json=line_body(),
    )
    quote = await new.step(
        "offerte",
        cast.owner,
        "post",
        f"/api/assignments/{new.assignment_id}/quotes",
        on=2,
        json={},
    )
    await new.check_every_look_back()
    stand = await new.stand(new.seen[-1].seq)
    assert stand["incomplete"] is False
    assert stand["course"]["current_key"] == "goedkeuring", "the rule of then is kept"
    assert stand["budget"]["total_budgeted_cents"] == quote["total_cents"]

    gone = await old.stand(old.seen[-1].seq)
    assert gone["incomplete"] is True
    assert gone["moment"]["erased"] is True
    assert gone["course"] is None
    assert gone["budget"]["total_budgeted_cents"] is None


async def test_an_erased_book_counts_only_until_a_later_fact_holds_the_book(
    client, db_session, cast
):
    walk = Walk(client, db_session, cast)
    await walk.begin(0)

    async def line(label, on, **changes):
        await walk.step(
            label,
            cast.owner,
            "post",
            f"/api/assignments/{walk.assignment_id}/budget-lines",
            on=on,
            json=line_body(**changes),
        )

    await line("eerste boek", 1)
    await rates.set_rate_band(db_session, YEAR, "D", 2000000, actor=cast.beheerder)
    await walk.step(
        "tweede boek",
        cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/quotes",
        on=2,
        json={},
    )
    await rates.set_rate_band(db_session, YEAR, "D", 2200000, actor=cast.beheerder)
    await line("derde boek", 3, role="Ontwikkelaar", rate_category="B")
    await walk.check_every_look_back()

    seen = {item.label: item for item in walk.seen}
    second_before = await walk.stand(seen["tweede boek"].seq)
    third_before = await walk.stand(seen["derde boek"].seq)
    books = await ChronicleRepository(db_session).rate_grams()
    assert len(books) == 3
    assert await _erase(
        db_session, StreamEvent.seq == books[1].seq, reason="t", about={}
    )

    second = await walk.stand(seen["tweede boek"].seq)
    assert second["incomplete"] is False, "the values of the case itself are whole"
    assert comparable(second["course"]) == comparable(second_before["course"])
    assert second["assignment"]["status"] == second_before["assignment"]["status"]
    assert second["quotes"] == second_before["quotes"]
    assert second["budget"]["total_budgeted_cents"] is None, "what priced is unknown"
    assert second["budget"]["pricing_error"] is None, "and it was no missing card"
    assert second["budget"]["previous_total_cents"] is None
    assert second["budget"]["subtotals_by_year"] == {}
    assert [line["budgeted_cents"] for line in second["budget"]["lines"]] == [None]
    assert second["outside"] == ["De tarieven zijn gewijzigd."]
    assert second["outside_values"] == second["outside"], "that it happened remains"

    third = await walk.stand(seen["derde boek"].seq)
    assert third["incomplete"] is False
    assert (
        third["budget"]["total_budgeted_cents"]
        == (third_before["budget"]["total_budgeted_cents"])
    ), "a later fact holds the whole book"
    assert third["budget"]["previous_total_cents"] is None, "that total is unknown"
    assert third["outside_values"] == third_before["outside_values"]

    first = await walk.stand(seen["eerste boek"].seq)
    assert first["budget"]["total_budgeted_cents"] == 10800000


async def test_erased_settings_leave_a_stand_whole(client, db_session, cast):
    walk = Walk(client, db_session, cast)
    for value in (365, 730):
        await instance_settings.set_values(
            db_session, {RETENTION_DAYS.key: value}, actor=cast.beheerder
        )
    await walk.call(
        cast.beheerder,
        "patch",
        "/api/instance-settings",
        json={"values": {quote_approval.MODE.key: "always"}},
    )
    await walk.begin(0)
    assert (
        await _erase(
            db_session,
            StreamEvent.subject_kind == "instance_setting",
            reason="test",
            about={},
        )
        == 3
    )
    stand = await walk.stand(walk.seen[0].seq)
    assert stand["incomplete"] is False
    assert stand["course"] is not None
    assert stand["outside"] == []


async def test_the_fact_that_made_the_case_erased(walked, db_session):
    birth = walked.seen[0].seq
    assert await _erase(db_session, StreamEvent.seq == birth, reason="test", about={})
    stand = await walked.stand(birth)
    assert stand["incomplete"] is True
    assert stand["assignment"]["name"] == "Voorbeeldtraject"
    assert stand["assignment"]["status_label"] == "Onbekend"
    assert stand["course"] is None
    assert (await verify_stream(db_session)).intact


async def test_later_known_tells_who_reads_the_basics_only_the_title(
    client, db_session, cast
):
    walk = Walk(client, db_session, cast)
    await walk.begin(0)
    await walk.step(
        "regel",
        cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=1,
        json=line_body(),
    )
    quote = await walk.step(
        "offerte",
        cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/quotes",
        on=2,
        json={},
    )
    await walk.step(
        "op dag 5",
        cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=5,
        json=line_body(role="Ontwikkelaar", rate_category="B"),
    )
    await walk.step(
        "op dag 10",
        cast.owner,
        "post",
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        on=10,
        data={
            "signer_name": "Directeur Voorbeeld",
            "signer_email": "directeur@opdrachtgever.example",
            "signed_at": day(3).isoformat(),
        },
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )
    seq = next(item for item in walk.seen if item.label == "op dag 5").seq
    told = (await walk.stand(seq, cast.reader))["later_known"]
    assert "Directeur Voorbeeld" in told[0]["statement"]
    assert told[0]["effective_on"] == clock.local_date(day(3)).isoformat()
    planner = (await walk.stand(seq, cast.planner))["later_known"]
    assert set(planner[0]) == {"seq", "title"}
    assert planner[0]["title"] == "Getekende pdf vastgelegd"
    assert "Directeur Voorbeeld" not in json.dumps(planner)

    signed_on = clock.local_date(day(3)).isoformat()
    for moment in await walk.moments(cast.planner):
        assert "effective_on" not in moment
        assert "statement" not in moment
        stand = await walk.stand(moment["seq"], cast.planner)
        assert not _keys(stand) & {"effective_on", "quote_date"}, moment["fact"]
        assert signed_on not in json.dumps(stand), moment["fact"]
    recorded = next(item for item in walk.seen if item.label == "op dag 10").seq
    as_reader = await walk.stand(recorded, cast.reader)
    assert as_reader["moment"]["effective_on"] == signed_on
    assert as_reader["assignment"]["quote_date"]
