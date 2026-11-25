"""The pure core of the chronicle: no database, no clock."""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import LargeBinary, String
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB

from grip.chronicle.effects import Drop, Flush, Insert, Patch, plain
from grip.chronicle.facts import (
    DECRETOGRAM,
    EXECUTOGRAM,
    FACTS,
    READ_MODELS,
    ROW_ONLY_COLUMNS,
    as_recorded,
    effects_of,
    title_of,
)
from grip.chronicle.ledger import Gram, diff, fold, is_born
from grip.chronicle.writer import (
    MODELS,
    changes_of,
    check_effect,
    columns_of,
    default_of,
    normal,
    row_of,
    typed,
)
from grip.models.assignment import Assignment, AssignmentRole, BudgetLine
from grip.models.quote import Quote, QuoteAcceptance
from grip.services.chronicle import _row

NOW = datetime(2026, 11, 3, 14, 2, 3, 456789, tzinfo=UTC)

# Stored facts keep their name for good. Add a new name here; taking one out or
# renaming it drops every old row of that fact from the fold, without a word.
FACT_NAMES = frozenset(
    {
        "acceptance_date_corrected",
        "approval_approved",
        "approval_requested",
        "approval_sent_back",
        "approval_withdrawn",
        "assignment_changed",
        "assignment_created",
        "assignment_request_received",
        "assignment_requested",
        "assignment_role_removed",
        "assignment_role_set",
        "assignment_shared",
        "assignment_status_changed",
        "budget_line_added",
        "budget_line_changed",
        "budget_line_removed",
        "budget_lines_role_merged",
        "chronicle_rebuilt",
        "dossier_closed",
        "dossier_kept_open",
        "dossier_reopened",
        "invitation_opened",
        "invitation_renewed",
        "invitation_withdrawn",
        "quote_accepted",
        "quote_document_fixed",
        "quote_issued",
        "quote_offered",
        "quote_received",
        "quote_rejected",
        "rates_established",
    }
)


def _gram(seq: int, fact: str, fields: dict | None) -> Gram:
    return Gram(seq=seq, fact=fact, occurred_at=NOW, fields=fields)


def _assignment(**values) -> dict:
    return row_of(
        Assignment,
        id=uuid4(),
        uri="https://voorbeeld.example/id/opdracht/1",
        name="Voorbeeldopdracht",
        kind="external",
        status="draft",
        context_refs=[],
        **values,
    )


def _line(assignment_id, **values) -> dict:
    return row_of(
        BudgetLine,
        id=uuid4(),
        assignment_id=assignment_id,
        kind="personnel",
        detail="",
        position=1,
        role="Voorbeeldrol",
        role_id=uuid4(),
        fte=Decimal("0.800"),
        rate_category="B",
        period_source="own",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        **values,
    )


def test_every_read_model_has_a_model():
    assert set(READ_MODELS) == set(MODELS)


# A column of a read model that can hold what someone typed or who someone is
# either lives in its row only (ROW_ONLY_COLUMNS), or stays in a fact for the
# reason given here. A new such column fails until it has chosen.
STAYS_IN_A_FACT = {
    "assignment.uri": "an address of the case",
    "assignment.name": "changes; a stand shows it as it was",
    "assignment.kind": "a code",
    "assignment.shared_with_instance_uri": "an address of an instance",
    "assignment.status": "a code",
    "assignment.parent_assignment_uri": "an address of a case",
    "assignment.context_refs": "addresses of policy",
    "assignment.notes": "changes; a stand shows it as it was",
    "assignment.verbal_agreement_note": "a stand shows it; asks for no name",
    "assignment_role.role": "a code",
    "budget_line.description": "changes; decides whether a quote is outdated",
    "budget_line.kind": "a code",
    "budget_line.role": "a name from the catalogue",
    "budget_line.rate_category": "a code",
    "budget_line.period_source": "a code",
    "quote.uri": "an address of the quote",
    "quote.reference": "a number",
    "quote.status": "a code",
    "quote.snapshot_hash": "a hash",
    "quote.document_sha256": "a hash",
    "quote.document_ref": "a reference to a stored document",
    "quote.document_origin": "a code",
    "quote.prose_provenance": "how sections were drafted, no person",
    "quote_offer.channel": "a code",
    "quote_approval.quote_hash": "a hash",
    "quote_approval.status": "a code",
    "quote_acceptance.quote_hash": "a hash",
    "quote_acceptance.organisation": "an organisation",
    "quote_acceptance.form": "a code",
    "quote_acceptance.document_sha256": "a hash",
    "quote_acceptance.document_ref": "a reference to a stored document",
    "quote_rejection.quote_hash": "a hash",
    "quote_rejection.organisation": "an organisation",
}


