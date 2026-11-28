"""The feed narrowed to one assignment or to who did it, and what it offers.

A filter cuts the items the feed shows without it, and the options come from
those same items. Neither may tell a reader more than the feed does: no item
and no option about an assignment they cannot open, no person the feed does
not name as who did it, and an id they cannot see answers exactly as one that
does not exist.
"""

from __future__ import annotations

import uuid

import pytest

from grip.access import unclassified_fields
from grip.events import stream
from grip.models.stream_event import ACTOR_GUEST
from grip.schema import updates as schema

FEED = "/api/updates"
FILTERS = "/api/updates/filters"
NOTHING = {"items": [], "new_count": 0, "next": None}


def _add(db, kind, *, actor, on=None, person=None, new=None, action="create"):
    return stream.append(
        db,
        subject=(kind, on.id if kind == "assignment" else uuid.uuid4()),
        action=action,
        actor_person_id=actor.id if actor is not None else None,
        assignment_id=on.id if on is not None else None,
        person_id=person.id if person is not None else None,
        new=new or {},
    )


@pytest.fixture
async def news(db_session, world):
    """News on the assignment of the team, and on one the team cannot open.

    On Alfa the owner records a signed quote, closes two months and puts the
    member on the team once more; the planner takes the colleague off and
    closes a month too. On Beta, which only the beheerder made, the outsider
    starts it, closes a month and puts himself on it, and the client rejects
    a quote.
    """
    db = db_session
    alfa, beta = world.assignment, world.other_assignment
    alfa.status = "in_progress"
    _add(db, "quote_acceptance", actor=world.owner, on=alfa)
    for month in ("2026-01", "2026-02"):
        _add(db, "month_close", actor=world.owner, on=alfa, new={"month": month})
    _add(db, "allocation", actor=world.owner, on=alfa, person=world.member)
    _add(
        db,
        "allocation",
        actor=world.planner,
        on=alfa,
        person=world.colleague,
        action="delete",
    )
    _add(db, "month_close", actor=world.planner, on=alfa, new={"month": "2026-03"})
    _add(
        db,
        "assignment",
        actor=world.outsider,
        on=beta,
        action="update",
        new={"status": "in_progress"},
    )
    _add(db, "month_close", actor=world.outsider, on=beta, new={"month": "2026-03"})
    rejected = stream.append(
        db,
        "quote_rejection.created",
        subject=("quote_rejection", uuid.uuid4()),
        assignment_id=beta.id,
        new={},
    )
    rejected.actor_kind = ACTOR_GUEST
    _add(db, "allocation", actor=world.outsider, on=beta, person=world.outsider)
    await db.flush()
    assert rejected.actor_kind == ACTOR_GUEST


async def _feed(client, **params) -> dict:
    answer = await client.get(FEED, params={"limiet": 50, **params})
    assert answer.status_code == 200, answer.text
    return answer.json()


async def _everything(client, size=2, **params) -> list[dict]:
    """Every item, page by page."""
    items: list[dict] = []
    after = None
    for _ in range(50):
        body = await _feed(
            client, limiet=size, **params, **({"na": after} if after else {})
        )
        items += body["items"]
        after = body["next"]
        if after is None:
            return items
    raise AssertionError("the cursor does not end")


async def _options(client) -> dict:
    answer = await client.get(FILTERS)
    assert answer.status_code == 200, answer.text
    return answer.json()


def _texts(body: dict) -> list[str]:
    return [item["text"] for item in body["items"]]


def _names(options: list[dict]) -> list[str]:
    return [option["name"] for option in options]


async def test_the_feed_narrows_to_an_assignment_with_its_parts(as_person, world, news):
    client = as_person(world.beheerder)
    everything = await _feed(client)
    alfa = await _feed(client, opdracht=str(world.assignment.id))
    beta = await _feed(client, opdracht=str(world.other_assignment.id))
    # The quote, the months and the team are parts of the assignment.
    assert sorted(item["kind"] for item in alfa["items"]) == [
        "joined",
        "left",
        "month_closed",
        "quote_signed",
    ]
    assert all("Opdracht Alfa 2026" in text for text in _texts(alfa))
    assert sorted(item["kind"] for item in beta["items"]) == [
        "assignment_started",
        "joined",
        "month_closed",
        "quote_rejected",
    ]
    assert all("Opdracht Beta 2026" in text for text in _texts(beta))
    # Together they are the feed, in its order and in its words.
    ordered = sorted(alfa["items"] + beta["items"], key=lambda item: -item["seq"])
    assert ordered == everything["items"]


