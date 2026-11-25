"""The facts on the path of winning an assignment, and what each one does.

A fact is one act or decision, recorded once: the chronolexogram of
chronolexografie. ``effects`` reads the fields of the fact and nothing else.
What was decided when the fact arose (which quotes it replaces, which lines
moved) is in its fields, so a replay never decides anything again.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from grip.chronicle.effects import Drop, Effect, Flush, Insert, Patch

GENERAL = "general"
DECRETOGRAM = "decretogram"
EXECUTOGRAM = "executogram"
LEXOGRAM = "lexogram"

ASSIGNMENT = "assignment"
ROLE = "assignment_role"
LINE = "budget_line"
QUOTE = "quote"
INVITATION = "quote_invitation"
OFFER = "quote_offer"
APPROVAL = "quote_approval"
ACCEPTANCE = "quote_acceptance"
REJECTION = "quote_rejection"

# The tables that are read models of the chronicle.
READ_MODELS = (
    ASSIGNMENT,
    ROLE,
    LINE,
    QUOTE,
    INVITATION,
    OFFER,
    APPROVAL,
    ACCEPTANCE,
    REJECTION,
)

Fields = Mapping[str, Any]


def _row(table: str, values: Fields) -> Insert:
    return Insert(table, str(values["id"]), dict(values))


def _created(fields: Fields) -> tuple[Effect, ...]:
    assignment = _row(ASSIGNMENT, fields["assignment"])
    if not fields.get("owner_role"):
        return (assignment,)
    return (assignment, Flush(), _row(ROLE, fields["owner_role"]))


def _changed(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(ASSIGNMENT, str(fields["assignment_id"]), fields["changes"]),
        *(
            Patch(LINE, line_id, period)
            for line_id, period in (fields.get("moved_lines") or {}).items()
        ),
    )


def _status_changed(fields: Fields) -> tuple[Effect, ...]:
    values: dict[str, Any] = {"status": fields["to"]}
    if fields["to"] == "verbally_agreed":
        # Kept after formal acceptance: only this step writes them.
        values["verbal_agreement_note"] = fields["verbal_agreement_note"]
        values["verbal_agreement_at"] = fields["verbal_agreement_at"]
    return (Patch(ASSIGNMENT, str(fields["assignment_id"]), values),)


def _share(fields: Fields) -> dict[str, Any]:
    return {
        "shared_with_instance_uri": fields["shared_with_instance_uri"],
        "shared_at": fields["shared_at"],
    }


def _shared(fields: Fields) -> tuple[Effect, ...]:
    return (Patch(ASSIGNMENT, str(fields["assignment_id"]), _share(fields)),)


def _role_set(fields: Fields) -> tuple[Effect, ...]:
    role = fields["role"]
    written: Effect = (
        _row(ROLE, role)
        if fields.get("new")
        else Patch(ROLE, str(role["id"]), {"role": role["role"]})
    )
    demoted = tuple(
        Patch(ROLE, role_id, {"role": "manager"}) for role_id in fields["demoted"]
    )
    # One owner per assignment: the old owner steps down before the new one
    # steps up, whichever row sorts first.
    return (*demoted, Flush(), written) if demoted else (written,)


def _role_removed(fields: Fields) -> tuple[Effect, ...]:
    return (Drop(ROLE, str(fields["role_id"])),)


def _line_added(fields: Fields) -> tuple[Effect, ...]:
    return (_row(LINE, fields["line"]),)


def _line_changed(fields: Fields) -> tuple[Effect, ...]:
    return (Patch(LINE, str(fields["line_id"]), fields["changes"]),)


def _line_removed(fields: Fields) -> tuple[Effect, ...]:
    return (Drop(LINE, str(fields["line_id"])),)


def _role_merged(fields: Fields) -> tuple[Effect, ...]:
    values = {"role_id": fields["role_id"], "role": fields["role"]}
    return tuple(Patch(LINE, line_id, values) for line_id in fields["line_ids"])


def _quote_made(fields: Fields) -> tuple[Effect, ...]:
    quote = fields["quote"]
    return (
        *(
            Patch(QUOTE, quote_id, {"status": "superseded"})
            for quote_id in fields["supersedes"]
        ),
        _row(QUOTE, quote),
        Patch(ASSIGNMENT, str(quote["assignment_id"]), fields["assignment"]),
    )


def _document_fixed(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(
            QUOTE,
            str(fields["quote_id"]),
            {
                "document_ref": fields["document_ref"],
                "document_sha256": fields["document_sha256"],
                "document_fixed_at": fields["document_fixed_at"],
                "document_origin": fields["document_origin"],
            },
        ),
    )


def _renewal(renewed: Fields) -> Patch:
    return Patch(
        INVITATION,
        str(renewed["invitation_id"]),
        {
            "expires_at": renewed["expires_at"],
            "withdrawn_at": None,
            "withdrawn_by_id": None,
        },
    )


def _offered(fields: Fields) -> tuple[Effect, ...]:
    effects: list[Effect] = []
    if fields.get("invitation"):
        effects += [_row(INVITATION, fields["invitation"]), Flush()]
    if fields.get("renewed"):
        effects.append(_renewal(fields["renewed"]))
    effects.append(_row(OFFER, fields["offer"]))
    if fields.get("shared"):
        effects.append(
            Patch(ASSIGNMENT, str(fields["assignment_id"]), _share(fields["shared"]))
        )
    return tuple(effects)


def _invitation_renewed(fields: Fields) -> tuple[Effect, ...]:
    return (_renewal(fields),)


def _invitation_withdrawn(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(
            INVITATION,
            str(fields["invitation_id"]),
            {
                "withdrawn_at": fields["withdrawn_at"],
                "withdrawn_by_id": fields["withdrawn_by_id"],
            },
        ),
    )


def _invitation_opened(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(
            INVITATION, str(fields["invitation_id"]), {"opened_at": fields["opened_at"]}
        ),
    )


def _approval_requested(fields: Fields) -> tuple[Effect, ...]:
    return (_row(APPROVAL, fields["approval"]),)


def _approval_decided(status: str) -> Callable[[Fields], tuple[Effect, ...]]:
    def effects(fields: Fields) -> tuple[Effect, ...]:
        return (
            Patch(
                APPROVAL,
                str(fields["approval_id"]),
                {
                    "status": status,
                    "decided_by_id": fields["decided_by_id"],
                    "decided_at": fields["decided_at"],
                    "evidence_id": fields["evidence_id"],
                    "decision_note": fields["decision_note"],
                    "self_approved": fields["self_approved"],
                },
            ),
        )

    return effects


def _approval_withdrawn(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(
            APPROVAL,
            str(fields["approval_id"]),
            {
                "status": "withdrawn",
                "withdrawn_by_id": fields["withdrawn_by_id"],
                "withdrawn_at": fields["withdrawn_at"],
            },
        ),
    )


def _accepted(fields: Fields) -> tuple[Effect, ...]:
    acceptance = fields["acceptance"]
    effects: list[Effect] = [
        _row(ACCEPTANCE, acceptance),
        Patch(QUOTE, str(acceptance["quote_id"]), {"status": "accepted"}),
    ]
    invitation = fields.get("invitation")
    if invitation:
        values = {"used_at": invitation["used_at"]}
        if invitation.get("person_id") is not None:
            values["person_id"] = invitation["person_id"]
        effects.append(Patch(INVITATION, str(invitation["id"]), values))
    effects.append(
        Patch(ASSIGNMENT, str(fields["assignment_id"]), fields["assignment"])
    )
    return tuple(effects)


def _acceptance_corrected(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(
            ACCEPTANCE, str(fields["acceptance_id"]), {"signed_at": fields["signed_at"]}
        ),
    )


def _rejected(fields: Fields) -> tuple[Effect, ...]:
    rejection = fields["rejection"]
    return (
        _row(REJECTION, rejection),
        Patch(QUOTE, str(rejection["quote_id"]), {"status": "rejected"}),
        Patch(ASSIGNMENT, str(fields["assignment_id"]), fields["assignment"]),
    )


def _dossier_closed(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(
            ASSIGNMENT,
            str(fields["assignment_id"]),
            {"dossier_closed_on": fields["dossier_closed_on"]},
        ),
    )


def _dossier_reopened(fields: Fields) -> tuple[Effect, ...]:
    return (
        Patch(ASSIGNMENT, str(fields["assignment_id"]), {"dossier_closed_on": None}),
    )


def _nothing(fields: Fields) -> tuple[Effect, ...]:
    return ()


def _status_kind(fields: Fields) -> str:
    target = fields.get("to")
    if target in ("in_progress", "cancelled", "completed", "accounted"):
        return DECRETOGRAM
    # Noting what someone else asked, said or signed is not deciding it.
    if target in ("requested", "verbally_agreed", "accepted", "rejected"):
        return EXECUTOGRAM
    return GENERAL


def _acceptance_kind(fields: Fields) -> str:
    if fields.get("received") or fields["acceptance"].get("form") == "uploaded_pdf":
        return EXECUTOGRAM
    return DECRETOGRAM


def _rejection_kind(fields: Fields) -> str:
    if fields.get("received") or fields["rejection"].get("recorded_by_id"):
        return EXECUTOGRAM
    return DECRETOGRAM


@dataclass(frozen=True)
class Fact:
    name: str
    # The class of this fact, or how it follows from the fields when the same
    # act can be a decision here or the record of a decision made elsewhere.
    kind: str | Callable[[Fields], str]
    # What it says on the screen for who may only know that it happened.
    title: str
    effects: Callable[[Fields], tuple[Effect, ...]]
    # A case starts with this fact: its chronicle is complete from here on.
    birth: bool = False
    # False for what says something about the chronicle, not about the case.
    moment: bool = True

    def kind_of(self, fields: Fields | None) -> str:
        if isinstance(self.kind, str):
            return self.kind
        return self.kind(fields) if fields is not None else GENERAL


FACTS: dict[str, Fact] = {
    fact.name: fact
    for fact in (
        Fact(
            "assignment_created", GENERAL, "Opdracht toegevoegd", _created, birth=True
        ),
        Fact(
            "assignment_requested",
            DECRETOGRAM,
            "Offerte aangevraagd",
            _created,
            birth=True,
        ),
        Fact(
            "assignment_request_received",
            EXECUTOGRAM,
            "Aanvraag ontvangen",
            _created,
            birth=True,
        ),
        Fact("assignment_changed", GENERAL, "Opdracht gewijzigd", _changed),
        Fact(
            "assignment_status_changed",
            _status_kind,
            "Status gewijzigd",
            _status_changed,
        ),
        Fact("assignment_shared", EXECUTOGRAM, "Gedeeld met instantie", _shared),
        Fact(
            "assignment_role_set",
            GENERAL,
            "Eigenaar of manager aangewezen",
            _role_set,
        ),
        Fact(
            "assignment_role_removed",
            GENERAL,
            "Manager van de opdracht gehaald",
            _role_removed,
        ),
        Fact(
            "budget_line_added",
            GENERAL,
            "Begrotingsregel toegevoegd",
            _line_added,
        ),
        Fact(
            "budget_line_changed",
            GENERAL,
            "Begrotingsregel gewijzigd",
            _line_changed,
        ),
        Fact(
            "budget_line_removed",
            GENERAL,
            "Begrotingsregel verwijderd",
            _line_removed,
        ),
        Fact("budget_lines_role_merged", GENERAL, "Rol samengevoegd", _role_merged),
        Fact("quote_issued", DECRETOGRAM, "Offerte gemaakt", _quote_made),
        Fact("quote_received", EXECUTOGRAM, "Offerte ontvangen", _quote_made),
        Fact(
            "quote_document_fixed",
            EXECUTOGRAM,
            "Bestand van de offerte vastgelegd",
            _document_fixed,
        ),
        Fact("quote_offered", EXECUTOGRAM, "Offerte aangeboden", _offered),
        Fact("invitation_renewed", GENERAL, "Tekenlink verlengd", _invitation_renewed),
        Fact(
            "invitation_withdrawn",
            GENERAL,
            "Tekenlink ingetrokken",
            _invitation_withdrawn,
        ),
        Fact("invitation_opened", EXECUTOGRAM, "Tekenlink geopend", _invitation_opened),
        Fact(
            "approval_requested",
            GENERAL,
            "Interne goedkeuring gevraagd",
            _approval_requested,
        ),
        Fact(
            "approval_approved",
            DECRETOGRAM,
            "Offerte intern goedgekeurd",
            _approval_decided("approved"),
        ),
        Fact(
            "approval_sent_back",
            DECRETOGRAM,
            "Offerte intern teruggestuurd",
            _approval_decided("sent_back"),
        ),
        Fact(
            "approval_withdrawn",
            GENERAL,
            "Goedkeuring ingetrokken",
            _approval_withdrawn,
        ),
        Fact("quote_accepted", _acceptance_kind, "Offerte getekend", _accepted),
        Fact(
            "acceptance_date_corrected",
            EXECUTOGRAM,
            "Datum van tekenen gecorrigeerd",
            _acceptance_corrected,
        ),
        Fact("quote_rejected", _rejection_kind, "Offerte afgewezen", _rejected),
        # ADR 0057: the closing day starts the retention period of the case.
        Fact("dossier_closed", DECRETOGRAM, "Dossier gesloten", _dossier_closed),
        Fact("dossier_reopened", DECRETOGRAM, "Dossier heropend", _dossier_reopened),
        # Changes no row: the decision itself is what counts, as activity.
        Fact("dossier_kept_open", DECRETOGRAM, "Dossier blijft open", _nothing),
        Fact(
            "chronicle_rebuilt",
            GENERAL,
            "Leesmodellen hersteld uit de kroniek",
            _nothing,
            moment=False,
        ),
        # Filed under the rate book, not under a case. Rate cards stay ordinary
        # tables: the fact holds the priced book as it stood from then on.
        Fact(
            "rates_established",
            LEXOGRAM,
            "Tarieven gewijzigd",
            _nothing,
            moment=False,
        ),
    )
}

# What a change of status says, by the status it leads to.
STATUS_TITLES: dict[str, str] = {
    "requested": "Offerte aangevraagd",
    "quoted": "Terug naar offerte",
    "verbally_agreed": "Mondeling akkoord genoteerd",
    "accepted": "Akkoord vastgelegd",
    "in_progress": "Opdracht in uitvoering gezet",
    "completed": "Opdracht afgerond",
    "accounted": "Opdracht verantwoord",
    "rejected": "Afwijzing vastgelegd",
    "cancelled": "Opdracht beëindigd",
    "draft": "Terug naar concept",
}
# A step to quoted from these goes back to the quote; from any other it marks
# one as made.
_BACK_TO_QUOTED = ("verbally_agreed", "rejected")


def received_from(fields: Fields) -> str | None:
    """The organisation a fact came in from, when its message named one."""
    received = fields.get("received") or {}
    return str(received.get("received_from") or "").strip() or None


def title_of(name: str, fields: Fields | None) -> str:
    fact = FACTS[name]
    if not fields:
        return fact.title
    if name == "assignment_status_changed":
        if fields.get("to") == "quoted" and fields.get("from") not in _BACK_TO_QUOTED:
            return "Offerte als gemaakt gemarkeerd"
        return STATUS_TITLES.get(str(fields.get("to")), fact.title)
    if name == "approval_withdrawn" and fields.get("was") == "requested":
        return "Vraag om goedkeuring ingetrokken"
    if (
        name == "quote_accepted"
        and (fields.get("acceptance") or {}).get("form") == "uploaded_pdf"
    ):
        return "Getekende pdf vastgelegd"
    if name in ("quote_received", "assignment_request_received"):
        sender = received_from(fields)
        if sender is not None:
            return f"{fact.title} van {sender}"
    return fact.title


def effects_of(name: str, fields: Fields) -> tuple[Effect, ...]:
    return FACTS[name].effects(fields)


# Who someone is, or what they typed, where a stand needs only what the row holds
# now: a column written once, or one no stand shows. A fact keeps the key without
# the value and a stand reads the value in the row (ADR 0056), so erasing it is
# changing that row, and nothing in the chronicle brings it back.
ROW_ONLY_COLUMNS: dict[str, frozenset[str]] = {
    ASSIGNMENT: frozenset({"client_contact"}),
    LINE: frozenset({"intended_person_id"}),
    QUOTE: frozenset({"canonical"}),
    INVITATION: frozenset({"email"}),
    OFFER: frozenset({"recipient"}),
    APPROVAL: frozenset({"request_note", "decision_note"}),
    ACCEPTANCE: frozenset({"signer_name", "signer_email", "signer_function", "jws"}),
    REJECTION: frozenset({"reason"}),
}

# Where a fact names such a row: the part of its fields that holds the columns
# (None for the fields themselves), the key of the row id, and the table.
_ROW_ONLY_PARTS: dict[str, tuple[tuple[str | None, str, str], ...]] = {
    "assignment_created": (("assignment", "id", ASSIGNMENT),),
    "assignment_requested": (("assignment", "id", ASSIGNMENT),),
    "assignment_request_received": (("assignment", "id", ASSIGNMENT),),
    "assignment_changed": (("changes", "assignment_id", ASSIGNMENT),),
    "budget_line_added": (("line", "id", LINE),),
    "budget_line_changed": (("changes", "line_id", LINE),),
    "quote_issued": (("quote", "id", QUOTE),),
    "quote_received": (("quote", "id", QUOTE),),
    "quote_offered": (("invitation", "id", INVITATION), ("offer", "id", OFFER)),
    "approval_requested": (("approval", "id", APPROVAL),),
    "approval_approved": ((None, "approval_id", APPROVAL),),
    "approval_sent_back": ((None, "approval_id", APPROVAL),),
    "quote_accepted": (("acceptance", "id", ACCEPTANCE),),
    "quote_rejected": (("rejection", "id", REJECTION),),
}


def row_only_parts(
    name: str, fields: Fields | None
) -> list[tuple[str | None, str, str, frozenset[str]]]:
    """Where this fact leaves values in a row: part, table, row id, columns."""
    found: list[tuple[str | None, str, str, frozenset[str]]] = []
    for part, id_key, table in _ROW_ONLY_PARTS.get(name, ()):
        holder = fields if part is None else (fields or {}).get(part)
        if not holder:
            continue
        columns = ROW_ONLY_COLUMNS[table] & set(holder)
        row_id = holder.get(id_key) or (fields or {}).get(id_key)
        if columns and row_id:
            found.append((part, table, str(row_id), frozenset(columns)))
    return found


def with_row_values(
    name: str, fields: Fields, values: Callable[[str, str, str], Any]
) -> dict[str, Any]:
    """The fields with each row-only column set to ``values(table, row_id, column)``."""
    result = dict(fields)
    for part, table, row_id, columns in row_only_parts(name, fields):
        holder = result if part is None else dict(result[part])
        for column in columns:
            holder[column] = values(table, row_id, column)
        if part is not None:
            result[part] = holder
    return result


def as_recorded(name: str, fields: Fields) -> dict[str, Any]:
    """The fields as the stream keeps them: without what only the row holds."""
    return with_row_values(name, fields, lambda _table, _row_id, _column: None)