def test_every_text_column_of_a_read_model_has_chosen():
    text_columns = {
        f"{table}.{column.key}"
        for table, model in MODELS.items()
        for column in sa_inspect(model).columns
        if isinstance(column.type, String | LargeBinary | JSONB)
    }
    in_rows = {
        f"{table}.{name}" for table, names in ROW_ONLY_COLUMNS.items() for name in names
    }
    assert not in_rows & set(STAYS_IN_A_FACT)
    assert text_columns - in_rows - set(STAYS_IN_A_FACT) == set()
    for table, names in ROW_ONLY_COLUMNS.items():
        assert names <= {column.key for column in sa_inspect(MODELS[table]).columns}


def test_a_fact_keeps_the_key_of_what_only_the_row_holds():
    fields = {
        "acceptance": {
            "id": str(uuid4()),
            "signer_name": "Voorbeeld Tekenaar",
            "signer_email": "tekenaar@voorbeeld.example",
            "form": "signing_link",
        },
        "assignment_id": str(uuid4()),
    }
    kept = as_recorded("quote_accepted", fields)
    assert kept["acceptance"]["signer_name"] is None
    assert kept["acceptance"]["signer_email"] is None
    assert kept["acceptance"]["form"] == "signing_link"
    assert fields["acceptance"]["signer_name"] == "Voorbeeld Tekenaar"
    # A fact that names no such row is kept as it is.
    assert as_recorded("assignment_shared", {"x": 1}) == {"x": 1}


def test_a_fact_keeps_its_name_for_good():
    assert set(FACTS) == FACT_NAMES


@pytest.mark.parametrize("fact", sorted(FACTS))
def test_every_fact_has_a_kind_and_a_title(fact):
    assert FACTS[fact].title
    assert FACTS[fact].kind_of(None)


def test_plain_has_one_form_for_one_value():
    moment = datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=1)))
    assert plain(moment) == "2026-01-01T11:00:00.000000+00:00"
    assert plain(Decimal("0.800")) == "0.8"
    assert plain(Decimal("100")) == "100"
    assert plain(Decimal("-0")) == "0"
    assert plain(date(2026, 1, 1)) == "2026-01-01"
    assert plain(b"\x00\xff") == base64.b64encode(b"\x00\xff").decode()
    key = uuid4()
    assert plain({key: [key]}) == {str(key): [str(key)]}


def test_plain_refuses_a_moment_without_a_zone():
    with pytest.raises(ValueError):
        plain(datetime(2026, 1, 1))


def test_a_float_stands_only_in_what_a_peer_sent():
    assert plain({"gewicht": 1.5}) == {"gewicht": 1.5}
    assert normal(QuoteAcceptance, "organisation", {"gewicht": 1.5}) == {"gewicht": 1.5}
    with pytest.raises(TypeError):
        normal(Assignment, "quoted_amount_cents", 1.5)


def test_a_float_holds_no_fte_either():
    with pytest.raises(TypeError):
        normal(BudgetLine, "fte", 0.1 + 0.2)
    with pytest.raises(TypeError):
        changes_of(BudgetLine, fte=0.5)
    assert normal(BudgetLine, "fte", Decimal(str(0.1 + 0.2))) == "0.3"


def test_a_value_is_cut_to_what_the_column_keeps():
    assert normal(BudgetLine, "fte", Decimal("0.12345")) == "0.123"
    assert normal(BudgetLine, "fte", 1) == "1"
    assert normal(BudgetLine, "fte", "0.800") == "0.8"


def test_typed_goes_through_the_attribute_not_the_column_name():
    assert typed(BudgetLine, "detail", "tot Q2") == "tot Q2"
    with pytest.raises(KeyError):
        typed(BudgetLine, "description", "de hybride is geen kolom")


def test_typed_and_normal_are_each_others_inverse():
    canonical = b'{"total":1}'
    for model, key, value in (
        (Assignment, "id", uuid4()),
        (Assignment, "start_date", date(2026, 1, 1)),
        (Assignment, "shared_at", NOW),
        (BudgetLine, "fte", Decimal("0.5")),
        (Quote, "canonical", canonical),
    ):
        text = normal(model, key, value)
        assert typed(model, key, text) == value
        assert normal(model, key, typed(model, key, text)) == text


