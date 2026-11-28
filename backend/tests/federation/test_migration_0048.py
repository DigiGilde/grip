"""Migration 0048 on an outbox that already holds final messages (ADR 0061).

A message that was final before the revision gets the reason its last answer
gives and starts set aside, so an upgrade opens no task for history that was
settled before. A message still pending is left alone.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from grip.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[2]

# status, last_status_code, last_error -> the reason it gets.
ROWS = {
    "refused_403": ("rejected", 403, "HTTP 403: niet bekend", "unknown_sender"),
    "refused_409": ("rejected", 409, "HTTP 409: bestaat al", "conflict"),
    "refused_422": ("rejected", 422, "HTTP 422: klopt niet", "invalid"),
    "gone": ("rejected", 410, "HTTP 410: weg", "gone"),
    "not_found": ("rejected", 404, "HTTP 404: onbekend", "not_found"),
    "timeout": ("dead", None, "ReadTimeout: timed out", "timeout"),
    "stale_code": ("dead", 500, "ConnectError: no route", "no_connection"),
    "receiver": ("dead", 503, "HTTP 503: later", "receiver_error"),
    "configuration": ("dead", None, "configuration: no outway", "configuration"),
    "teapot": ("dead", 418, "HTTP 418: thee", "other"),
}


def _alembic(env: dict[str, str], *args: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed command, own interpreter
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_final_messages_get_their_reason_and_start_set_aside():
    url = make_url(get_settings().DATABASE_URL)
    scratch = f"grip_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{scratch}"'))
    scratch_url = url.set(database=scratch)
    env = {
        **os.environ,
        "DEV_NO_AUTH": "1",
        "DATABASE_URL": scratch_url.render_as_string(hide_password=False),
    }
    engine = create_async_engine(scratch_url)
    try:
        _alembic(env, "upgrade", "0047_inbox_path_parameters")
        peer = uuid.uuid4()
        ids = {name: uuid.uuid4() for name in [*ROWS, "pending"]}
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO peer (id, peer_id, name, organisation_tooi_uri,"
                    " base_uri, role) VALUES (:id, '00000000000000000020',"
                    " 'Voorbeeldgilde', '', 'https://grip.gilde.example',"
                    " 'counterpart')"
                ),
                {"id": peer},
            )
            for name, (status, code, error, _reason) in ROWS.items():
                await conn.execute(
                    text(
                        "INSERT INTO federation_outbox (id, message_id, peer_id,"
                        " service, operation, method, path, payload, status,"
                        " attempts, next_attempt_at, last_status_code, last_error)"
                        " VALUES (:id, :id, :peer, 'grip-opdrachtverkeer',"
                        " 'sendQuote', 'POST', '/v1/offertes', '{}', :status, 3,"
                        " '2026-11-27T09:00:00Z', :code, :error)"
                    ),
                    {
                        "id": ids[name],
                        "peer": peer,
                        "status": status,
                        "code": code,
                        "error": error,
                    },
                )
            await conn.execute(
                text(
                    "INSERT INTO federation_outbox (id, message_id, peer_id, service,"
                    " operation, method, path, payload, status, attempts,"
                    " last_status_code, last_error) VALUES (:id, :id, :peer,"
                    " 'grip-opdrachtverkeer', 'sendQuote', 'POST', '/v1/offertes',"
                    " '{}', 'pending', 2, 503, 'HTTP 503: later')"
                ),
                {"id": ids["pending"], "peer": peer},
            )

        _alembic(env, "upgrade", "0048_outbox_retry_window")
        async with engine.connect() as conn:
            rows = {
                row.id: row
                for row in await conn.execute(
                    text(
                        "SELECT id, failure, failing_since, set_aside_at,"
                        " retry_until FROM federation_outbox"
                    )
                )
            }
        for name, (_status, _code, _error, reason) in ROWS.items():
            row = rows[ids[name]]
            assert row.failure == reason, name
            assert row.failing_since is not None and row.set_aside_at is not None
            assert row.retry_until is None
        pending = rows[ids["pending"]]
        assert (pending.failure, pending.failing_since, pending.set_aside_at) == (
            None,
            None,
            None,
        )

        _alembic(env, "downgrade", "0047_inbox_path_parameters")
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            )
        await admin.dispose()
