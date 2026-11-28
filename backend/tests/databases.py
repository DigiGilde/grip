"""A database of its own for every test process, copied from a template.

The template holds the migrations and nothing else. It is named after the
migration files, so it is built once and every later run with the same
migrations copies it (``CREATE DATABASE ... TEMPLATE``) instead of migrating.

Every process gets its own copy: each pytest-xdist worker, and the single
process of a run without xdist. The copies are named after the checkout and
the worker, so runs from other checkouts against the same server do not meet.
``DATABASE_URL`` names the server and the base name; the database it names is
not touched.

The user of ``DATABASE_URL`` needs the right to create databases.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import threading
from pathlib import Path

import asyncpg
from sqlalchemy.engine import URL, make_url

BACKEND = Path(__file__).resolve().parents[1]
BASE_URL_ENV = "GRIP_TEST_BASE_DATABASE_URL"
# One key for every template on the server: a build or removal of a template
# holds it exclusively, a copy holds it shared.
_TEMPLATE_LOCK = 0x67726970

_created: set[str] = set()


def configure(base_url: str) -> str:
    """Point ``DATABASE_URL`` at this process's database and return its URL.

    Call before ``grip.core.database`` is imported: it makes its engine at
    import.
    """
    base_url = os.environ.setdefault(BASE_URL_ENV, base_url)
    url = make_url(base_url).set(database=_own_name(make_url(base_url)))
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    return os.environ["DATABASE_URL"]


def prepare() -> None:
    """Create this process's database from the template, once per process."""
    ensure("")


def ensure(suffix: str) -> str:
    """The URL of this process's database, or of an extra one with ``suffix``.

    The database is a fresh copy of the template the first time this process
    asks for it.
    """
    base = make_url(os.environ[BASE_URL_ENV])
    name = _own_name(base) + (f"_{suffix}" if suffix else "")
    if name not in _created:
        _run(_copy(base, name))
        _created.add(name)
    return base.set(database=name).render_as_string(hide_password=False)


def _own_name(base: URL) -> str:
    checkout = hashlib.sha256(str(BACKEND).encode()).hexdigest()[:6]
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return f"{base.database}_{checkout}_{worker}"


def _template_name(base: URL) -> str:
    digest = hashlib.sha256()
    for path in sorted((BACKEND / "grip" / "migrations").rglob("*.py")):
        digest.update(path.relative_to(BACKEND).as_posix().encode())
        digest.update(path.read_bytes())
    return f"{base.database}_tpl_{digest.hexdigest()[:12]}"


def _run(coroutine) -> None:
    """Run outside the event loop of the test that may be running."""
    failure: list[BaseException] = []

    def target() -> None:
        try:
            asyncio.run(coroutine)
        except BaseException as exc:  # noqa: BLE001 - raised again below
            failure.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if failure:
        raise failure[0]


async def _admin(base: URL) -> asyncpg.Connection:
    url = base.set(drivername="postgresql", database="postgres")
    return await asyncpg.connect(url.render_as_string(hide_password=False))


async def _copy(base: URL, name: str) -> None:
    template = _template_name(base)
    conn = await _admin(base)
    try:
        while True:
            await conn.execute("SELECT pg_advisory_lock_shared($1)", _TEMPLATE_LOCK)
            try:
                if await _exists(conn, template):
                    await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
                    await conn.execute(
                        f'CREATE DATABASE "{name}" TEMPLATE "{template}"'
                    )
                    return
            finally:
                await conn.execute(
                    "SELECT pg_advisory_unlock_shared($1)", _TEMPLATE_LOCK
                )
            await _build(conn, base, template)
    finally:
        await conn.close()


async def _build(conn: asyncpg.Connection, base: URL, template: str) -> None:
    """Migrate a new template, unless another process did so meanwhile."""
    await conn.execute("SELECT pg_advisory_lock($1)", _TEMPLATE_LOCK)
    try:
        if await _exists(conn, template):
            return
        building = f"{template}_new"
        await conn.execute(f'DROP DATABASE IF EXISTS "{building}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{building}"')
        result = subprocess.run(  # noqa: S603 - fixed command, own interpreter
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env={
                **os.environ,
                "DATABASE_URL": base.set(database=building).render_as_string(
                    hide_password=False
                ),
            },
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"migrating the test template failed:\n{result.stderr}")
        await conn.execute(f'ALTER DATABASE "{building}" RENAME TO "{template}"')
        # Templates of earlier migrations are left from other runs.
        prefix = f"{base.database}_tpl_"
        for row in await conn.fetch(
            "SELECT datname FROM pg_database WHERE starts_with(datname, $1)", prefix
        ):
            if row["datname"] != template:
                await conn.execute(f'DROP DATABASE "{row["datname"]}" WITH (FORCE)')
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", _TEMPLATE_LOCK)


async def _exists(conn: asyncpg.Connection, name: str) -> bool:
    return bool(
        await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
    )
