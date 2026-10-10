"""The files an image is built from agree with each other."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_the_backend_image_takes_the_huisstijl_from_the_frontends_version() -> None:
    """The Rijkslint and the typeface in the backend image come from the same
    version of the design system as the screens."""
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
    pinned = re.search(r"ARG NLDD_DESIGN_SYSTEM_VERSION=(\S+)", dockerfile)
    assert pinned is not None
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    used = lock["packages"]["node_modules/@nldd/design-system"]["version"]
    assert pinned.group(1) == used


def test_the_single_container_role_runs_the_worker() -> None:
    """Tasks, mail and notifications need the worker, also without federation."""
    entrypoint = (ROOT / "backend" / "entrypoint.sh").read_text()
    role = entrypoint[entrypoint.index("    all)") :]
    assert "python -m grip.worker" in role
    assert 'is_on "${WORKER_ENABLED:-1}"' in role


def test_the_frontend_container_starts_without_a_backend_address() -> None:
    """With the platform routing /api/ itself there is no upstream to resolve."""
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
    assert 'BACKEND_URL=""' in dockerfile
    template = (ROOT / "frontend" / "nginx.conf.template").read_text()
    assert "proxy_pass" not in template
    assert "include /tmp/grip-api.conf;" in template
    assert "location = /sw.js" in template


@pytest.mark.parametrize(
    "module", ["grip.core.app", "grip.worker", "grip.federation.app", "grip.dev.seed"]
)
def test_every_process_of_the_image_can_be_imported_on_its_own(module: str) -> None:
    """Each role of the entrypoint starts in a fresh interpreter. The order of
    imports differs per role, so a circular import can break one and not
    another."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        env={**os.environ, "DEV_NO_AUTH": "1"},
        check=False,
    )
    assert result.returncode == 0, result.stderr[-600:]


def test_the_ontwikkelportaal_image_checks_the_site_and_allows_search() -> None:
    """The image builds the site from the lockfile, fails on a broken link, and
    its policy lets Pagefind compile without allowing inline script."""
    dockerfile = (ROOT / "ontwikkelportaal" / "Dockerfile").read_text()
    assert "npm ci" in dockerfile
    assert "npm run build && npm run check" in dockerfile
    package = json.loads((ROOT / "ontwikkelportaal" / "package.json").read_text())
    lock = json.loads((ROOT / "ontwikkelportaal" / "package-lock.json").read_text())
    for name, version in package["dependencies"].items():
        assert version == lock["packages"][f"node_modules/{name}"]["version"], name
    screens = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    nldd = "node_modules/@nldd/design-system"
    assert lock["packages"][nldd]["version"] == screens["packages"][nldd]["version"]
    template = (ROOT / "ontwikkelportaal" / "nginx.conf.template").read_text()
    script_src = re.search(r"script-src ([^;]*);", template)
    assert script_src is not None
    assert script_src.group(1).split() == ["'self'", "'wasm-unsafe-eval'"]


def test_the_root_build_context_holds_only_the_portal_and_docs() -> None:
    """The ontwikkelportaal is built from the repository root; nothing else of
    the repository, and no local secret, may reach that context."""
    lines = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    allowlist = lines[lines.index("*") :]
    assert [line for line in allowlist if line.startswith("!")] == [
        "!docs",
        "!ontwikkelportaal",
    ]
    assert "**/.env" in allowlist
    assert "ontwikkelportaal/node_modules" in allowlist
