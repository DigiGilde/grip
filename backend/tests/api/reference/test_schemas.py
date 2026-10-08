"""Every response field of this slice has exactly one data class."""

import pytest

from grip.access import unclassified_fields
from grip.schema.costs import BudgetLineOptionOut, CostItemOut
from grip.schema.kpi import KpiOut
from grip.schema.people import PersonOut
from grip.schema.rates import RateCardListOut, RateCardOut


@pytest.mark.parametrize(
    "schema",
    [RateCardListOut, RateCardOut, PersonOut, KpiOut, CostItemOut, BudgetLineOptionOut],
)
def test_no_unclassified_fields(schema):
    assert unclassified_fields(schema) == []
