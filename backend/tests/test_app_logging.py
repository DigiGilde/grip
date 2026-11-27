"""The application's own log lines reach the container log."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from grip.core.app import configure_logging
from grip.core.database import engine


def test_info_lines_of_the_application_are_not_dropped():
    own = logging.getLogger("grip")
    before = own.level
    try:
        own.setLevel(logging.WARNING)
        configure_logging()

        assert logging.getLogger("grip.api.routes.auth").isEnabledFor(logging.INFO)
    finally:
        own.setLevel(before)


async def test_a_failed_statement_does_not_carry_its_values():
    with pytest.raises(DBAPIError) as failed:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT 1 / 0, CAST(:value AS text)"),
                {"value": "Voorbeeldnaam"},
            )
    await engine.dispose()

    assert "Voorbeeldnaam" not in str(failed.value)


def test_configuring_twice_adds_no_second_handler():
    own = logging.getLogger("grip")
    configure_logging()
    count = len(own.handlers)
    configure_logging()

    assert len(own.handlers) == count
