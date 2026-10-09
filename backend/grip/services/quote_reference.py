"""The reference of a quote: what a person says on the phone and writes in a mail.

A reference looks like "DG-2026-0007": a prefix that says which organisation
issued it, the year of issue, and a number that counts up per year. A number
is given out once and never again, also when the quote it went to is later
replaced: a new version of a quote is a new quote with its own reference.

The URI of a quote stays its identifier for machines. A reference is for
people, and it is part of the frozen content of the quote, so it is covered
by the hash and stands on the signed document.
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.services import instance_settings
from grip.services.errors import DomainValidationError

_NOT_ALLOWED = re.compile(r"[^A-Z0-9]+")
MAX_PREFIX = 10


def reference_prefix(settings: Settings | None = None) -> str:
    """The prefix of this instance: the setting, or else from the instance key."""
    settings = settings or get_settings()
    raw = settings.QUOTE_REFERENCE_PREFIX.strip() or settings.INSTANCE_KEY
    prefix = _NOT_ALLOWED.sub("", raw.upper())[:MAX_PREFIX]
    return prefix or "OFF"


def _prefix_check(value: object) -> str:
    if not isinstance(value, str):
        raise DomainValidationError("Het voorvoegsel is tekst.")
    cleaned = value.strip().upper()
    if cleaned and (_NOT_ALLOWED.search(cleaned) or len(cleaned) > MAX_PREFIX):
        raise DomainValidationError(
            f"Het voorvoegsel bestaat uit hooguit {MAX_PREFIX} letters en cijfers."
        )
    return cleaned


# The beheerder sets the prefix on the screen; the environment variable is
# the value an installation starts with.
PREFIX = instance_settings.declare(
    "quote.reference_prefix",
    reference_prefix(),
    _prefix_check,
    "Het voorvoegsel van het kenmerk van een offerte, zoals DG in DG-2026-0007. "
    "Leeg volgt de waarde waarmee de omgeving is ingericht.",
)


async def current_prefix(session: AsyncSession) -> str:
    """The prefix new references get: set on the screen, or else the default."""
    chosen = str(await instance_settings.get(session, PREFIX.key) or "")
    return chosen or reference_prefix()


def format_reference(prefix: str, year: int, number: int) -> str:
    return f"{prefix}-{year}-{number:04d}"


async def next_reference(session: AsyncSession, year: int) -> str:
    """Take the next reference of a year, inside the current transaction.

    One statement adds one to the counter of the year and returns it. Two
    transactions that issue at the same moment wait for each other on that
    row, so they cannot get the same number. When the transaction rolls
    back, the number goes back with it; nothing was issued under it.
    """
    result = await session.execute(
        text(
            "INSERT INTO quote_reference_counter (year, last_number) "
            "VALUES (:year, 1) "
            "ON CONFLICT (year) DO UPDATE "
            "SET last_number = quote_reference_counter.last_number + 1 "
            "RETURNING last_number"
        ),
        {"year": year},
    )
    number = int(result.scalar_one())
    return format_reference(await current_prefix(session), year, number)


async def upcoming_reference(session: AsyncSession, year: int) -> str:
    """The reference the next quote of the year would get. Takes nothing:
    for showing on the settings page what the prefix leads to."""
    result = await session.execute(
        text("SELECT last_number FROM quote_reference_counter WHERE year = :year"),
        {"year": year},
    )
    last = int(result.scalar_one_or_none() or 0)
    return format_reference(await current_prefix(session), year, last + 1)


def file_stem(reference: str | None, fallback: str) -> str:
    """A reference as part of a file name; the fallback when there is none."""
    cleaned = re.sub(r"[^A-Za-z0-9-]+", "-", reference or "").strip("-")
    return cleaned or fallback
