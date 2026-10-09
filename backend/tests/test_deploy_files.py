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
