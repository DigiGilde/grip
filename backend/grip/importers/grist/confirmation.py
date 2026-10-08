"""The confirmation list: proposals a person approves before they count.

The import writes one JSON file with an item per thing it had to interpret:
a person (email address, and whether the row is a real person), the billing
scale of a person, and the fields of a budget line. Each item shows the
original text, the proposal, how sure the parser is and why.

A person sets ``status`` to ``bevestigd`` (after correcting ``values`` where
needed) or to ``overslaan``. Only confirmed items are applied. Writing the
list again for a newer download keeps every decision whose source text did
not change, and puts the others back to ``voorstel``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROPOSED = "voorstel"
CONFIRMED = "bevestigd"
SKIPPED = "overslaan"
STATUSES = (PROPOSED, CONFIRMED, SKIPPED)

KIND_PERSON = "person"
KIND_SCALE = "person_scale"
KIND_LINE = "budget_line"
KINDS = (KIND_PERSON, KIND_SCALE, KIND_LINE)

PERSON_LOAD = "laden"
PERSON_SKIP = "overslaan"

HIGH_CONFIDENCE = "hoog"

FORMAT_VERSION = 1


class ConfirmationError(Exception):
    """The confirmation file cannot be used as it is."""


def source_hash(source: dict[str, Any]) -> str:
    canonical = json.dumps(source, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class ConfirmationItem:
    key: str
    kind: str
    label: str
    source: dict[str, Any]
    proposal: dict[str, Any]
    confidence: str
    remarks: list[str] = field(default_factory=list)
    status: str = PROPOSED
    values: dict[str, Any] = field(default_factory=dict)
    previous_values: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.values:
            self.values = dict(self.proposal)

    @property
    def hash(self) -> str:
        return source_hash(self.source)

    @property
    def confirmed(self) -> bool:
        return self.status == CONFIRMED

    @property
    def skipped(self) -> bool:
        return self.status == SKIPPED

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "confidence": self.confidence,
            "remarks": self.remarks,
            "source": self.source,
            "source_hash": self.hash,
            "proposal": self.proposal,
            "values": self.values,
        }
        if self.previous_values is not None:
            data["previous_values"] = self.previous_values
        return data


def _as_date(value: Any, where: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfirmationError(
            f"{where}: '{value}' is geen datum (jjjj-mm-dd)."
        ) from exc


def _as_decimal(value: Any, where: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation as exc:
        raise ConfirmationError(f"{where}: '{value}' is geen getal.") from exc


def _as_int(value: Any, where: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfirmationError(f"{where}: '{value}' is geen geheel getal.") from exc


@dataclass(frozen=True)
class PersonDecision:
    email: str | None
    load: bool


@dataclass(frozen=True)
class ScaleDecision:
    billing_scale: int | None
    valid_from: date | None


@dataclass(frozen=True)
class LineDecision:
    kind: str
    role: str | None
    fte: Decimal | None
    rate_category: str | None
    start_date: date | None
    end_date: date | None
    amount_cents: int | None
    year: int | None

    def problems(self) -> list[str]:
        if self.kind == "personnel":
            missing = [
                label
                for label, value in (
                    ("fte", self.fte),
                    ("rate_category", self.rate_category),
                    ("start_date", self.start_date),
                    ("end_date", self.end_date),
                )
                if value is None
            ]
            if missing:
                return [f"personeelsregel mist {', '.join(missing)}"]
            if self.rate_category not in ("A", "B", "C", "D", "E"):
                return [f"onbekende categorie {self.rate_category}"]
            assert self.start_date and self.end_date
            if self.end_date < self.start_date:
                return ["einddatum ligt voor begindatum"]
            return []
        if self.kind == "fixed":
            if self.amount_cents is None or self.year is None:
                return ["vaste regel mist amount_cents of year"]
            return []
        return [f"onbekend soort regel '{self.kind}'"]


@dataclass
class ConfirmationList:
    document: str
    items: list[ConfirmationItem] = field(default_factory=list)

    def by_key(self) -> dict[str, ConfirmationItem]:
        return {item.key: item for item in self.items}

    def get(self, key: str) -> ConfirmationItem | None:
        return self.by_key().get(key)

    def open_items(self) -> list[ConfirmationItem]:
        return [item for item in self.items if item.status == PROPOSED]

    def counts(self) -> dict[str, int]:
        result = dict.fromkeys(STATUSES, 0)
        for item in self.items:
            result[item.status] += 1
        return result

    # -- typed decisions ------------------------------------------------------

    def person(self, key: str) -> PersonDecision | None:
        item = self.get(key)
        if item is None or item.status == PROPOSED:
            return None
        if item.skipped:
            return PersonDecision(email=None, load=False)
        action = str(item.values.get("action") or PERSON_LOAD)
        if action not in (PERSON_LOAD, PERSON_SKIP):
            raise ConfirmationError(
                f"{key}: action is '{action}', verwacht '{PERSON_LOAD}' of "
                f"'{PERSON_SKIP}'."
            )
        email = str(item.values.get("email") or "").strip() or None
        if email is not None and "@" not in email:
            raise ConfirmationError(f"{key}: '{email}' is geen e-mailadres.")
        return PersonDecision(email=email, load=action == PERSON_LOAD)

    def scale(self, key: str) -> ScaleDecision | None:
        item = self.get(key)
        if item is None or not item.confirmed:
            return None
        return ScaleDecision(
            billing_scale=_as_int(item.values.get("billing_scale"), key),
            valid_from=_as_date(item.values.get("valid_from"), key),
        )

    def line(self, key: str) -> LineDecision | None:
        item = self.get(key)
        if item is None or not item.confirmed:
            return None
        values = item.values
        decision = LineDecision(
            kind=str(values.get("kind") or ""),
            role=(str(values["role"]).strip() or None) if values.get("role") else None,
            fte=_as_decimal(values.get("fte"), key),
            rate_category=(
                str(values["rate_category"]).strip().upper()
                if values.get("rate_category")
                else None
            ),
            start_date=_as_date(values.get("start_date"), key),
            end_date=_as_date(values.get("end_date"), key),
            amount_cents=_as_int(values.get("amount_cents"), key),
            year=_as_int(values.get("year"), key),
        )
        problems = decision.problems()
        if problems:
            raise ConfirmationError(f"{key}: {'; '.join(problems)}.")
        return decision

    # -- file -----------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "format": FORMAT_VERSION,
            "document": self.document,
            "uitleg": (
                "Zet status op 'bevestigd' na controle (pas 'values' aan waar "
                "nodig) of op 'overslaan'. Alleen bevestigde items worden "
                "toegepast. 'proposal' en 'source' niet wijzigen."
            ),
            "items": [item.to_json() for item in self.items],
        }

    def write(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_json(), indent=2, ensure_ascii=False, default=str)
            + "\n",
            encoding="utf-8",
        )


def read_confirmations(path: str | Path) -> ConfirmationList:
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfirmationError(
            f"De bevestigingslijst is niet te lezen: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfirmationError(
            "De bevestigingslijst is geen geldige JSON "
            f"(regel {exc.lineno}): {exc.msg}."
        ) from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
        raise ConfirmationError("De bevestigingslijst heeft een onbekend formaat.")
    items = []
    seen: set[str] = set()
    for index, raw in enumerate(data.get("items") or []):
        where = f"item {index + 1}"
        try:
            key, kind, status = raw["key"], raw["kind"], raw["status"]
        except (KeyError, TypeError) as exc:
            raise ConfirmationError(f"{where}: key, kind of status ontbreekt.") from exc
        if kind not in KINDS:
            raise ConfirmationError(f"{key}: onbekend soort '{kind}'.")
        if status not in STATUSES:
            raise ConfirmationError(
                f"{key}: status is '{status}', verwacht een van {', '.join(STATUSES)}."
            )
        if key in seen:
            raise ConfirmationError(f"{key}: staat twee keer in de lijst.")
        seen.add(key)
        items.append(
            ConfirmationItem(
                key=key,
                kind=kind,
                label=str(raw.get("label") or ""),
                source=dict(raw.get("source") or {}),
                proposal=dict(raw.get("proposal") or {}),
                confidence=str(raw.get("confidence") or ""),
                remarks=list(raw.get("remarks") or []),
                status=status,
                values=dict(raw.get("values") or {}),
                previous_values=raw.get("previous_values"),
            )
        )
    return ConfirmationList(document=str(data.get("document") or ""), items=items)


@dataclass(frozen=True)
class MergeResult:
    merged: ConfirmationList
    kept: int
    reset: tuple[str, ...]
    new: tuple[str, ...]
    dropped: tuple[str, ...]


def merge(fresh: ConfirmationList, earlier: ConfirmationList | None) -> MergeResult:
    """Carry decisions from an earlier list over to a freshly proposed one.

    A decision is kept only when the source text is unchanged. When the
    source changed, the item goes back to ``voorstel`` and the earlier
    values are shown next to the new proposal.
    """
    if earlier is None:
        return MergeResult(fresh, 0, (), tuple(i.key for i in fresh.items), ())
    old = earlier.by_key()
    kept = 0
    reset: list[str] = []
    new: list[str] = []
    for item in fresh.items:
        before = old.get(item.key)
        if before is None:
            new.append(item.key)
            continue
        if before.hash == item.hash and before.kind == item.kind:
            item.status = before.status
            item.values = dict(before.values)
            if before.status != PROPOSED:
                kept += 1
            continue
        if before.status != PROPOSED:
            item.previous_values = dict(before.values)
            item.remarks = [
                *item.remarks,
                "De bron is gewijzigd sinds de vorige lijst; opnieuw beoordelen.",
            ]
            reset.append(item.key)
    fresh_keys = {item.key for item in fresh.items}
    dropped = tuple(sorted(key for key in old if key not in fresh_keys))
    return MergeResult(fresh, kept, tuple(reset), tuple(new), dropped)


def confirm_by_confidence(
    confirmations: ConfirmationList, confidence: str, kinds: tuple[str, ...] = KINDS
) -> list[str]:
    """Confirm every open item of the given confidence. An explicit bulk act."""
    changed = []
    for item in confirmations.items:
        if (
            item.status == PROPOSED
            and item.confidence == confidence
            and item.kind in kinds
        ):
            item.status = CONFIRMED
            changed.append(item.key)
    return changed
