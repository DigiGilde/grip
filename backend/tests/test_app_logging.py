"""The application's own log lines reach the container log."""

from __future__ import annotations

import logging

from grip.core.app import configure_logging


def test_info_lines_of_the_application_are_not_dropped():
    own = logging.getLogger("grip")
    before = own.level
    try:
        own.setLevel(logging.WARNING)
        configure_logging()

        assert logging.getLogger("grip.api.routes.auth").isEnabledFor(logging.INFO)
    finally:
        own.setLevel(before)


def test_configuring_twice_adds_no_second_handler():
    own = logging.getLogger("grip")
    configure_logging()
    count = len(own.handlers)
    configure_logging()

    assert len(own.handlers) == count
