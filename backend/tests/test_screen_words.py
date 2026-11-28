"""The old words for a place or a thing do not come back in a sentence of the server."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

GRIP = Path(__file__).resolve().parents[1] / "grip"

OLD_WORDS = [
    re.compile(r"Bemensing"),
    re.compile(r"pijplijn", re.IGNORECASE),
    re.compile(r"Stand van zaken"),
    re.compile(r"Wat er gebeurd is"),
    re.compile(r"\b(bij|onder|op) Team\b"),
    re.compile(r"\b(spoor|sporen)\b", re.IGNORECASE),
]


def _hits(text: str) -> list[str]:
    return [pattern.pattern for pattern in OLD_WORDS if pattern.search(text)]


def _strings_of(source: str) -> list[str]:
    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _json_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _json_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _json_strings(item)]
    return []


def offenders(python: dict[str, str], documents: dict[str, str]) -> list[str]:
    found: list[str] = []
    for name, source in python.items():
        for text in _strings_of(source):
            found += [f"{name}: {hit}" for hit in _hits(text)]
    for name, source in documents.items():
        for text in _json_strings(json.loads(source)):
            found += [f"{name}: {hit}" for hit in _hits(text)]
    return found


def test_no_old_word_in_a_sentence_of_the_server():
    python = {
        str(path.relative_to(GRIP)): path.read_text()
        for path in GRIP.rglob("*.py")
        if "migrations" not in path.parts and "importers" not in path.parts
    }
    documents = {
        str(path.relative_to(GRIP)): path.read_text()
        for path in (GRIP / "data" / "tasks").glob("*.json")
    }
    assert offenders(python, documents) == []


def test_the_guard_fails_on_the_old_word():
    assert len(offenders({"a.py": 'LABEL = "Bemensing van de opdracht"'}, {})) == 1
    assert len(offenders({"a.py": 'LABEL = "Als de pijplijn doorgaat"'}, {})) == 1
    plan = '{"label": "Een beheerder doet dit bij Team"}'
    assert len(offenders({}, {"plan.json": plan})) == 1
    assert len(offenders({"a.py": 'MESSAGE = "Dit spoor bestaat niet"'}, {})) == 1
    assert offenders({"a.py": 'KEY = "bemensing"\nPIPELINE = pipeline_cents'}, {}) == []