def test_a_new_row_says_every_column():
    row = _assignment()
    assert set(row) == set(columns_of(Assignment))
    assert "version" not in row and "updated_at" not in row and "created_at" not in row
    # A default of the model is written down, not left to the database.
    line = _line(row["id"])
    assert line["kind"] == "personnel"


def test_a_fact_from_before_a_column_reads_as_the_column_holds_it_unsaid():
    assignment = _assignment(notes="Eerste notitie")
    line = _line(assignment["id"], amount_cents=1234)
    for row, key in (
        (assignment, "notes"),
        (assignment, "kind"),
        (assignment, "context_refs"),
        (line, "amount_cents"),
        (line, "period_source"),
    ):
        del row[key]
    read_assignment = _row("assignment", assignment)
    assert read_assignment.notes is None
    assert read_assignment.kind == "external"
    assert read_assignment.context_refs is None, "only a scalar default counts"
    read_line = _row("budget_line", line)
    assert read_line.amount_cents is None
    assert read_line.period_source == "own"
    assert read_line.fte == Decimal("0.8"), "what a fact does say stays typed"
    assert read_line.start_date == date(2026, 1, 1)
    assert not hasattr(read_line, "version"), "no part of what a fact says"


def test_a_row_reads_past_a_key_that_is_no_column_any_more():
    assignment = _assignment()
    assignment["kolom_van_vroeger"] = "weg"
    assert not hasattr(_row("assignment", assignment), "kolom_van_vroeger")


def test_the_default_of_a_column_is_in_the_form_a_fact_holds_it():
    assert default_of(Assignment, "status") == "draft"
    assert default_of(BudgetLine, "position") == 1
    assert default_of(Assignment, "notes") is None
    assert default_of(Assignment, "context_refs") is None, "a callable is no scalar"


def test_a_new_row_refuses_what_is_no_column_and_needs_what_has_no_default():
    with pytest.raises(ValueError, match="no column"):
        row_of(Assignment, id=uuid4(), bestaat_niet=1)
    with pytest.raises(ValueError, match="needs a value"):
        row_of(AssignmentRole, id=uuid4())


def test_an_effect_must_be_whole_and_in_its_form():
    row = _assignment()
    check_effect(Insert("assignment", row["id"], row))
    with pytest.raises(ValueError, match="lacks"):
        check_effect(Insert("assignment", row["id"], {"id": row["id"]}))
    with pytest.raises(ValueError, match="not in its form"):
        check_effect(Patch("budget_line", row["id"], {"fte": "0.800"}))
    check_effect(Patch("budget_line", row["id"], changes_of(BudgetLine, fte="0.800")))
    check_effect(Drop("assignment", row["id"]))
    check_effect(Flush())


def test_a_fold_applies_what_each_fact_says_in_the_order_of_the_chronicle():
    assignment = _assignment()
    line = _line(assignment["id"])
    grams = [
        _gram(
            1,
            "assignment_created",
            {"assignment": assignment, "owner_role": None},
        ),
        _gram(2, "budget_line_added", {"line": line}),
        _gram(
            3,
            "budget_line_changed",
            {"line_id": line["id"], "changes": changes_of(BudgetLine, fte="1.000")},
        ),
    ]
    # Whatever order they come in: the position counts.
    ledger = fold(reversed(grams))
    assert ledger.table("budget_line")[line["id"]]["fte"] == "1"
    assert fold(grams, upto=2).table("budget_line")[line["id"]]["fte"] == "0.8"
    assert fold(grams, upto=1).table("budget_line") == {}


def test_a_removed_line_is_gone_from_the_moment_on_and_stays_in_the_moment_before():
    assignment = _assignment()
    line = _line(assignment["id"])
    grams = [
        _gram(1, "assignment_created", {"assignment": assignment, "owner_role": None}),
        _gram(2, "budget_line_added", {"line": line}),
        _gram(3, "budget_line_removed", {"line_id": line["id"]}),
    ]
    assert line["id"] in fold(grams, upto=2).table("budget_line")
    assert line["id"] not in fold(grams).table("budget_line")


