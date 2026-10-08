"""Every response field of this slice has exactly one data class."""

import pytest

from grip.access import unclassified_fields
from grip.schema import allocations, assignments, budget_lines, organisations, overview

_SCHEMAS = [
    organisations.OrganisationOut,
    assignments.AssignmentSummaryOut,
    assignments.AssignmentListOut,
    assignments.AssignmentDetailOut,
    assignments.RoleHolderOut,
    assignments.AssignmentPermissionsOut,
    assignments.PersonOptionOut,
    assignments.PersonOptionsOut,
    budget_lines.BudgetLineOut,
    budget_lines.BudgetOut,
    allocations.AllocationOut,
    allocations.AllocationListOut,
    allocations.PersonChoiceOut,
    allocations.LineChoiceOut,
    allocations.AllocationOptionsOut,
    overview.TotalsOut,
    overview.OverviewRowOut,
    overview.OverviewOut,
    overview.TeamMemberOut,
    overview.LineCostOut,
    overview.LineOverviewOut,
    overview.AssignmentOverviewOut,
]


@pytest.mark.parametrize("schema", _SCHEMAS, ids=lambda s: s.__name__)
def test_no_unclassified_fields(schema):
    assert unclassified_fields(schema) == []
