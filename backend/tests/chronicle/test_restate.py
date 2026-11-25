"""Taking a typed text out of a chronicle: the pure part (ADR 0057).

No database, no clock. All names and texts are fictional.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect as sa_inspect

from grip.chronicle import words
from grip.chronicle.facts import ASSIGNMENT, FACTS, LINE, ROW_ONLY_COLUMNS
from grip.chronicle.ledger import Gram, fold
from grip.chronicle.restate import (
    PLACEHOLDER,
    RESTATED,
    TYPED_TEXTS,
    contains,
    plan,
    removable,
    substituted,
    without,
)
from grip.chronicle.writer import MODELS, changes_of, columns_of, row_of
from grip.models.assignment import Assignment, BudgetLine

NOW = datetime(2026, 11, 3, 14, 2, tzinfo=UTC)
TEXT = "Afwezig wegens een operatie aan de knie"


def _gram(seq: int, fact: str, fields: dict[str, Any] | None, **meta: Any) -> Gram:
    return Gram(seq=seq, fact=fact, occurred_at=NOW, fields=fields, **meta)


def _created(aid, **values: Any) -> dict[str, Any]:
    return {
        "assignment": row_of(
            Assignment,
            **{
                "id": aid,
                "uri": f"https://voorbeeld.example/id/opdracht/{aid}",
                "name": "Voorbeeldopdracht",
                "kind": "external",
                "status": "draft",
                "context_refs": [],
                **values,
            },
        ),
        "owner_role": None,
    }


def _line(aid, **values: Any) -> dict[str, Any]:
    return {
        "line": row_of(
            BudgetLine,
            id=uuid4(),
            assignment_id=aid,
            kind="personnel",
            position=1,
            role="Productmanager",
            role_id=uuid4(),
            fte=Decimal("0.5"),
            rate_category="D",
            period_source="own",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            **values,
        )
    }


def _restated(grams: list[Gram], texts: list[str]) -> list[Gram]:
    """The chronicle as the stream holds it after the act: the holders erased
    and a herstelfeit for each at the end."""
    planned = plan(grams, texts, assignment_id="a")
    held = {holder.seq for holder, _fields in planned}
    after = [replace(gram, fields=None) if gram.seq in held else gram for gram in grams]
    seq = max(gram.seq for gram in grams)
    for offset, (_holder, fields) in enumerate(planned, start=1):
        after.append(_gram(seq + offset, RESTATED, fields))
    return after


def test_every_typed_text_is_a_text_column_that_stays_in_a_fact():
    for text in TYPED_TEXTS:
        if text.table is None:
            continue
        model = MODELS[text.table]
        assert text.column in columns_of(model), text.key
        assert text.column not in ROW_ONLY_COLUMNS.get(text.table, ()), text.key
        column = sa_inspect(model).column_attrs[text.column].columns[0]
        assert text.required is (not column.nullable), text.key
    keys = {text.key for text in TYPED_TEXTS}
    assert {
        "assignment.name",
        "assignment.notes",
        "assignment.verbal_agreement_note",
        "budget_line.detail",
    } <= keys


def test_a_herstelfeit_takes_the_place_of_what_it_restates():
    aid = str(uuid4())
    born = _gram(1, "assignment_created", _created(aid, notes=TEXT), kind="general")
    line = _gram(2, "budget_line_added", _line(aid))
    recorded = _restated([born, line], [TEXT])
    assert [gram.fact for gram in recorded] == [
        "assignment_created",
        "budget_line_added",
        RESTATED,
    ]
    assert recorded[0].erased

    read = substituted(recorded)
    assert read[0].fields is not None
    assert read[0].restated_by == (3,)
    assert read[0].kind == "general"
    assert read[0].fields["assignment"]["notes"] is None
    assert read[0].fields["assignment"]["name"] == "Voorbeeldopdracht"
    ledger = fold(read)
    assert ledger.erased == [], "a restated fact leaves no stand incomplete"
    assert ledger.table(ASSIGNMENT)[aid]["notes"] is None
    assert TEXT not in repr(read)


def test_a_stand_before_the_herstelfeit_is_whole_too():
    aid = str(uuid4())
    born = _gram(1, "assignment_created", _created(aid, notes=TEXT))
    line = _gram(2, "budget_line_added", _line(aid))
    recorded = _restated([born, line], [TEXT])
    cut = [gram for gram in recorded if gram.seq <= 1]
    alone = fold(substituted(cut))
    assert alone.erased == [1], "without what restated it, the fact is gone"
    whole = fold(substituted(cut, [gram for gram in recorded if gram.fact == RESTATED]))
    assert whole.erased == []
    assert whole.table(ASSIGNMENT)[aid]["notes"] is None


def test_the_herstelfeit_folds_as_its_patches_and_changes_nothing_more():
    aid = str(uuid4())
    born = _gram(1, "assignment_created", _created(aid, notes=TEXT))
    recorded = _restated([born], [TEXT])
    herstel = recorded[-1]
    assert herstel.fields is not None
    assert herstel.fields["patches"] == [
        {"table": ASSIGNMENT, "id": aid, "values": {"notes": None}}
    ]
    read = substituted(recorded)
    assert fold(read, upto=1).rows == fold(read).rows


def test_an_erased_fact_that_nothing_restated_stays_erased():
    aid = str(uuid4())
    born = _gram(1, "assignment_created", _created(aid))
    erased = _gram(2, "assignment_changed", None)
    assert fold(substituted([born, erased])).erased == [2]


def test_no_patch_where_a_later_fact_changed_the_column():
    aid = str(uuid4())
    born = _gram(1, "assignment_created", _created(aid, notes=TEXT))
    changed = _gram(
        2,
        "assignment_changed",
        {
            "assignment_id": aid,
            "changes": changes_of(Assignment, notes="Iets anders"),
            "moved_lines": {},
        },
    )
    planned = plan([born, changed], [TEXT], assignment_id=aid)
    assert [holder.seq for holder, _fields in planned] == [1]
    assert planned[0][1]["patches"] == []
    read = substituted(_restated([born, changed], [TEXT]))
    assert fold(read).table(ASSIGNMENT)[aid]["notes"] == "Iets anders"
    assert fold(read, upto=1).table(ASSIGNMENT)[aid]["notes"] is None


def test_a_column_that_may_not_be_empty_keeps_the_placeholder():
    aid = str(uuid4())
    fields = _created(aid, name=TEXT, notes=f"Over {TEXT}, verder niets")
    kept, removed = without("assignment_created", fields, [TEXT])
    assert kept["assignment"]["name"] == PLACEHOLDER
    assert kept["assignment"]["notes"] == f"Over {PLACEHOLDER}, verder niets"
    assert removed == [
        {"path": "assignment.name", "label": "Naam"},
        {"path": "assignment.notes", "label": "Notities"},
    ]
    assert fields["assignment"]["name"] == TEXT, "the fields given stay as they are"
    line, _ = without("budget_line_added", _line(aid, detail=TEXT), [TEXT])
    assert line["line"]["detail"] == PLACEHOLDER


def test_a_verbal_agreement_offers_its_note_once_and_loses_it_twice():
    aid = str(uuid4())
    fields = {
        "assignment_id": aid,
        "from": "quoted",
        "to": "verbally_agreed",
        "reason": TEXT,
        "verbal_agreement_note": TEXT,
        "verbal_agreement_at": "2026-11-03T13:02:00.000000+00:00",
    }
    offered = removable("assignment_status_changed", fields)
    assert [(text.key, value) for text, value in offered] == [
        ("assignment.verbal_agreement_note", TEXT)
    ]
    kept, _ = without("assignment_status_changed", fields, [TEXT])
    assert kept["reason"] is None
    assert kept["verbal_agreement_note"] is None
    assert words.lines("assignment_status_changed", kept) == ()


def test_a_reason_alone_can_go():
    fields = {
        "assignment_id": "a",
        "from": "requested",
        "to": "cancelled",
        "reason": TEXT,
    }
    offered = removable("assignment_status_changed", fields)
    assert [(text.key, text.label) for text, _ in offered] == [("reason", "Reden")]


def test_the_reason_of_a_reopened_dossier_can_go():
    fields = {"assignment_id": "a", "reason": TEXT}
    offered = removable("dossier_reopened", fields)
    assert [(text.key, text.label, value) for text, value in offered] == [
        ("reason", "Reden", TEXT)
    ]
    assert words.lines("dossier_reopened", fields) == (TEXT,)
    kept, removed = without("dossier_reopened", fields, [TEXT])
    assert kept == {"assignment_id": "a", "reason": None}
    assert removed == [{"path": "reason", "label": "Reden"}]
    assert words.lines("dossier_reopened", kept) == ()
    # Reopened before a reopen asked for a reason: nothing to show or take out.
    older = {"assignment_id": "a"}
    assert removable("dossier_reopened", older) == []
    assert words.lines("dossier_reopened", older) == ()


def test_the_name_of_a_line_loses_its_detail_too():
    aid = str(uuid4())
    added = _gram(1, "budget_line_added", _line(aid, detail=TEXT))
    line_id = added.fields["line"]["id"]  # type: ignore[index]
    removed = _gram(
        2,
        "budget_line_removed",
        {"line_id": line_id, "name": f"Productmanager: {TEXT}"},
    )
    planned = plan([added, removed], [TEXT], assignment_id=aid)
    assert [holder.seq for holder, _fields in planned] == [1, 2]
    assert planned[1][1]["fields"]["name"] == f"Productmanager: {PLACEHOLDER}"
    assert planned[1][1]["removed"] == [{"path": "name", "label": "Omschrijving"}]
    # The line is gone: no row to patch.
    assert all(fields["patches"] == [] for _holder, fields in planned)
    assert removable("budget_line_removed", removed.fields) == []


def test_a_short_text_goes_only_where_it_is_the_whole_value():
    aid = str(uuid4())
    short = _gram(1, "assignment_created", _created(aid, notes="Ja"))
    longer = _gram(
        2,
        "assignment_changed",
        {"assignment_id": aid, "changes": {"notes": "Jaarplan, ja"}},
    )
    planned = plan([short, longer], ["Ja"], assignment_id=aid)
    assert [holder.seq for holder, _fields in planned] == [1]
    assert planned[0][1]["fields"]["assignment"]["notes"] is None
    assert contains({"note": "Ja"}, ["Ja"])
    assert not contains({"note": "Jaarplan"}, ["Ja"])


def test_a_long_text_goes_as_a_whole_phrase_inside_another_value():
    kept, _ = without(
        "assignment_status_changed",
        {"assignment_id": "a", "reason": f"Gemeld: {TEXT}. Verder niets."},
        [TEXT],
    )
    assert kept["reason"] == f"Gemeld: {PLACEHOLDER}. Verder niets."
    # Not inside a longer word.
    assert not contains("Opdracht Voorbeeldtrajectje", ["Voorbeeldtraject"])
    assert contains("Opdracht Voorbeeldtraject gestart", ["Voorbeeldtraject"])


def test_a_moment_offers_no_placeholder_and_no_empty_text():
    aid = str(uuid4())
    fields = _created(aid, name=PLACEHOLDER, notes="  ")
    assert removable("assignment_created", fields) == []
    assert removable(RESTATED, {"fact": "assignment_created", "fields": fields}) == []


def test_a_herstelfeit_restated_in_turn_still_stands():
    aid = str(uuid4())
    born = _gram(1, "assignment_created", _created(aid, name=TEXT, notes="Iets"))
    first = _restated([born], ["Iets"])
    assert first[-1].seq == 2
    # Taking the name out of the same moment again restates the herstelfeit.
    second = _restated(first, [TEXT])
    assert [(gram.seq, gram.erased) for gram in second] == [
        (1, True),
        (2, True),
        (3, False),
    ]
    read = substituted(second)
    assert read[0].restated_by == (2, 3)
    assert read[0].fields is not None
    assert read[0].fields["assignment"]["name"] == PLACEHOLDER
    assert read[0].fields["assignment"]["notes"] is None
    assert read[1].restated_by == (3,)
    assert read[1].fields is not None and read[1].fields["restates"] == 1
    ledger = fold(read)
    assert ledger.erased == []
    assert ledger.table(ASSIGNMENT)[aid]["name"] == PLACEHOLDER
    assert TEXT not in repr(read)
    assert second[-1].fields is not None
    assert second[-1].fields["patches"] == [
        {"table": ASSIGNMENT, "id": aid, "values": {"name": PLACEHOLDER}}
    ]


def test_a_chronicle_that_starts_later_still_patches_its_rows():
    aid = str(uuid4())
    changed = _gram(
        1,
        "assignment_changed",
        {
            "assignment_id": aid,
            "changes": changes_of(Assignment, notes=TEXT),
            "moved_lines": {},
        },
    )
    planned = plan([changed], [TEXT], assignment_id=aid)
    assert planned[0][1]["patches"] == [
        {"table": ASSIGNMENT, "id": aid, "values": {"notes": None}}
    ]


def test_the_herstelfeit_says_what_went_and_from_which_moment():
    aid = str(uuid4())
    born = _gram(
        1, "assignment_created", _created(aid, notes=TEXT), recorded_on="2026-11-03"
    )
    herstel = _restated([born], [TEXT])[-1]
    assert FACTS[RESTATED].title == "Tekst verwijderd"
    assert (
        words.statement(RESTATED, herstel.fields, actor=None)
        == "Notities verwijderd uit het moment Opdracht toegevoegd van 3 november 2026."
    )
    assert TEXT not in repr(herstel.fields)
    assert herstel.fields is not None
    assert herstel.fields["restates"] == 1
    assert herstel.fields["fact"] == "assignment_created"
    assert herstel.fields["recorded_on"] == "2026-11-03"


def test_a_line_detail_in_the_words_of_a_restated_moment():
    aid = str(uuid4())
    added = _gram(1, "budget_line_added", _line(aid, detail=TEXT))
    read = substituted(_restated([added], [TEXT]))
    assert (
        words.statement("budget_line_added", read[0].fields, actor=None)
        == f"Begrotingsregel Productmanager: {PLACEHOLDER} toegevoegd."
    )
    line = next(iter(fold(read).table(LINE).values()))
    assert line["detail"] == PLACEHOLDER
