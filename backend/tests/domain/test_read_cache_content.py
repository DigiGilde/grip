"""Remembering by content: the same inputs give the kept value, other inputs
are computed, and a computation that is not pure is found out."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from grip.services import read_cache


@dataclass(frozen=True)
class _Line:
    id: str
    fte: Decimal
    start: date


@pytest.fixture(autouse=True)
def _empty():
    read_cache.clear()
    yield
    read_cache.clear()


def test_digest_is_the_same_for_the_same_content():
    one = read_cache.digest(
        [_Line("a", Decimal("0.5"), date(2026, 1, 1))], {"b": 2, "a": 1}
    )
    two = read_cache.digest(
        (_Line("a", Decimal("0.5"), date(2026, 1, 1)),), {"a": 1, "b": 2}
    )
    assert one == two


@pytest.mark.parametrize(
    "other",
    [
        _Line("a", Decimal("0.6"), date(2026, 1, 1)),
        _Line("a", Decimal("0.5"), date(2026, 1, 2)),
        _Line("b", Decimal("0.5"), date(2026, 1, 1)),
    ],
)
def test_digest_differs_when_a_value_differs(other):
    line = _Line("a", Decimal("0.5"), date(2026, 1, 1))
    assert read_cache.digest(line) != read_cache.digest(other)


def test_digest_tells_types_apart():
    @dataclass(frozen=True)
    class Other:
        id: str
        fte: Decimal
        start: date

    line = _Line("a", Decimal("0.5"), date(2026, 1, 1))
    assert read_cache.digest(line) != read_cache.digest(
        Other("a", Decimal("0.5"), date(2026, 1, 1))
    )


def test_by_content_computes_once_per_content(monkeypatch):
    monkeypatch.setenv("READ_CACHE", "on")
    calls = []

    def compute(value):
        def run():
            calls.append(value)
            return (value, value * 2)

        return run

    first = read_cache.by_content("test", read_cache.digest(1), compute(1))
    again = read_cache.by_content("test", read_cache.digest(1), compute(1))
    other = read_cache.by_content("test", read_cache.digest(2), compute(2))
    assert first is again
    assert other == (2, 4)
    assert calls == [1, 2]
    # Another read model with the same content is another value.
    read_cache.by_content("other", read_cache.digest(1), compute(1))
    assert calls == [1, 2, 1]


def test_off_always_computes(monkeypatch):
    monkeypatch.setenv("READ_CACHE", "off")
    calls = []

    def run():
        calls.append(1)
        return len(calls)

    assert read_cache.by_content("test", "x", run) == 1
    assert read_cache.by_content("test", "x", run) == 2


def test_verify_finds_a_computation_that_reads_more_than_it_says(monkeypatch):
    monkeypatch.setenv("READ_CACHE", "verify")
    outside = {"value": 1}

    def run():
        return (outside["value"],)

    read_cache.by_content("test", "same", run)
    outside["value"] = 2
    with pytest.raises(read_cache.StaleReadError):
        read_cache.by_content("test", "same", run)