async def test_the_feed_narrows_to_who_the_sentence_says_did_it(as_person, world, news):
    client = as_person(world.beheerder)
    assert _texts(await _feed(client, persoon=str(world.owner.id))) == [
        "3 mensen ingezet op Opdracht Alfa 2026 door Eva Eigenaar"
    ]
    assert _texts(await _feed(client, persoon=str(world.planner.id))) == [
        "Cas Collega is van Opdracht Alfa 2026 af door Pim Planner"
    ]
    beta = str(world.other_assignment.id)
    by_outsider = await _feed(client, opdracht=beta, persoon=str(world.outsider.id))
    assert _texts(by_outsider) == [
        "Maart 2026 afgesloten op Opdracht Beta 2026 door Bo Buiten",
        "Opdracht Beta 2026 is gestart door Bo Buiten",
    ]
    assert by_outsider == await _feed(client, persoon=str(world.outsider.id))
    assert await _feed(client, opdracht=beta, persoon=str(world.owner.id)) == NOTHING

    # The owner made Alfa, but that news does not say who: it is nobody's.
    planner = as_person(world.planner)
    assert "Nieuwe potentiële opdracht: Opdracht Alfa 2026" in _texts(
        await _feed(planner)
    )
    assert _texts(await _feed(planner, persoon=str(world.owner.id))) == [
        "3 mensen ingezet op Opdracht Alfa 2026 door Eva Eigenaar"
    ]


async def test_an_item_that_does_not_say_who_did_it_is_nobodys(as_person, world, news):
    client = as_person(world.beheerder)
    texts = _texts(await _feed(client))
    nobodys = [
        # Done by several people.
        "3 maanden afgesloten op Opdracht Alfa 2026",
        # Done by the one it is about.
        "Bo Buiten is ingezet op Opdracht Beta 2026",
        # Done by the client, who is no person here.
        "Offerte voor Opdracht Beta 2026 is afgewezen",
    ]
    assert set(nobodys) <= set(texts)
    people = (world.owner, world.planner, world.outsider, world.member)
    for person in people:
        narrowed = _texts(await _feed(client, persoon=str(person.id)))
        assert not set(nobodys) & set(narrowed), person.name


async def test_who_only_recorded_a_decision_is_not_offered_as_who_made_it(
    as_person, world, news
):
    """A signed pdf is recorded by someone of this organisation; the client
    signed it. The sentence says that person recorded it, and the filter does
    not count it as theirs."""
    client = as_person(world.lezer)
    signed = next(
        item
        for item in (await _feed(client))["items"]
        if item["kind"] == "quote_signed"
    )
    assert signed["text"].endswith(" is getekend, vastgelegd door Eva Eigenaar")
    assert _names((await _options(client))["people"]) == ["Bo Buiten"]
    assert await _feed(client, persoon=str(world.owner.id)) == NOTHING


async def test_a_filtered_feed_pages_back_like_the_whole(as_person, world, news):
    client = as_person(world.beheerder)
    for params in (
        {"opdracht": str(world.assignment.id)},
        {"persoon": str(world.outsider.id)},
    ):
        paged = await _everything(client, size=1, **params)
        assert paged == (await _feed(client, **params))["items"]
        assert len({item["id"] for item in paged}) == len(paged) > 1


async def test_what_is_new_is_counted_in_what_the_filter_keeps(
    as_person, world, news, db_session
):
    alfa, beta = str(world.assignment.id), str(world.other_assignment.id)
    for reader in (world.beheerder, world.member):
        assert (await as_person(reader).post("/api/updates/seen")).status_code == 204
    _add(
        db_session,
        "month_close",
        actor=world.outsider,
        on=world.other_assignment,
        new={"month": "2026-04"},
    )
    _add(
        db_session,
        "allocation",
        actor=world.owner,
        on=world.assignment,
        person=world.member,
    )
    await db_session.flush()

    client = as_person(world.beheerder)
    assert (await _feed(client))["new_count"] == 2
    expected = {
        ("opdracht", alfa): 1,
        ("opdracht", beta): 1,
        ("persoon", str(world.owner.id)): 1,
        ("persoon", str(world.outsider.id)): 1,
        ("persoon", str(world.planner.id)): 0,
    }
    for (key, value), count in expected.items():
        body = await _feed(client, **{key: value})
        assert body["new_count"] == count, (key, value)
        assert sum(item["new"] for item in body["items"]) == count, (key, value)

    # What is new on an assignment the member cannot see stays as hidden as
    # one that does not exist.
    member = as_person(world.member)
    assert (await _feed(member))["new_count"] == 1
    assert await _feed(member, opdracht=beta) == NOTHING
    assert await _feed(member, opdracht=str(uuid.uuid4())) == NOTHING


async def test_the_options_are_what_the_feed_shows(as_person, world, news):
    client = as_person(world.beheerder)
    options = await _options(client)
    assert _names(options["assignments"]) == [
        "Opdracht Alfa 2026",
        "Opdracht Beta 2026",
    ]
    assert _names(options["people"]) == ["Bo Buiten", "Eva Eigenaar", "Pim Planner"]
    shown = await _feed(client)
    for option in options["assignments"]:
        assert any(
            (part.get("href") or "").startswith(f"/opdrachten/{option['id']}")
            for item in shown["items"]
            for part in item["parts"]
        )
    for option in options["people"]:
        assert any(text.endswith(f" door {option['name']}") for text in _texts(shown))

    member = await _options(as_person(world.member))
    assert _names(member["assignments"]) == ["Opdracht Alfa 2026"]
    assert _names(member["people"]) == ["Eva Eigenaar"]
    # Every item of the owner is about Alfa and says Pim did it: choosing
    # either would change nothing, so neither is offered.
    assert await _options(as_person(world.owner)) == {"assignments": [], "people": []}


