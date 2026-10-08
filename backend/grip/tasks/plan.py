"""The plan: which tasks arise on a case, when, for whom, and what closes them.

A plan is data, shipped with grip in ``grip/data/tasks``. It is read and
checked against the catalogue once; a plan that names a subject, fact, role
or anchor the code does not offer is refused at start, so a plan can only
arrange work and never reach past a rule of the domain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from grip.tasks import catalogue

_PLAN_DIR = Path(__file__).resolve().parents[1] / "data" / "tasks"
DEFAULT_PLAN_FILE = _PLAN_DIR / "plan.json"


class PlanError(ValueError):
    """The plan names something the catalogue does not offer."""


@dataclass(frozen=True)
class DueRule:
    working_days: int
    after: str


@dataclass(frozen=True)
class Template:
    key: str
    case_kind: str
    track: str
    title: str
    subject: str
    # Fact names that must all hold; a name prefixed with "not " must not.
    when: tuple[str, ...]
    # The fact that closes the task. None: a person ticks it.
    done_when: str | None
    assignee: str
    # A person may also tick a task that a fact can close.
    manual: bool = False
    # Of the subjects in order, only the first one that is not done gets a
    # task: one month to close at a time, not twelve.
    only_first: bool = False
    waiting_on: str | None = None
    due: DueRule | None = None
    link: str | None = None

    @property
    def closes_by_hand(self) -> bool:
        return self.done_when is None or self.manual


@dataclass(frozen=True)
class Track:
    key: str
    label: str


@dataclass(frozen=True)
class Plan:
    version: str
    tracks: dict[str, tuple[Track, ...]]
    templates: dict[str, tuple[Template, ...]]

    def template(self, key: str) -> Template | None:
        for templates in self.templates.values():
            for template in templates:
                if template.key == key:
                    return template
        return None

    def track_label(self, case_kind: str, key: str) -> str:
        for track in self.tracks.get(case_kind, ()):
            if track.key == key:
                return track.label
        return key


def _fact_name(condition: str) -> str:
    return condition[4:] if condition.startswith("not ") else condition


def _template(case_kind: str, tracks: set[str], raw: dict[str, Any]) -> Template:
    key = raw.get("key")
    if not isinstance(key, str) or not key:
        raise PlanError("Een taak in het plan heeft geen sleutel.")

    def fail(message: str) -> PlanError:
        return PlanError(f"Taak {key}: {message}")

    subject = raw.get("for", "case")
    if subject not in catalogue.SUBJECTS[case_kind]:
        raise fail(f"onbekend onderwerp '{subject}'")
    if raw.get("track") not in tracks:
        raise fail(f"onbekend spoor '{raw.get('track')}'")
    known = catalogue.facts_for(case_kind, subject)
    when = tuple(raw.get("when", ()))
    for condition in when:
        if _fact_name(condition) not in known:
            raise fail(f"onbekend feit '{_fact_name(condition)}'")
    done_when = raw.get("done_when")
    if done_when is not None and done_when not in known:
        raise fail(f"onbekend feit '{done_when}'")
    assignee = raw.get("assignee")
    if assignee not in catalogue.ASSIGNEES[case_kind]:
        raise fail(f"onbekende rol '{assignee}'")
    due = None
    if raw.get("due") is not None:
        rule = raw["due"]
        if rule.get("after") not in catalogue.ANCHORS[subject]:
            raise fail(f"onbekend moment '{rule.get('after')}'")
        days = rule.get("working_days")
        if not isinstance(days, int) or days < 0:
            raise fail("de termijn is een aantal werkdagen van nul of meer")
        due = DueRule(working_days=days, after=rule["after"])
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise fail("de titel ontbreekt")
    unknown = set(raw) - {
        "key",
        "track",
        "title",
        "for",
        "when",
        "done_when",
        "assignee",
        "manual",
        "only_first",
        "waiting_on",
        "due",
        "link",
    }
    if unknown:
        raise fail(f"onbekende instelling {sorted(unknown)}")
    return Template(
        key=key,
        case_kind=case_kind,
        track=raw["track"],
        title=title,
        subject=subject,
        when=when,
        done_when=done_when,
        assignee=assignee,
        manual=bool(raw.get("manual", False)),
        only_first=bool(raw.get("only_first", False)),
        waiting_on=raw.get("waiting_on"),
        due=due,
        link=raw.get("link"),
    )


def parse_plan(data: dict[str, Any]) -> Plan:
    """Check a plan against the catalogue and return it."""
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise PlanError("Het plan heeft geen versie.")
    tracks: dict[str, tuple[Track, ...]] = {}
    templates: dict[str, tuple[Template, ...]] = {}
    seen: set[str] = set()
    for case_kind, section in (data.get("case_kinds") or {}).items():
        if case_kind not in catalogue.CASE_KINDS:
            raise PlanError(f"Onbekend soort zaak '{case_kind}'.")
        kind_tracks = tuple(
            Track(key=track["key"], label=track["label"])
            for track in section.get("tracks", ())
        )
        tracks[case_kind] = kind_tracks
        keys = {track.key for track in kind_tracks}
        parsed = []
        for raw in section.get("templates", ()):
            template = _template(case_kind, keys, raw)
            if template.key in seen:
                raise PlanError(f"Taak {template.key} staat twee keer in het plan.")
            seen.add(template.key)
            parsed.append(template)
        templates[case_kind] = tuple(parsed)
    return Plan(version=version, tracks=tracks, templates=templates)


def load_plan(path: Path = DEFAULT_PLAN_FILE) -> Plan:
    return parse_plan(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def current_plan() -> Plan:
    """The plan that ships with this version of grip."""
    return load_plan()


@lru_cache(maxsize=1)
def known_plans() -> dict[str, Plan]:
    """Every plan version in the data folder, by version.

    A case keeps the version it started with. Older versions stay in the
    folder as ``plan-<version>.json``; ``plan.json`` is the current one.
    """
    plans = {current_plan().version: current_plan()}
    for path in sorted(_PLAN_DIR.glob("plan-*.json")):
        plan = load_plan(path)
        plans.setdefault(plan.version, plan)
    return plans


def plan_for(version: str | None) -> Plan:
    """The plan of a case; the current one when its version is gone."""
    if version is None:
        return current_plan()
    return known_plans().get(version, current_plan())
