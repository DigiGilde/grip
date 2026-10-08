"""Events in words: Dutch on the server, and changes apart from reads."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from grip.events import stream, words
from grip.events.classification import SPECS
from grip.services import events as domain_events


@dataclass
class _Seen:
    field: str
    visible: bool = True
    old: Any = None
    new: Any = None


def _has_code(text: str) -> bool:
    return words.CODE.search(text) is not None


# -- the words ------------------------------------------------------------------


def test_a_reader_who_may_see_values_gets_from_what_to_what():
    changes = [
        _Seen("billing_scale", old=11, new=12),
        _Seen("valid_from", new="2026-07-01"),
    ]
    assert words.title("person_scale.updated", "person_scale", "Lot Lid") == (
        "Schaal van Lot Lid gewijzigd"
    )
    assert words.lines("person_scale.updated", "person_scale", changes) == [
        "Schaal van 11 naar 12 per 1 juli 2026"
    ]
    hidden = [_Seen("billing_scale", visible=False), _Seen("valid_from", visible=False)]
    assert words.lines("person_scale.updated", "person_scale", hidden) == []


def test_code_values_get_their_dutch_label():
    assert words.lines(
        "assignment.updated",
        "assignment",
        [_Seen("status", old="verbally_agreed", new="in_progress")],
    ) == ["Status van Mondeling akkoord naar In uitvoering"]
    assert words.lines(
        "vacancy_text.created",
        "vacancy_text",
        [_Seen("source", new="standard_text"), _Seen("reason", new="standard_text")],
    ) == ["Herkomst Standaardtekst", "Reden Standaardtekst gebruikt"]
    assert words.lines(
        "assignment.status_changed",
        "assignment",
        [],
        payload={"new_status": "in_progress", "reason": "na overleg met de klant"},
    ) == ["Status In uitvoering", "Reden na overleg met de klant"]
    assert words.lines(
        "budget_line.updated",
        "budget_line",
        [_Seen("amount_cents", old=1000000, new=1250050)],
    ) == ["Bedrag van € 10.000 naar € 12.500,50"]


def test_a_code_without_a_label_is_not_shown():
    lines = words.lines(
        "quote.updated",
        "quote",
        [
            _Seen("status", old="issued", new="some_new_state"),
            _Seen("reason", new="not_yet_translated"),
            # A field without a Dutch name is left out altogether.
            _Seen("document_sha256", new="abc"),
            _Seen("internal_flag", new="x_y"),
        ],
        note="see_also other_thing",
    )
    assert lines == ["Status Gemaakt vervalt", "Reden gewijzigd"]


def test_a_read_says_what_was_read_and_of_how_many():
    one = [_Seen("classes", new=["person_rate"])]
    assert (
        words.title("data.read", "person", "Lot Lid") == "Gegevens van Lot Lid ingezien"
    )
    assert words.lines("data.read", "person", one) == ["Schaal en tarief"]
    many = [
        _Seen("classes", new=["person_cost", "person_rate"]),
        _Seen("persons", new=40),
    ]
    assert words.title("data.read", "data", None) == "Gegevens ingezien"
    assert words.lines("data.read", "data", many) == [
        "Kostentarief en marge en schaal en tarief van 40 personen"
    ]


def test_no_rendered_line_contains_a_code_name():
    """Every kind and type, every labelled field with every known code value
    and with one nobody labelled: nothing with an underscore comes out."""
    codes = {value for labels in words.VALUE_LABELS.values() for value in labels}
    codes |= {"brand_new_code", "x_1", "retention_after_withdrawn_hire"}
    types = [
        *(
            f"{kind}.{verb}"
            for kind in SPECS
            for verb in ("created", "updated", "deleted")
        ),
        *domain_events.EVENT_TYPES,
        "data.read",
        "stream.erased",
    ]
    fields = [*words.FIELD_LABELS, "unknown_field", "person_id", "classes", "persons"]
    checked = 0
    for event_type in types:
        kind = event_type.partition(".")[0]
        for person in (None, "Lot Lid"):
            assert not _has_code(words.title(event_type, kind, person)), event_type
        for code in sorted(codes):
            changes = [_Seen(name, old=code, new="other_code") for name in fields]
            changes += [_Seen(name, new=code) for name in fields]
            rendered = words.lines(
                event_type,
                kind,
                changes,
                payload={"new_status": code, "reason": code},
                note=code,
            )
            for line in rendered:
                assert not _has_code(line), (event_type, code, line)
                checked += 1
    assert checked > 1000
    # Every kind that can be the subject of an event has a Dutch name.
    assert set(SPECS) <= set(words.KIND_LABELS)
    assert not any(_has_code(label) for label in words.KIND_LABELS.values())


async def test_what_the_api_gives_of_real_events_has_no_code_names(
    client, as_person, world, db_session
):
    from grip.services import assignments

    await assignments.update_assignment(
        db_session, world.assignment.id, actor=world.owner, name="Opdracht Alfa II"
    )
    stream.append(
        db_session,
        subject=("vacancy_text", uuid.uuid4()),
        action="create",
        assignment_id=world.assignment.id,
        new={"kind": "vacancy", "source": "standard_text", "reason": "standard_text"},
    )
    await db_session.flush()
    seen, before = [], None
    while True:
        params = {"limit": 200, "kind": "all", **({"before": before} if before else {})}
        body = (
            await as_person(world.beheerder).get("/api/events", params=params)
        ).json()
        seen += body["items"]
        before = body["next_before"]
        if before is None:
            break
    assert len(seen) > 10
    for item in seen:
        assert item["title"] and not _has_code(item["title"]), item["type"]
        for line in item["lines"]:
            assert not _has_code(line), (item["type"], line)
    text = next(item for item in seen if item["type"] == "vacancy_text.created")
    assert text["title"] == "Vacaturetekst toegevoegd"
    assert text["lines"] == [
        "Soort Vacaturetekst",
        "Herkomst Standaardtekst",
        "Reden Standaardtekst gebruikt",
    ]
    assert {c["field"]: c["label"] for c in text["changes"]} == {
        "kind": "Soort",
        "source": "Herkomst",
        "reason": "Reden",
    }


# -- changes apart from reads ----------------------------------------------------


async def test_changes_are_found_among_a_hundred_times_as_many_reads(
    client, as_person, world, db_session
):
    marker = f"k{uuid.uuid4().hex[:8]}"
    changes = []
    for index in range(4):
        for _ in range(100):
            stream.append(
                db_session,
                "data.read",
                subject=("person", world.member.id),
                person_id=world.member.id,
                new={"classes": ["person_rate"]},
                existence_class="person_rate",
                field_classes={"*": "person_rate"},
            )
        changes.append(
            stream.append(
                db_session,
                subject=("rate_card", f"{marker}-{index}"),
                action="update",
                new={"status": "active"},
            )
        )
    for _ in range(300):
        stream.append(
            db_session,
            "data.read",
            subject=("person", world.member.id),
            person_id=world.member.id,
            new={"classes": ["person_rate"]},
            existence_class="person_rate",
            field_classes={"*": "person_rate"},
        )
    await db_session.flush()
    reader = as_person(world.beheerder)

    # The default is changes: a small page holds all four, newest first,
    # although seven hundred reads lie on top of and between them.
    default = (await reader.get("/api/events", params={"limit": 10})).json()["items"]
    assert all(item["type"] != "data.read" for item in default)
    ours = [
        item["seq"] for item in default if (item["subject_id"] or "").startswith(marker)
    ]
    assert ours == [event.seq for event in reversed(changes)]
    explicit = (
        await reader.get("/api/events", params={"limit": 10, "kind": "changes"})
    ).json()["items"]
    assert [item["seq"] for item in explicit] == [item["seq"] for item in default]

    # Paging through changes never lands on a read.
    paged, before = [], None
    for _ in range(4):
        params = {"limit": 1, "subject_kind": "rate_card"}
        body = (
            await reader.get(
                "/api/events",
                params={**params, **({"before": before} if before else {})},
            )
        ).json()
        paged += [item["seq"] for item in body["items"]]
        before = body["next_before"]
    assert paged == [event.seq for event in reversed(changes)]

    # Reads are a choice, and then there is nothing else.
    reads = (
        await reader.get("/api/events", params={"limit": 200, "kind": "reads"})
    ).json()
    assert len(reads["items"]) == 200 and reads["next_before"] is not None
    assert {item["type"] for item in reads["items"]} == {"data.read"}
    assert reads["items"][0]["title"] == "Gegevens van Lot Lid ingezien"

    everything = (
        await reader.get("/api/events", params={"limit": 200, "kind": "all"})
    ).json()
    kinds = {item["type"] for item in everything["items"]}
    assert "data.read" in kinds
    assert (await reader.get("/api/events", params={"kind": "iets"})).status_code == 422


def test_a_right_is_named_with_what_happened_to_it():
    granted = [_Seen("function", new="lezer"), _Seen("person_id", new="x")]
    assert words.title(
        "person_role.created", "person_role", "Lot Lid", changes=granted
    ) == ("Recht lezer aan Lot Lid toegekend")
    revoked = [_Seen("function", old="lezer"), _Seen("ended", new="2026-03-01")]
    assert words.title(
        "person_role.updated", "person_role", "Lot Lid", changes=revoked
    ) == ("Recht lezer van Lot Lid ingetrokken")
    # A reader who may not see which right still reads what happened.
    hidden = [_Seen("function", visible=False), _Seen("ended", new="2026-03-01")]
    assert words.title("person_role.updated", "person_role", None, changes=hidden) == (
        "Recht in grip ingetrokken"
    )


def test_a_role_on_an_assignment_names_the_role_and_the_assignment():
    role = [_Seen("role", new="manager"), _Seen("assignment_id", new="x")]
    assert (
        words.title(
            "assignment_role.created",
            "assignment_role",
            "Lot Lid",
            changes=role,
            case_name="Opdracht Alfa",
        )
        == "Lot Lid is manager van Opdracht Alfa"
    )
    gone = [_Seen("role", old="manager")]
    assert (
        words.title(
            "assignment_role.deleted", "assignment_role", "Lot Lid", changes=gone
        )
        == "Lot Lid is geen manager meer van de opdracht"
    )
    assert (
        words.title("assignment_role.created", "assignment_role", None, changes=role)
        == "Rol op de opdracht toegevoegd"
    )