def test_a_later_status_keeps_the_note_of_a_verbal_agreement():
    assignment = _assignment()
    grams = [
        _gram(1, "assignment_created", {"assignment": assignment, "owner_role": None}),
        _gram(
            2,
            "assignment_status_changed",
            {
                "assignment_id": assignment["id"],
                "from": "quoted",
                "to": "verbally_agreed",
                "reason": "Telefonisch",
                "verbal_agreement_note": "Telefonisch",
                "verbal_agreement_at": plain(NOW),
            },
        ),
        _gram(
            3,
            "assignment_status_changed",
            {
                "assignment_id": assignment["id"],
                "from": "verbally_agreed",
                "to": "accepted",
                "reason": None,
            },
        ),
    ]
    row = fold(grams).table("assignment")[assignment["id"]]
    assert row["status"] == "accepted"
    assert row["verbal_agreement_note"] == "Telefonisch"


def test_a_fact_whose_values_are_gone_leaves_the_state_incomplete_and_says_so():
    assignment = _assignment()
    grams = [
        _gram(1, "assignment_created", {"assignment": assignment, "owner_role": None}),
        _gram(2, "budget_line_added", None),
    ]
    ledger = fold(grams)
    assert ledger.erased == [2]
    assert grams[1].erased


def test_a_patch_or_a_drop_on_a_row_the_chronicle_does_not_know_changes_nothing():
    ledger = fold(
        [
            _gram(1, "budget_line_changed", {"line_id": "x", "changes": {"fte": "1"}}),
            _gram(2, "budget_line_removed", {"line_id": "x"}),
        ]
    )
    assert ledger.table("budget_line") == {}
    assert ledger.erased == []


def test_only_a_fact_that_creates_the_case_starts_a_chronicle():
    assignment = _assignment()
    born = _gram(
        1, "assignment_created", {"assignment": assignment, "owner_role": None}
    )
    later = _gram(2, "budget_line_changed", {"line_id": "x", "changes": {}})
    assert is_born([later, born])
    assert not is_born([later])
    assert not is_born([])


def test_a_flush_means_nothing_in_a_fold():
    assignment = _assignment()
    role = row_of(
        AssignmentRole,
        id=uuid4(),
        assignment_id=assignment["id"],
        person_id=uuid4(),
        role="owner",
    )
    effects = effects_of(
        "assignment_created", {"assignment": assignment, "owner_role": role}
    )
    assert isinstance(effects[1], Flush)
    ledger = fold(
        [_gram(1, "assignment_created", {"assignment": assignment, "owner_role": role})]
    )
    assert list(ledger.table("assignment_role")) == [role["id"]]


def test_a_new_owner_comes_after_the_old_one_stepped_down():
    effects = effects_of(
        "assignment_role_set",
        {"role": {"id": "new", "role": "owner"}, "new": False, "demoted": ["old"]},
    )
    assert [type(effect) for effect in effects] == [Patch, Flush, Patch]
    assert effects[0].id == "old" and effects[0].values == {"role": "manager"}
    assert effects[2].id == "new" and effects[2].values == {"role": "owner"}


def test_a_new_invitation_is_written_before_the_offer_that_names_it():
    effects = effects_of(
        "quote_offered",
        {
            "offer": {"id": "o", "invitation_id": "i"},
            "invitation": {"id": "i"},
            "renewed": None,
            "shared": None,
            "assignment_id": "a",
        },
    )
    assert [type(effect) for effect in effects] == [Insert, Flush, Insert]
    assert effects[0].table == "quote_invitation" and effects[2].table == "quote_offer"


def test_what_a_quote_replaces_is_in_the_fact():
    quote_id = str(uuid4())
    effects = effects_of(
        "quote_issued",
        {
            "quote": {"id": quote_id, "assignment_id": "a"},
            "supersedes": ["old"],
            "assignment": {"quote_date": "2026-11-03", "status": "quoted"},
        },
    )
    assert effects[0] == Patch("quote", "old", {"status": "superseded"})
    assert effects[1].table == "quote" and effects[1].id == quote_id
    assert effects[2] == Patch(
        "assignment", "a", {"quote_date": "2026-11-03", "status": "quoted"}
    )


@pytest.mark.parametrize(
    ("fields", "kind"),
    [
        ({"acceptance": {"form": "signing_link"}}, DECRETOGRAM),
        ({"acceptance": {"form": "own_instance"}}, DECRETOGRAM),
        ({"acceptance": {"form": "uploaded_pdf"}}, EXECUTOGRAM),
        (
            {
                "acceptance": {"form": "own_instance"},
                "received": {"from": "p", "id": "1"},
            },
            EXECUTOGRAM,
        ),
    ],
)
def test_recording_a_signature_made_elsewhere_is_no_decision_here(fields, kind):
    assert FACTS["quote_accepted"].kind_of(fields) == kind


