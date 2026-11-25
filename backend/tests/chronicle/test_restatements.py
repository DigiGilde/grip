"""Taking a typed text out of a moment, through the routes (ADR 0057).

A beheerder removes a text that never belonged; the fact is erased and recorded
again without it, and every stand stays whole. All names and texts are fictional.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from httpx import Response
from sqlalchemy import select

from grip.chronicle import words
from grip.chronicle.restate import PLACEHOLDER, RESTATED, contains
from grip.chronicle.verify import differences
from grip.core import clock
from grip.events.check import verify_stream
from grip.events.retention import ERASED_TYPE, _erase
from grip.models.assignment import Assignment, BudgetLine
from grip.models.quote import Quote
from grip.models.stream_event import StreamEvent
from grip.repositories.chronicle import ChronicleRepository
from grip.services import assignments
from tests.chronicle.walking import Walk, comparable, day, line_body, make_cast

TEXT = "Afwezig wegens een operatie aan de knie"
SENTENCE = "De tekst staat ook in offerte {}; die blijft zoals ze is gemaakt."


@pytest.fixture
async def cast(db_session, create_person):
    return await make_cast(db_session, create_person)


@pytest.fixture
def walk(client, db_session, cast):
    return Walk(client, db_session, cast)


def _path(walk: Walk, seq: int) -> str:
    return f"/api/assignments/{walk.assignment_id}/chronicle/{seq}/restate"


async def _restate(walk: Walk, seq: int, *columns: str, on: int = 9) -> dict[str, Any]:
    return await walk.step(
        "tekst verwijderd",
        walk.cast.beheerder,
        "post",
        _path(walk, seq),
        on=on,
        json={"columns": list(columns)},
    )


async def _try(walk: Walk, seq: int, columns: list[str], person=None) -> Response:
    client = walk.as_person(person or walk.cast.beheerder)
    return await client.post(_path(walk, seq), json={"columns": columns})


async def _line(walk: Walk, on: int, **changes: Any) -> dict[str, Any]:
    return await walk.step(
        "regel",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        on=on,
        json=line_body(**changes),
    )


async def _herstelfeiten(db_session, walk: Walk) -> list[Any]:
    recorded = await ChronicleRepository(db_session).recorded(UUID(walk.assignment_id))
    return [gram for gram in recorded if gram.fact == RESTATED]


async def _erased(db_session, seq: int) -> bool:
    erased_at = await db_session.scalar(
        select(StreamEvent.erased_at).where(StreamEvent.seq == seq)
    )
    return erased_at is not None


async def _still_holding(db_session, walk: Walk, text: str) -> list[str]:
    """The events of the case whose values still hold the text."""
    rows = await db_session.execute(
        select(
            StreamEvent.type,
            StreamEvent.old_value,
            StreamEvent.new_value,
            StreamEvent.payload,
            StreamEvent.note,
        ).where(StreamEvent.case_id == UUID(walk.assignment_id))
    )
    return [
        row.type
        for row in rows
        if any(
            contains(value, [text])
            for value in (row.old_value, row.new_value, row.payload, row.note)
        )
    ]


async def _change_lines(db_session, walk: Walk, subject_kind: str) -> list[Any]:
    return list(
        (
            await db_session.execute(
                select(StreamEvent.seq, StreamEvent.erased_at)
                .where(
                    StreamEvent.case_id == UUID(walk.assignment_id),
                    StreamEvent.subject_kind == subject_kind,
                    StreamEvent.action.is_not(None),
                )
                .order_by(StreamEvent.seq)
            )
        ).all()
    )


async def test_a_note_goes_and_every_stand_stays_whole(walk, db_session):
    await walk.begin(0, notes=TEXT)
    await _line(walk, 1)
    born = walk.seen[0].seq
    aid = UUID(walk.assignment_id)
    before = await walk.stand(born)
    assert before["removable_texts"] == [
        {
            "key": "assignment.name",
            "label": "Naam",
            "text": "Voorbeeldtraject",
            "kept": [],
        },
        {"key": "assignment.notes", "label": "Notities", "text": TEXT, "kept": []},
    ]

    body = await _restate(walk, born, "assignment.notes", on=2)

    assert await _erased(db_session, born), "the fact that held the text is erased"
    (herstel,) = await _herstelfeiten(db_session, walk)
    assert herstel.actor_person_id == walk.cast.beheerder.id
    assert herstel.fields["restates"] == born
    assert herstel.fields["fact"] == "assignment_created"
    assert herstel.fields["removed"] == [
        {"path": "assignment.notes", "label": "Notities"}
    ]
    assert herstel.fields["patches"] == [
        {"table": "assignment", "id": walk.assignment_id, "values": {"notes": None}}
    ]
    assert (
        await db_session.scalar(select(Assignment.notes).where(Assignment.id == aid))
        is None
    )
    report = await differences(db_session, aid)
    assert report.checked and report.differences == []
    assert (await verify_stream(db_session)).intact
    assert await _still_holding(db_session, walk, TEXT) == []
    erasure = await db_session.scalar(
        select(StreamEvent.new_value)
        .where(StreamEvent.type == ERASED_TYPE)
        .order_by(StreamEvent.seq.desc())
        .limit(1)
    )
    assert erasure["reason"] == "restated"
    assert erasure["assignment_id"] == walk.assignment_id
    assert erasure["restated_by"] == [herstel.seq]

    stand = body["stand"]
    assert body["kept"] == []
    assert stand["moment"]["seq"] == born
    assert stand["moment"]["erased"] is False
    assert stand["incomplete"] is False
    assert stand["course"] is not None
    assert stand["assignment"]["notes"] is None
    assert stand["assignment"]["name"] == "Voorbeeldtraject"
    assert [item["seq"] for item in stand["restated"]] == [herstel.seq]
    assert stand["restated"][0]["removed"] == ["Notities"]
    assert [item["key"] for item in stand["removable_texts"]] == ["assignment.name"]
    # A cut before the herstelfeit reads the moment whole as well.
    (cut,) = await ChronicleRepository(db_session).grams(aid, upto=born)
    assert cut.restated_by == (herstel.seq,)
    assert cut.fields is not None and cut.fields["assignment"]["notes"] is None
    for seen in walk.seen:
        then = await walk.stand(seen.seq)
        assert then["incomplete"] is False, seen.label
        assert TEXT not in json.dumps(then), seen.label

    moments = await walk.moments(walk.cast.beheerder)
    last = moments[-1]
    assert (last["seq"], last["fact"], last["title"]) == (
        herstel.seq,
        RESTATED,
        "Tekst verwijderd",
    )
    assert last["actor_name"] == walk.cast.beheerder.name
    day_said = words.day_words(clock.local_date(day(0)))
    assert last["statement"] == (
        f"Notities verwijderd uit het moment Opdracht toegevoegd van {day_said}."
    )
    assert TEXT not in json.dumps(moments)


async def test_a_note_changed_later_leaves_the_row_alone(walk, db_session):
    await walk.begin(0, notes=TEXT)
    changed = await walk.step(
        "notitie",
        walk.cast.owner,
        "patch",
        f"/api/assignments/{walk.assignment_id}",
        on=1,
        json={"notes": "Iets anders"},
    )
    assert changed["notes"] == "Iets anders"
    born, noted = walk.seen[0].seq, walk.seen[1].seq
    change_line = (await _change_lines(db_session, walk, "assignment"))[-1]

    await _restate(walk, born, "assignment.notes", on=2)

    (herstel,) = await _herstelfeiten(db_session, walk)
    assert herstel.fields["patches"] == [], "a later fact already changed the column"
    aid = UUID(walk.assignment_id)
    notes = await db_session.scalar(
        select(Assignment.notes).where(Assignment.id == aid)
    )
    assert notes == "Iets anders"
    assert not await _erased(db_session, noted), "that fact never held the text"
    assert await _erased(db_session, change_line.seq), "the change line from the text"
    assert await _still_holding(db_session, walk, TEXT) == []
    assert (await walk.stand(born))["assignment"]["notes"] is None
    assert (await walk.stand(noted))["assignment"]["notes"] == "Iets anders"


async def test_the_same_text_in_another_fact_goes_with_it(walk, db_session):
    await walk.begin(0, notes=TEXT)
    added = await _line(walk, 1, description=TEXT)
    line_id = UUID(added["lines"][0]["id"])
    born, line_moment = walk.seen[0].seq, walk.seen[1].seq

    await _restate(walk, born, "assignment.notes", on=2)

    herstel = await _herstelfeiten(db_session, walk)
    assert [item.fields["restates"] for item in herstel] == [born, line_moment]
    assert herstel[1].fields["removed"] == [
        {"path": "line.detail", "label": "Omschrijving"}
    ]
    assert await _erased(db_session, born) and await _erased(db_session, line_moment)
    detail = await db_session.scalar(
        select(BudgetLine.detail).where(BudgetLine.id == line_id)
    )
    assert detail == PLACEHOLDER
    made, patched = await _change_lines(db_session, walk, "budget_line")
    assert made.erased_at is not None, "the change line that added the line"
    assert patched.erased_at is None, "the change line of the herstelfeit"
    assert await _still_holding(db_session, walk, TEXT) == []
    stand = await walk.stand(line_moment)
    assert stand["incomplete"] is False
    assert (
        stand["budget"]["lines"][0]["description"] == f"Productmanager: {PLACEHOLDER}"
    )
    assert [item["removed"] for item in stand["restated"]] == [["Omschrijving"]]


async def test_an_issued_quote_keeps_the_text_and_is_named(walk, db_session):
    await walk.begin(0)
    await _line(walk, 1, description=TEXT)
    quote = await walk.step(
        "offerte",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/quotes",
        on=2,
        json={},
    )
    line_moment, made = walk.seen[1].seq, walk.seen[2].seq
    quotes_path = f"/api/assignments/{walk.assignment_id}/quotes"
    listed = await walk.call(walk.cast.owner, "get", quotes_path)
    assert listed["budget_moved"] is False
    course_then = comparable((await walk.stand(made))["course"])
    frozen = await db_session.scalar(
        select(Quote.canonical).where(Quote.id == UUID(quote["id"]))
    )
    kept = SENTENCE.format(quote["reference"])
    offered = (await walk.stand(line_moment))["removable_texts"]
    assert offered == [
        {
            "key": "budget_line.detail",
            "label": "Omschrijving",
            "text": TEXT,
            "kept": [kept],
        }
    ]

    body = await _restate(walk, line_moment, "budget_line.detail", on=3)

    assert body["kept"] == [kept]
    after = await db_session.scalar(
        select(Quote.canonical).where(Quote.id == UUID(quote["id"]))
    )
    assert after == frozen, "an issued quote is a frozen snapshot"
    stand = await walk.stand(made)
    assert stand["incomplete"] is False
    assert TEXT in json.dumps(stand["quotes"][0]["content"])
    assert (
        stand["budget"]["lines"][0]["description"] == f"Productmanager: {PLACEHOLDER}"
    )
    # The budget no longer says what the open quote says, live and looking back:
    # a new quote is the way to get the text out of the quote too.
    listed = await walk.call(walk.cast.owner, "get", quotes_path)
    assert listed["budget_moved"] is True
    assert comparable(stand["course"]) != course_then


async def test_a_verbal_agreement_loses_its_note_and_its_reason(walk, db_session):
    await walk.begin(0)
    await _line(walk, 1)
    for on, (target, reason) in enumerate(
        (("requested", None), ("quoted", None), ("verbally_agreed", TEXT)), start=2
    ):
        await walk.step(
            target,
            walk.cast.owner,
            "post",
            f"/api/assignments/{walk.assignment_id}/transition",
            on=on,
            json={"target": target, **({"reason": reason} if reason else {})},
        )
    agreed = walk.seen[-1].seq
    stand = await walk.stand(agreed)
    assert stand["moment"]["lines"] == [TEXT]
    # The note stands twice in the fact, as the note and as the reason.
    assert [item["key"] for item in stand["removable_texts"]] == [
        "assignment.verbal_agreement_note"
    ]

    body = await _restate(walk, agreed, "assignment.verbal_agreement_note", on=5)

    stand = body["stand"]
    assert stand["moment"]["lines"] == []
    assert stand["assignment"]["verbal_agreement_note"] is None
    assert stand["assignment"]["status"] == "verbally_agreed"
    aid = UUID(walk.assignment_id)
    note = await db_session.scalar(
        select(Assignment.verbal_agreement_note).where(Assignment.id == aid)
    )
    assert note is None
    assert await _still_holding(db_session, walk, TEXT) == []


async def test_a_reason_alone_leaves_every_row_alone(walk, db_session):
    await walk.begin(0)
    await _line(walk, 1)
    await walk.step(
        "aangevraagd",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/transition",
        on=2,
        json={"target": "requested"},
    )
    await walk.step(
        "afgesloten",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/transition",
        on=3,
        json={"target": "cancelled", "reason": TEXT},
    )
    ended = walk.seen[-1].seq
    body = await _restate(walk, ended, "reason", on=4)
    (herstel,) = await _herstelfeiten(db_session, walk)
    assert herstel.fields["patches"] == []
    assert herstel.fields["removed"] == [{"path": "reason", "label": "Reden"}]
    assert body["stand"]["moment"]["lines"] == []
    assert body["stand"]["assignment"]["status"] == "cancelled"
    assert await _still_holding(db_session, walk, TEXT) == []


async def test_taking_out_a_text_of_a_restated_moment_again(walk, db_session):
    await walk.begin(0, notes=TEXT, name="Opdracht met een naam die weg moet")
    born = walk.seen[0].seq
    await _restate(walk, born, "assignment.notes", on=1)
    body = await _restate(walk, born, "assignment.name", on=2)
    first, second = await _herstelfeiten(db_session, walk)
    assert first.erased, "the first herstelfeit held the name too"
    assert second.fields["restates"] == first.seq
    stand = body["stand"]
    assert stand["incomplete"] is False
    assert stand["assignment"]["name"] == PLACEHOLDER
    assert stand["assignment"]["notes"] is None
    assert [item["removed"] for item in stand["restated"]] == [["Notities"], ["Naam"]]
    assert stand["removable_texts"] == []
    aid = UUID(walk.assignment_id)
    assert (
        await db_session.scalar(select(Assignment.name).where(Assignment.id == aid))
        == PLACEHOLDER
    )
    assert "Opdracht met een naam die weg moet" not in json.dumps(
        await walk.moments(walk.cast.beheerder)
    )
    report = await differences(db_session, aid)
    assert report.checked and report.differences == []


async def test_a_closed_dossier_keeps_no_text_that_never_belonged(walk, db_session):
    await walk.begin(0, notes=TEXT)
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

    body = await _restate(walk, walk.seen[0].seq, "assignment.notes", on=9)

    assert body["stand"]["assignment"]["notes"] is None
    aid = UUID(walk.assignment_id)
    row = (
        await db_session.execute(
            select(Assignment.notes, Assignment.dossier_closed_on).where(
                Assignment.id == aid
            )
        )
    ).one()
    assert row.notes is None
    assert row.dossier_closed_on is not None, "the dossier stays closed"
    last = await walk.stand(walk.seen[-1].seq)
    assert last["course"]["ended"] == "Dossier gesloten"


# -- who may, and what is not there ------------------------------------------


async def _staffed(walk: Walk, db_session) -> None:
    """A member on the case: who reads only class A of it."""
    budget = await _line(walk, 1)
    await assignments.add_allocation(
        db_session,
        UUID(budget["lines"][0]["id"]),
        walk.cast.member.id,
        start_date=day(0).date().replace(month=1, day=1),
        end_date=day(0).date().replace(month=12, day=31),
        fte_pct=50,
        actor=walk.cast.owner,
    )


@pytest.mark.parametrize("who", ["owner", "planner", "reader", "member"])
async def test_only_the_beheerder_takes_a_text_out(walk, db_session, who):
    await walk.begin(0, notes=TEXT)
    await _staffed(walk, db_session)
    born = walk.seen[0].seq
    response = await _try(walk, born, ["assignment.notes"], getattr(walk.cast, who))
    assert response.status_code == 403, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert not await _erased(db_session, born)
    assert await _herstelfeiten(db_session, walk) == []


async def test_an_outsider_is_told_nothing(walk, db_session):
    await walk.begin(0, notes=TEXT)
    born = walk.seen[0].seq
    response = await _try(walk, born, ["assignment.notes"], walk.cast.outsider)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert not await _erased(db_session, born)


async def test_what_is_no_moment_of_this_case_is_not_found(walk, db_session):
    other = Walk(walk.client, db_session, walk.cast)
    await other.begin(0, notes=TEXT)
    await walk.begin(0, notes=TEXT)
    await _line(walk, 1)
    audit_row = await db_session.scalar(
        select(StreamEvent.seq)
        .where(
            StreamEvent.case_id == UUID(walk.assignment_id),
            StreamEvent.action.is_not(None),
        )
        .limit(1)
    )
    for seq in (other.seen[0].seq, audit_row, 0, 999999999999):
        response = await _try(walk, seq, ["assignment.notes"])
        assert response.status_code == 404, seq
    missing = "00000000-0000-4000-8000-000000000001"
    client = walk.as_person(walk.cast.beheerder)
    response = await client.post(
        f"/api/assignments/{missing}/chronicle/1/restate",
        json={"columns": ["assignment.notes"]},
    )
    assert response.status_code == 404


async def test_a_moment_erased_without_a_herstelfeit_is_not_found(walk, db_session):
    await walk.begin(0, notes=TEXT)
    born = walk.seen[0].seq
    assert await _erase(db_session, StreamEvent.seq == born, reason="test", about={})
    response = await _try(walk, born, ["assignment.notes"])
    assert response.status_code == 404


async def test_a_text_that_is_not_there_is_refused_in_words(walk, db_session):
    await walk.begin(0, notes=TEXT)
    born = walk.seen[0].seq
    for columns, said in (
        (
            ["assignment.verbal_agreement_note"],
            "Dit moment heeft geen tekst bij mondeling akkoord.",
        ),
        (["budget_line.detail"], "Dit moment heeft geen tekst bij omschrijving."),
        (["iets"], "Dit moment heeft geen tekst bij iets."),
        ([], "Kies de tekst die je wilt verwijderen."),
    ):
        response = await _try(walk, born, columns)
        assert response.status_code == 422, columns
        assert response.json()["detail"] == said
    assert not await _erased(db_session, born)
    assert await _herstelfeiten(db_session, walk) == []


async def test_which_texts_can_go_is_told_only_to_who_may_take_them_out(
    walk, db_session
):
    await walk.begin(0, notes=TEXT)
    await _staffed(walk, db_session)
    born = walk.seen[0].seq
    beheerder = await walk.stand(born, walk.cast.beheerder)
    assert [item["text"] for item in beheerder["removable_texts"]] == [
        "Voorbeeldtraject",
        TEXT,
    ]
    for who in ("owner", "planner", "reader", "member"):
        stand = await walk.stand(born, getattr(walk.cast, who))
        assert stand.get("removable_texts") is None, who
        assert "kept" not in json.dumps(stand), who
