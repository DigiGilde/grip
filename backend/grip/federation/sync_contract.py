"""Refresh the vendored contract from a checkout of the contract repo.

Usage (from ``backend/``)::

    uv run python -m grip.federation.sync_contract <path-to-checkout>

Copies the two OpenAPI documents, the schemas, the core vocabulary and the
examples, and records which commit and version they came from. The vendored
copy is the only place in grip where these shapes are defined; nothing is
edited by hand after a sync.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

CONTRACT_DIR = Path(__file__).parent / "contract"
SOURCE_REPO = "https://github.com/DigiGilde/grip-koppelvlakken"

# Paths in the contract repo, relative to its root.
_FILES = (
    "opdrachtverkeer/v1/openapi.yaml",
    "corpus-context/v1/openapi.yaml",
    "vocabulaire/kern.json",
)
_DIRS = ("schemas", "examples/valid", "examples/invalid")


def _git(checkout: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sync(checkout: Path) -> dict:
    """Copy the contract from ``checkout`` and return the version record."""
    for relative in (*_FILES, *_DIRS):
        if not (checkout / relative).exists():
            raise SystemExit(f"Not a contract checkout: {relative} is missing")

    for relative in ("opdrachtverkeer", "corpus-context", "vocabulaire", *_DIRS):
        target = CONTRACT_DIR / relative
        if target.exists():
            shutil.rmtree(target)

    for relative in _FILES:
        target = CONTRACT_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkout / relative, target)
    for relative in _DIRS:
        target = CONTRACT_DIR / relative
        target.mkdir(parents=True, exist_ok=True)
        for source in sorted((checkout / relative).glob("*.json")):
            shutil.copyfile(source, target / source.name)

    versions = {
        service: yaml.safe_load((checkout / path).read_text())["info"]["version"]
        for service, path in (
            ("grip-opdrachtverkeer", _FILES[0]),
            ("corpus-context", _FILES[1]),
        )
    }
    paths = [*_FILES, *_DIRS]
    record = {
        "source": SOURCE_REPO,
        "commit": _git(checkout, "rev-parse", "HEAD"),
        # True when the copied files differed from the commit above.
        "modified": bool(_git(checkout, "status", "--porcelain", "--", *paths)),
        "versions": versions,
    }
    (CONTRACT_DIR / "CONTRACT_VERSION.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    return record


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    record = sync(Path(sys.argv[1]).expanduser().resolve())
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
