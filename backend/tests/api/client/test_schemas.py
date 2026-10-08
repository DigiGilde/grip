"""Every field of the client-side response schemas has exactly one data class."""

import pytest

from grip.access import unclassified_fields
from grip.schema import client_side, nodes

SCHEMAS = [
    client_side.ClientOptionsOut,
    client_side.ClientAssignmentListOut,
    client_side.ClientAssignmentDetailOut,
    client_side.ReceivedRequestListOut,
    client_side.ReceivedQuoteListOut,
    client_side.ReceivedQuoteDetailOut,
    client_side.ProgressOut,
    client_side.BudgetUsageOut,
    client_side.FinalReportOut,
    nodes.CorporaOut,
    nodes.NodeSearchOut,
    nodes.NodeLookupOut,
    nodes.ContextOut,
]


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema.__name__)
def test_no_field_without_a_data_class(schema):
    assert unclassified_fields(schema) == []
