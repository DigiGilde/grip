"""Nothing outside the chronicle writes the read models.

A look at the source: no constructor of the nine models, and no Core update,
insert or delete of them, outside ``grip/chronicle``. Names are followed through
their imports, so ``calc.BudgetLine`` or an enum of the access layer that happens
to share a name is not the model.
"""

from __future__ import annotations

import ast
from pathlib import Path

import grip
from grip.chronicle.writer import MODELS

ROOT = Path(grip.__file__).parent
_MODEL_NAMES = frozenset(model.__name__ for model in MODELS.values())
_MODELS_PACKAGE = "grip.models"
_CORE_WRITES = frozenset(
    {
        "sqlalchemy.update",
        "sqlalchemy.insert",
        "sqlalchemy.delete",
        "sqlalchemy.sql.update",
        "sqlalchemy.sql.insert",
        "sqlalchemy.sql.delete",
        "sqlalchemy.dialects.postgresql.insert",
    }
)
# Fixes a name typed long ago across every line that carries it, and cannot
# say which case each line belongs to. Run by hand.
_ALLOWED = frozenset({"dev/fix_role_po.py"})


def _module_of(path: Path) -> str:
    parts = list(path.relative_to(ROOT.parent).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(tree: ast.Module, module: str, is_package: bool) -> dict[str, str]:
    """What each local name stands for, as a dotted path."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    names[top] = top
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parents = module.split(".")
                keep = len(parents) - node.level + (1 if is_package else 0)
                prefix = ".".join(parents[:keep])
                base = f"{prefix}.{base}" if base else prefix
            for alias in node.names:
                names[alias.asname or alias.name] = f"{base}.{alias.name}"
    return names


def _dotted(node: ast.expr, names: dict[str, str]) -> str | None:
    """The dotted path an expression stands for, through the imports."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value, names)
        return f"{base}.{node.attr}" if base else None
    return None


def _is_model(path: str | None) -> bool:
    if path is None or not path.startswith(f"{_MODELS_PACKAGE}."):
        return False
    return path.rsplit(".", 1)[-1] in _MODEL_NAMES


def findings(source: str, *, module: str, is_package: bool = False) -> list[str]:
    """Where this source writes a read model around the chronicle."""
    tree = ast.parse(source)
    names = _imports(tree, module, is_package)
    if module.startswith(_MODELS_PACKAGE):
        # The classes a models module defines itself.
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in _MODEL_NAMES:
                names[node.name] = f"{module}.{node.name}"
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = _dotted(node.func, names)
        if _is_model(called):
            found.append(f"{module}:{node.lineno}: new {called}")
        elif called in _CORE_WRITES and node.args:
            target = _dotted(node.args[0], names)
            if _is_model(target):
                found.append(f"{module}:{node.lineno}: {called} of {target}")
    return found


def _sources() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.py")
        if "migrations" not in path.parts
        and "chronicle" != path.relative_to(ROOT).parts[0]
        and path.relative_to(ROOT).as_posix() not in _ALLOWED
    ]


def test_there_are_nine_read_models():
    assert len(_MODEL_NAMES) == 9


def test_nothing_writes_a_read_model_around_the_chronicle():
    sources = _sources()
    assert len(sources) > 100
    assert ROOT / "services" / "quotes.py" in sources
    assert ROOT / "chronicle" / "writer.py" not in sources
    assert ROOT / "dev" / "fix_role_po.py" not in sources
    found = [
        item
        for path in sources
        for item in findings(
            path.read_text(encoding="utf-8"),
            module=_module_of(path),
            is_package=path.name == "__init__.py",
        )
    ]
    assert found == []


def test_the_known_exception_is_what_the_check_would_catch():
    source = (ROOT / "dev" / "fix_role_po.py").read_text(encoding="utf-8")
    assert findings(source, module="grip.dev.fix_role_po")


def test_it_sees_a_constructor_through_every_kind_of_import():
    for source in (
        "from grip.models.quote import Quote\nQuote(id=1)",
        "from grip.models.quote import Quote as Q\nQ(id=1)",
        "import grip.models.quote\ngrip.models.quote.Quote(id=1)",
        "import grip.models.quote as m\nm.QuoteOffer(id=1)",
        "from grip.models import assignment\nassignment.BudgetLine(id=1)",
        "from grip.models import quote as q\nq.QuoteRejection(id=1)",
        "from ..models.assignment import AssignmentRole\nAssignmentRole(id=1)",
    ):
        assert findings(source, module="grip.services.voorbeeld"), source


def test_it_sees_a_core_write():
    for source in (
        "from sqlalchemy import update\nfrom grip.models.quote import Quote\n"
        "update(Quote).values(status='x')",
        "import sqlalchemy as sa\nfrom grip.models.assignment import Assignment\n"
        "sa.delete(Assignment)",
        "from sqlalchemy.dialects.postgresql import insert\n"
        "from grip.models.assignment import BudgetLine\ninsert(BudgetLine)",
    ):
        assert findings(source, module="grip.services.voorbeeld"), source


def test_it_is_not_fooled_by_a_name():
    for source in (
        "from grip import calc\ncalc.BudgetLine(id='1')",
        "from grip.calc import BudgetLine\nBudgetLine(id='1')",
        "from grip.access.types import ResourceKind\nResourceKind.QUOTE",
        "from grip.access import sql\nsql.Quote",
        "from sqlalchemy import select\nfrom grip.models.quote import Quote\n"
        "select(Quote)",
        "from sqlalchemy import update\nfrom grip.models.vacancy import Vacancy\n"
        "update(Vacancy)",
        "class Quote:\n    pass\nQuote()",
    ):
        assert findings(source, module="grip.services.voorbeeld") == [], source