async def test_no_item_and_no_option_about_an_assignment_the_reader_cannot_see(
    as_person, world, news
):
    beta = world.other_assignment
    for reader in (world.member, world.colleague, world.owner, world.outsider):
        client = as_person(reader)
        assert (await client.get(f"/api/assignments/{beta.id}")).status_code == 404
        options = await client.get(FILTERS)
        assert options.status_code == 200
        assert str(beta.id) not in options.text and beta.name not in options.text
        # Nor who did what happened on it.
        assert world.outsider.name not in options.text
        for item in await _everything(client):
            assert beta.name not in item["text"], (reader.name, item["text"])
            assert str(beta.id) not in str(item["parts"]), reader.name
        assert await _feed(client, opdracht=str(beta.id)) == NOTHING


async def test_an_id_the_reader_cannot_see_answers_as_one_that_does_not_exist(
    as_person, world, news
):
    unknown = str(uuid.uuid4())
    # The member cannot open Beta, and does not see what Bo and Pim did.
    hidden = (
        ("opdracht", world.other_assignment.id),
        ("persoon", world.outsider.id),
        ("persoon", world.planner.id),
    )
    for reader in (world.member, world.outsider):
        client = as_person(reader)
        for key, value in hidden:
            seen = await client.get(FEED, params={key: str(value)})
            not_there = await client.get(FEED, params={key: unknown})
            assert seen.status_code == not_there.status_code == 200
            assert seen.json() == not_there.json() == NOTHING, (reader.name, key)
        both = await client.get(
            FEED,
            params={
                "opdracht": str(world.other_assignment.id),
                "persoon": str(world.outsider.id),
            },
        )
        assert both.status_code == 200 and both.json() == NOTHING
    # An assignment the team may open, and the outsider may not.
    outsider = as_person(world.outsider)
    alfa = await outsider.get(FEED, params={"opdracht": str(world.assignment.id)})
    assert alfa.status_code == 200 and alfa.json() == NOTHING
    # What is no id at all is refused before anything is looked up.
    assert (await outsider.get(FEED, params={"opdracht": "x"})).status_code == 422


async def test_an_assignment_named_in_news_about_you_but_closed_to_you_is_no_choice(
    as_person, world, news, db_session
):
    """News about the reader can name an assignment they cannot open. The
    name is theirs to know; its id is not, so it is not offered, and
    filtering on it finds nothing."""
    alfa = world.assignment
    _add(db_session, "allocation", actor=world.owner, on=alfa, person=world.outsider)
    stream.append(
        db_session,
        subject=("person_scale", uuid.uuid4()),
        action="update",
        actor_person_id=world.beheerder.id,
        person_id=world.outsider.id,
        new={"billing_scale": 12},
    )
    await db_session.flush()
    client = as_person(world.outsider)
    assert (await client.get(f"/api/assignments/{alfa.id}")).status_code == 404
    assert _texts(await _feed(client)) == [
        "Je hebt een nieuwe schaal",
        "Je bent ingezet op Opdracht Alfa 2026 door Eva Eigenaar",
    ]
    options = await client.get(FILTERS)
    assert str(alfa.id) not in options.text and alfa.name not in options.text
    assert await _feed(client, opdracht=str(alfa.id)) == NOTHING


async def test_a_person_filter_never_shows_what_the_reader_could_not_see(
    as_person, world, news
):
    people = (
        world.beheerder,
        world.lezer,
        world.planner,
        world.owner,
        world.member,
        world.colleague,
        world.outsider,
    )
    narrowed = 0
    for reader in people:
        client = as_person(reader)
        whole = {item["id"]: item for item in await _everything(client)}
        offered = {option["id"] for option in (await _options(client))["people"]}
        for actor in people:
            items = await _everything(client, persoon=str(actor.id))
            for item in items:
                # The very item the feed shows, in its words, saying who.
                assert whole.get(item["id"]) == item, (reader.name, actor.name)
                assert item["text"].endswith(f" door {actor.name}"), item["text"]
            if str(actor.id) not in offered:
                # No sentence names them, or every sentence does.
                assert items in ([], list(whole.values())), (reader.name, actor.name)
            narrowed += len(items)
    assert narrowed > 5


@pytest.mark.parametrize(
    "model",
    [
        schema.UpdatePartOut,
        schema.UpdateItemOut,
        schema.UpdateFeedOut,
        schema.UpdateOptionOut,
        schema.UpdatePersonOut,
        schema.UpdateFiltersOut,
    ],
    ids=lambda model: model.__name__,
)
def test_every_field_has_one_data_class(model):
    assert unclassified_fields(model) == []
