"""The feed of updates: a curated, personal selection of the stream."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from grip.access.decider import LocalDecider
from grip.access.sql import SqlRelationSource
from grip.access.types import Subject
from grip.core.config import get_settings
from grip.events import news, stream, words
from grip.events.classification import SPECS
from grip.events.reading import EventAccess
from grip.models.stream_event import StreamEvent
from grip.services import events as domain_events


def _all_types() -> set[str]:
    types = {
        f"{kind}.{verb}" for kind in SPECS for verb in ("created", "updated", "deleted")
    }
    return types | set(domain_events.EVENT_TYPES) | {"data.read", "stream.erased"}


def test_every_type_is_news_or_explicitly_not():
    undecided = sorted(t for t in _all_types() if not news.is_decided(t))
    assert undecided == []
    # And never both: a type is on one list.
    assert news.NEWS_TYPES & news.OFF_TYPES == set()
    assert {
        t for t in news.NEWS_TYPES if t.partition(".")[0] in news.OFF_KINDS
    } == set()
    # What must never be news.
    for never in ("data.read", "login.created", "quote_draft.updated", "task.updated"):
        assert never not in news.NEWS_TYPES
    for off in ("instance_setting", "mail_outbox", "task", "data", "login"):
        assert off in news.OFF_KINDS
    assert len({rule.key for rule in news.NEWS}) == len(news.NEWS)
    assert all(rule.rank in (1, 2, 3) and rule.functions for rule in news.NEWS)


def _add(
    db,
    world,
    kind,
    *,
    actor,
    action="create",
    new=None,
    person=None,
    case=True,
    subject=None,
):
    return stream.append(
        db,
        subject=(kind, subject or uuid.uuid4()),
        action=action,
        actor_person_id=actor.id if actor else None,
        assignment_id=world.assignment.id if case else None,
        person_id=person.id if person else None,
        new=new or {},
    )


@pytest.fixture
async def day(db_session, world):
    """A day of work on the assignment, done by the owner."""
    db, owner = db_session, world.owner
    quote_id = uuid.uuid4()
    made = {
        "quote_made": _add(
            db,
            world,
            "quote",
            actor=owner,
            subject=quote_id,
            new={"total_cents": 123456},
        ),
        "quote_offered": _add(
            db, world, "quote_offer", actor=owner, new={"quote_id": str(quote_id)}
        ),
        "joined": _add(
            db,
            world,
            "allocation",
            actor=owner,
            person=world.member,
            new={"fte_pct": "80"},
        ),
        "scale": stream.append(
            db,
            subject=("person_scale", uuid.uuid4()),
            action="update",
            actor_person_id=world.beheerder.id,
            person_id=world.member.id,
            old={"billing_scale": 11},
            new={"billing_scale": 12},
        ),
        "draft": _add(
            db, world, "quote_draft", actor=owner, action="update", new={"text": "x"}
        ),
        "setting": stream.append(
            db, subject=("instance_setting", "instance"), action="update"
        ),
    }
    for month in ("2026-01", "2026-02", "2026-03"):
        made[f"close-{month}"] = _add(
            db, world, "month_close", actor=owner, new={"month": month}
        )
    await db.flush()
    return made


async def _feed(client, as_person, person, **params) -> dict:
    answer = await as_person(person).get(
        "/api/updates", params={"limiet": 50, **params}
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _texts(body: dict) -> list[str]:
    return [item["text"] for item in body["items"]]


async def test_a_burst_is_one_item_and_two_steps_are_one_sentence(
    client, as_person, world, day
):
    texts = _texts(await _feed(client, as_person, world.beheerder))
    assert "3 maanden afgesloten op Opdracht Alfa 2026 door Eva Eigenaar" in texts
    assert (
        "Offerte gemaakt en aangeboden voor Opdracht Alfa 2026 door Eva Eigenaar"
        in texts
    )
    assert not any(text.startswith("Offerte aangeboden") for text in texts)
    # The team of the day is one item too.
    assert "3 mensen ingezet op Opdracht Alfa 2026 door Eva Eigenaar" in texts
    # Never: a draft that was saved, a setting that was touched.
    kinds = {
        item["kind"]
        for item in (await _feed(client, as_person, world.beheerder))["items"]
    }
    assert kinds <= {rule.key for rule in news.NEWS} | {"quote_made_offered"}
    months = next(
        i
        for i in (await _feed(client, as_person, world.beheerder))["items"]
        if i["kind"] == "month_closed"
    )
    assert months["count"] == 3
    link = next(part for part in months["parts"] if part.get("href"))
    assert link == {
        "text": "Opdracht Alfa 2026",
        "href": f"/opdrachten/{world.assignment.id}/maandafsluiting",
    }


async def test_what_the_reader_did_is_not_news_to_them(client, as_person, world, day):
    owner = _texts(await _feed(client, as_person, world.owner))
    assert not any("maanden afgesloten" in text or "Offerte" in text for text in owner)
    assert not any("ingezet" in text for text in owner)


async def test_each_reader_gets_what_concerns_them(client, as_person, world, day):
    member = _texts(await _feed(client, as_person, world.member))
    # About themselves, said to them, and without the values.
    assert "Je bent ingezet op Opdracht Alfa 2026 door Eva Eigenaar" in member
    assert "Je hebt een nieuwe schaal" in member
    # The steps of a quote and the months are for who manages the assignment.
    assert not any("Offerte" in text or "afgesloten" in text for text in member)

    planner = _texts(await _feed(client, as_person, world.planner))
    assert "3 mensen ingezet op Opdracht Alfa 2026 door Eva Eigenaar" in planner
    assert not any("Offerte" in text or "afgesloten" in text for text in planner)
    assert not any("schaal" in text for text in planner)

    lezer = _texts(await _feed(client, as_person, world.lezer))
    assert any("3 maanden afgesloten" in text for text in lezer)
    assert not any("ingezet" in text or "schaal" in text for text in lezer)

    assert await _feed(client, as_person, world.outsider) == {
        "items": [],
        "new_count": 0,
        "next": None,
    }


async def test_the_feed_never_shows_a_value_or_what_cannot_be_opened(
    client, as_person, world, day, db_session
):
    decider = LocalDecider(
        SqlRelationSource(
            db_session, instance_base_uri=get_settings().INSTANCE_BASE_URI
        )
    )
    readers = {
        "beheerder": (world.beheerder, {"beheerder"}),
        "lezer": (world.lezer, {"lezer"}),
        "planner": (world.planner, {"planner"}),
        "owner": (world.owner, set()),
        "member": (world.member, set()),
        "colleague": (world.colleague, set()),
        "outsider": (world.outsider, set()),
    }
    seen = 0
    for name, (person, functions) in readers.items():
        access = EventAccess(
            db_session, decider, Subject.for_person(person.id, frozenset(functions))
        )
        body = await _feed(client, as_person, person)
        for item in body["items"]:
            seen += 1
            event = await db_session.scalar(
                select(StreamEvent).where(StreamEvent.seq == item["seq"])
            )
            assert await access.may_know(event), (name, item["text"])
            # Scales, rates and amounts are never in a sentence.
            assert "11" not in item["text"] and "12" not in item["text"].replace(
                "2026", ""
            )
            assert "123456" not in str(item) and "1.234" not in str(item)
            assert not words.CODE.search(item["text"]), item["text"]
    assert seen > 5


async def test_news_about_you_names_a_closed_assignment_without_a_link(
    client, as_person, world, db_session
):
    """News about the reader can name an assignment they cannot open: their
    own inzet that has not started, or one that is over. The name is theirs
    to know; a link to it would lead nowhere, so there is none."""
    _add(
        db_session,
        world,
        "allocation",
        actor=world.owner,
        person=world.outsider,
        new={"fte_pct": "50"},
    )
    await db_session.flush()

    closed = await _feed(client, as_person, world.outsider)
    item = next(item for item in closed["items"] if "ingezet" in item["text"])
    assert world.assignment.name in item["text"]
    assert not any(part.get("href") for part in item["parts"])

    # Whoever can open the assignment keeps the link.
    opened = await _feed(client, as_person, world.beheerder)
    item = next(item for item in opened["items"] if "ingezet" in item["text"])
    assert any(
        (part.get("href") or "").startswith(f"/opdrachten/{world.assignment.id}")
        for part in item["parts"]
    )


async def test_someone_who_may_not_know_who_gets_no_name(db_session, world, day):
    """The sentence about a person is built from what the reader may see."""
    decider = LocalDecider(
        SqlRelationSource(
            db_session, instance_base_uri=get_settings().INSTANCE_BASE_URI
        )
    )
    relations = SqlRelationSource(
        db_session, instance_base_uri=get_settings().INSTANCE_BASE_URI
    )

    class _NoNames(EventAccess):
        async def may_see_person(self, event):
            return False

    access = _NoNames(
        db_session,
        decider,
        Subject.for_person(world.planner.id, frozenset({"planner"})),
    )
    feed = await news.read(db_session, access, relations, limit=50)
    joined = [item.text for item in feed.items if item.kind == "joined"]
    assert joined and not any("Lot Lid" in text or "Cas" in text for text in joined)
    assert not any(item.kind == "scale" for item in feed.items)


async def test_the_cursor_pages_back_without_repeating(client, as_person, world, day):
    everything = _texts(await _feed(client, as_person, world.beheerder))
    paged, cursor = [], None
    for _ in range(40):
        body = await _feed(
            client,
            as_person,
            world.beheerder,
            limiet=2,
            **({"na": cursor} if cursor else {}),
        )
        assert len(body["items"]) <= 2
        paged += _texts(body)
        cursor = body["next"]
        if cursor is None:
            break
    assert cursor is None
    assert paged == everything and len(paged) == len(set(paged))


async def test_new_is_what_came_after_the_reader_last_looked(
    client, as_person, world, day, db_session
):
    reader = world.beheerder
    first = await _feed(client, as_person, reader)
    # Never looked: nothing is marked, there is no count to chase.
    assert first["new_count"] == 0 and not any(item["new"] for item in first["items"])

    assert (await as_person(reader).post("/api/updates/seen")).status_code == 204
    assert (await _feed(client, as_person, reader))["new_count"] == 0

    _add(
        db_session,
        world,
        "quote_acceptance",
        actor=world.owner,
        new={"form": "uploaded_pdf"},
    )
    _add(db_session, world, "month_close", actor=world.owner, new={"month": "2026-04"})
    await db_session.flush()
    after = await _feed(client, as_person, reader)
    assert after["new_count"] == 2
    new = [item["text"] for item in after["items"] if item["new"]]
    assert new[0].startswith("4 maanden afgesloten") or new[1].startswith("4 maanden")
    assert any(
        text.startswith("Offerte voor Opdracht Alfa 2026 is getekend") for text in new
    )
    # The signed quote says it all: the steps towards it are gone.
    assert not any("gemaakt en aangeboden" in text for text in _texts(after))
    # The marker is per person.
    assert (await _feed(client, as_person, world.lezer))["new_count"] == 0

    await as_person(reader).post("/api/updates/seen")
    again = await _feed(client, as_person, reader)
    assert again["new_count"] == 0 and not any(item["new"] for item in again["items"])


async def test_reading_the_feed_is_not_logged_as_a_read_of_sensitive_data(
    client, as_person, world, day, db_session
):
    async def reads() -> int:
        await db_session.flush()
        return len(
            (
                await db_session.scalars(
                    select(StreamEvent.seq).where(StreamEvent.type == "data.read")
                )
            ).all()
        )

    before = await reads()
    await _feed(client, as_person, world.member)
    await _feed(client, as_person, world.beheerder)
    assert await reads() == before


def test_time_is_said_as_people_say_it():
    now = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)
    assert news.when_text(datetime(2026, 10, 9, 7, 30, tzinfo=UTC), now) == "vanochtend"
    assert news.when_text(datetime(2026, 10, 9, 12, 30, tzinfo=UTC), now) == "vanmiddag"
    assert news.when_text(now - timedelta(days=1), now) == "gisteren"
    assert news.when_text(datetime(2026, 10, 2, 9, 0, tzinfo=UTC), now) == "2 oktober"
    assert news.day_label(now, now) == "Vandaag"
    assert news.day_label(now - timedelta(days=1), now) == "Gisteren"
    assert (
        news.day_label(datetime(2025, 12, 30, 9, 0, tzinfo=UTC), now)
        == "30 december 2025"
    )


def test_no_sentence_template_holds_a_code_name():
    for rule in news.NEWS:
        for template in (rule.one, rule.many, rule.anonymous or "", rule.you or ""):
            plain = template.replace("{object}", "x").replace("{person}", "x")
            plain = (
                plain.replace("{n}", "3").replace("{ref}", "").replace("{detail}", "x")
            )
            assert not words.CODE.search(plain) and "{" not in plain, template
