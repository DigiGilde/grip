"""Which factuurverzoek replaces which: the lookup, without a database."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from grip.services.billing_deliveries import replacements

FEB, MAR = date(2026, 2, 1), date(2026, 3, 1)
T0 = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)


@dataclass
class Export:
    month: date
    month_close_id: UUID
    delivery_id: UUID | None
    total_cents: int
    kind: str = "original"
    created_at: datetime = T0


def later(days: int) -> datetime:
    return T0 + timedelta(days=days)


def test_a_first_delivery_replaces_nothing() -> None:
    first = uuid4()
    exports = [Export(FEB, uuid4(), first, 100), Export(MAR, uuid4(), first, 200)]
    assert replacements(exports) == []


def test_a_month_delivered_again_replaces_the_request_before_it() -> None:
    first, second = uuid4(), uuid4()
    exports = [
        Export(FEB, uuid4(), first, 3_290_000),
        Export(MAR, uuid4(), first, 3_000_000),
        Export(FEB, uuid4(), second, 2_965_000, created_at=later(5)),
    ]
    [found] = replacements(exports)
    assert (found.month, found.old_delivery_id, found.new_delivery_id) == (
        FEB,
        first,
        second,
    )
    assert (found.old_cents, found.new_cents) == (3_290_000, 2_965_000)
    assert found.difference_cents == -325_000


def test_each_request_replaces_only_the_one_before_it() -> None:
    first, second, third = uuid4(), uuid4(), uuid4()
    exports = [
        Export(FEB, uuid4(), first, 100),
        Export(FEB, uuid4(), second, 90, created_at=later(1)),
        Export(FEB, uuid4(), third, 95, created_at=later(2)),
    ]
    found = replacements(exports)
    assert [(r.old_delivery_id, r.new_delivery_id) for r in found] == [
        (first, second),
        (second, third),
    ]
    assert [r.difference_cents for r in found] == [-10, 5]


def test_a_naverrekening_in_another_request_is_replaced_with_its_month() -> None:
    """March went out in full, then a difference travelled with the next
    quarter; delivered again, the new amount replaces both."""
    first, quarter_two, again = uuid4(), uuid4(), uuid4()
    close = uuid4()
    exports = [
        Export(MAR, close, first, 1_000),
        Export(MAR, close, quarter_two, -200, kind="correction", created_at=later(90)),
        Export(MAR, uuid4(), again, 700, created_at=later(120)),
    ]
    found = replacements(exports)
    assert {r.old_delivery_id: r.old_cents for r in found} == {
        first: 1_000,
        quarter_two: -200,
    }
    assert {r.new_delivery_id for r in found} == {again}
    # The difference is against everything stated for the month before.
    assert {r.difference_cents for r in found} == {-100}


def test_a_naverrekening_on_the_delivery_in_force_replaces_nothing() -> None:
    first, second = uuid4(), uuid4()
    close = uuid4()
    exports = [
        Export(MAR, close, first, 1_000),
        Export(MAR, close, second, -200, kind="correction", created_at=later(30)),
    ]
    assert replacements(exports) == []


def test_the_close_in_force_settles_the_order_at_the_same_moment() -> None:
    first, second = uuid4(), uuid4()
    old_close, new_close = uuid4(), uuid4()
    exports = [
        Export(FEB, new_close, second, 90),
        Export(FEB, old_close, first, 100),
    ]
    [found] = replacements(exports, {FEB: new_close})
    assert (found.old_delivery_id, found.new_delivery_id) == (first, second)


def test_an_export_that_was_never_delivered_is_left_out() -> None:
    exports = [
        Export(FEB, uuid4(), None, 100),
        Export(FEB, uuid4(), uuid4(), 90, created_at=later(1)),
    ]
    assert replacements(exports) == []