@pytest.mark.parametrize(
    ("target", "title"),
    [
        ("in_progress", "Opdracht in uitvoering gezet"),
        ("verbally_agreed", "Mondeling akkoord genoteerd"),
        ("cancelled", "Opdracht beëindigd"),
        ("completed", "Opdracht afgerond"),
    ],
)
def test_a_change_of_status_says_what_it_led_to(target, title):
    assert title_of("assignment_status_changed", {"to": target}) == title


@pytest.mark.parametrize(
    ("fields", "title"),
    [
        ({"acceptance": {"form": "uploaded_pdf"}}, "Getekende pdf vastgelegd"),
        ({"acceptance": {"form": "signing_link"}}, "Offerte getekend"),
        ({"acceptance": {"form": "own_instance"}}, "Offerte getekend"),
        ({"acceptance": {}}, "Offerte getekend"),
        ({"quote_id": "een ouder feit"}, "Offerte getekend"),
        ({}, "Offerte getekend"),
        (None, "Offerte getekend"),
    ],
)
def test_who_records_a_signed_pdf_is_not_told_as_who_signed(fields, title):
    assert title_of("quote_accepted", fields) == title


def test_diff_says_what_a_moment_changed():
    assignment = _assignment()
    line = _line(assignment["id"])
    other = _line(assignment["id"])
    grams = [
        _gram(1, "assignment_created", {"assignment": assignment, "owner_role": None}),
        _gram(2, "budget_line_added", {"line": line}),
        _gram(3, "budget_line_added", {"line": other}),
        _gram(
            4,
            "budget_line_changed",
            {"line_id": line["id"], "changes": changes_of(BudgetLine, fte="1")},
        ),
        _gram(5, "budget_line_removed", {"line_id": other["id"]}),
    ]
    changed = diff(fold(grams, upto=3), fold(grams, upto=4))
    assert [(c.id, c.change) for c in changed] == [(line["id"], "changed")]
    assert changed[0].columns == {"fte": ("0.8", "1")}
    removed = diff(fold(grams, upto=4), fold(grams))
    assert [(c.id, c.change) for c in removed] == [(other["id"], "removed")]
    added = diff(fold(grams, upto=2), fold(grams, upto=3))
    assert [(c.id, c.change) for c in added] == [(other["id"], "added")]


def test_no_fact_writes_an_attribute_that_is_not_a_column():
    columns = {
        table: {attr.key for attr in sa_inspect(model).column_attrs}
        for table, model in MODELS.items()
    }
    for effect in (
        *effects_of(
            "quote_accepted",
            {
                "assignment_id": "a",
                "assignment": {"status": "accepted"},
                "acceptance": {"id": "x", "quote_id": "q"},
                "invitation": {"id": "i", "used_at": "t", "person_id": "p"},
            },
        ),
        *effects_of(
            "approval_approved",
            {
                "approval_id": "x",
                "decided_by_id": "p",
                "decided_at": "t",
                "evidence_id": None,
                "decision_note": None,
                "self_approved": False,
            },
        ),
        *effects_of(
            "approval_withdrawn",
            {"approval_id": "x", "withdrawn_by_id": "p", "withdrawn_at": "t"},
        ),
        *effects_of("invitation_renewed", {"invitation_id": "x", "expires_at": "t"}),
        *effects_of(
            "invitation_withdrawn",
            {"invitation_id": "x", "withdrawn_at": "t", "withdrawn_by_id": "p"},
        ),
        *effects_of("invitation_opened", {"invitation_id": "x", "opened_at": "t"}),
        *effects_of(
            "quote_document_fixed",
            {
                "quote_id": "x",
                "document_ref": "r",
                "document_sha256": "s",
                "document_fixed_at": "t",
                "document_origin": "issue",
            },
        ),
        *effects_of(
            "assignment_shared",
            {"assignment_id": "a", "shared_with_instance_uri": "u", "shared_at": "t"},
        ),
        *effects_of(
            "acceptance_date_corrected", {"acceptance_id": "x", "signed_at": "t"}
        ),
        *effects_of(
            "dossier_closed", {"assignment_id": "a", "dossier_closed_on": "2026-11-25"}
        ),
        *effects_of("dossier_reopened", {"assignment_id": "a"}),
    ):
        if isinstance(effect, Flush):
            continue
        if isinstance(effect, Patch):
            assert set(effect.values) <= columns[effect.table], effect
