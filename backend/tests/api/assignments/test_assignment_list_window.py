"""The list of assignments in pages: the window never shows or counts more
than the reader may see."""

from datetime import date

import pytest

from grip.services import assignments


@pytest.fixture
async def more(world, db_session):
    """Five more assignments nobody but a reader of all is involved in."""
    made = []
    for letter in ("Gamma", "Delta", "Epsilon", "Zeta", "Eta"):
        made.append(
            await assignments.create_assignment(
                db_session,
                name=f"Opdracht {letter} 2026",
                actor=world.beheerder,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
            )
        )
    return made


async def test_a_page_is_a_window_on_the_whole_list(world, more, as_person):
    client = as_person(world.beheerder)
    whole = (await client.get("/api/assignments")).json()
    names = [i["name"] for i in whole["items"]]
    assert len(names) == 7
    assert whole["total"] == 7
    # Every new assignment starts as a potential one.
    assert whole["counts"] == {"potential": 7, "active": 0, "closed": 0}

    first = (
        await client.get("/api/assignments", params={"page": 1, "page_size": 3})
    ).json()
    last = (
        await client.get("/api/assignments", params={"page": 3, "page_size": 3})
    ).json()
    assert [i["name"] for i in first["items"]] == names[:3]
    assert [i["name"] for i in last["items"]] == names[6:]
    assert first["total"] == last["total"] == 7
    assert (last["page"], last["page_size"]) == (3, 3)
    # A page past the end is empty, not an error, and still says the total.
    beyond = (
        await client.get("/api/assignments", params={"page": 9, "page_size": 3})
    ).json()
    assert beyond["items"] == [] and beyond["total"] == 7


async def test_phase_and_search_narrow_the_list_on_the_server(world, more, as_person):
    client = as_person(world.beheerder)
    moved = await client.post(
        f"/api/assignments/{more[0].id}/transition",
        json={"target": "cancelled", "reason": "Gaat niet door"},
    )
    assert moved.status_code == 200, moved.text
    closed = (await client.get("/api/assignments", params={"phase": "closed"})).json()
    assert [i["name"] for i in closed["items"]] == ["Opdracht Gamma 2026"]
    assert closed["total"] == 1
    assert closed["counts"] == {"potential": 6, "active": 0, "closed": 1}

    # By the name of the assignment or of its client, without regard to case.
    found = (await client.get("/api/assignments", params={"q": "zeta"})).json()
    assert [i["name"] for i in found["items"]] == ["Opdracht Zeta 2026"]
    by_client = (
        await client.get("/api/assignments", params={"q": "voorbeeldminis"})
    ).json()
    assert [i["name"] for i in by_client["items"]] == ["Opdracht Alfa 2026"]
    # The counts on the tabs follow the search.
    assert by_client["counts"] == {"potential": 1, "active": 0, "closed": 0}
    # What the reader types is text, not a pattern.
    assert (await client.get("/api/assignments", params={"q": "%"})).json()[
        "total"
    ] == 0
    assert (await client.get("/api/assignments", params={"q": "_"})).json()[
        "total"
    ] == 0


async def test_counts_and_windows_hold_only_what_the_reader_may_see(
    world, more, as_person
):
    """A team member is on one assignment of seven."""
    client = as_person(world.member)
    whole = (await client.get("/api/assignments")).json()
    assert [i["name"] for i in whole["items"]] == ["Opdracht Alfa 2026"]
    assert whole["total"] == 1
    assert whole["counts"] == {"potential": 1, "active": 0, "closed": 0}

    # No page reaches past the own assignment, however it is cut.
    seen = set()
    for page in range(1, 8):
        body = (
            await client.get("/api/assignments", params={"page": page, "page_size": 1})
        ).json()
        assert body["total"] == 1
        seen.update(i["name"] for i in body["items"])
    assert seen == {"Opdracht Alfa 2026"}

    # Searching for an assignment that exists but is not theirs finds nothing
    # and counts nothing: the search cannot be used to learn that it exists.
    for words in ("Zeta", "Opdracht", "Beta"):
        body = (await client.get("/api/assignments", params={"q": words})).json()
        assert {i["name"] for i in body["items"]} <= {"Opdracht Alfa 2026"}
        assert body["total"] == len(body["items"])
        assert sum(body["counts"].values()) == len(body["items"])
    # Money stays out of a windowed answer too.
    assert "quoted_amount_cents" not in whole["items"][0]


async def test_someone_without_any_assignment_counts_nothing(world, more, as_person):
    body = (
        await as_person(world.outsider).get(
            "/api/assignments", params={"page": 1, "q": "Opdracht"}
        )
    ).json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["counts"] == {"potential": 0, "active": 0, "closed": 0}


async def test_the_window_has_bounds(world, as_person):
    client = as_person(world.beheerder)
    assert (await client.get("/api/assignments", params={"page": 0})).status_code == 422
    assert (
        await client.get("/api/assignments", params={"page_size": 100000})
    ).status_code == 422
    assert (
        await client.get("/api/assignments", params={"phase": "alles"})
    ).status_code == 422
