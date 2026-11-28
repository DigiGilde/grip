from pathlib import Path

import pytest

from grip.dev.personaboek import PersonaError, load_personas

FRONT = """---
code: {code}
naam: Test
rol: Rol
organisatie: Voorbeeldprogramma
eenheid: Eenheid
fgr: {{functie: F, familie: G, schaal: "11", url: "https://x.org", inschatting: false}}
mandaat: {{tekst: T, bron: aanname}}
grips: []
---
## Wie
Tekst
"""


def write(directory: Path, name: str, content: str) -> None:
    (directory / name).write_text(content, encoding="utf-8")


def test_valid_persona_loads(tmp_path: Path) -> None:
    write(tmp_path, "PRG-PO.md", FRONT.format(code="PRG-PO"))
    _, personas = load_personas(tmp_path)
    assert [p.code for p in personas] == ["PRG-PO"]


def test_missing_key(tmp_path: Path) -> None:
    write(tmp_path, "PRG-PO.md", FRONT.format(code="PRG-PO").replace("rol: Rol\n", ""))
    with pytest.raises(PersonaError, match="rol"):
        load_personas(tmp_path)


def test_code_must_match_filename(tmp_path: Path) -> None:
    write(tmp_path, "PRG-PO.md", FRONT.format(code="PRG-XX"))
    with pytest.raises(PersonaError, match="bestandsnaam"):
        load_personas(tmp_path)


def test_missing_front_matter(tmp_path: Path) -> None:
    write(tmp_path, "PRG-PO.md", "## Wie\n")
    with pytest.raises(PersonaError, match="front matter"):
        load_personas(tmp_path)
