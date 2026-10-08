"""Data classes on response fields: marking, checking and filtering."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from grip.access import (
    Action,
    DataClass,
    Resource,
    UnclassifiedFieldError,
    build_response,
    field_classes,
    in_class,
    nested,
    permitted_classes,
    schema_classes,
    unclassified_fields,
)

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)


class AllocationOut(BaseModel):
    person_id: Annotated[UUID, in_class(DataClass.STAFFING_ROSTER)]
    person_name: Annotated[str, in_class(DataClass.STAFFING_ROSTER)]
    fte_pct: Annotated[Decimal, in_class(DataClass.STAFFING)]
    start_date: Annotated[date, in_class(DataClass.STAFFING)]
    rate_category: Annotated[str, in_class(DataClass.PERSON_RATE)]
    amount_cents: Annotated[int, in_class(DataClass.PERSON_RATE)]
    margin_cents: Annotated[int | None, in_class(DataClass.PERSON_COST)] = None
    category_differs: Annotated[bool, in_class(DataClass.RATE_MISMATCH_SIGNAL)] = False


class TotalsOut(BaseModel):
    budgeted_cents: Annotated[int, B]
    used_cents: Annotated[int, B]


class AssignmentOut(BaseModel):
    id: Annotated[UUID, A]
    name: Annotated[str, A]
    totals: Annotated[TotalsOut | None, nested()] = None
    team: Annotated[list[AllocationOut], nested()] = []
    by_role: Annotated[dict[str, AllocationOut], nested()] = {}


def _assignment() -> AssignmentOut:
    line = AllocationOut(
        person_id=uuid4(),
        person_name="Persoon Een",
        fte_pct=Decimal("80"),
        start_date=date(2026, 1, 1),
        rate_category="D",
        amount_cents=1_440_000,
        margin_cents=120_000,
        category_differs=True,
    )
    return AssignmentOut(
        id=uuid4(),
        name="Opdracht Alfa",
        totals=TotalsOut(budgeted_cents=17_280_000, used_cents=1_440_000),
        team=[line],
        by_role={"developer": line},
    )


def test_field_classes() -> None:
    assert field_classes(TotalsOut) == {
        "budgeted_cents": DataClass.ASSIGNMENT_FINANCIAL,
        "used_cents": DataClass.ASSIGNMENT_FINANCIAL,
    }
    classes = field_classes(AssignmentOut)
    assert classes["name"] is DataClass.ASSIGNMENT_BASIC
    assert classes["team"] is None and classes["totals"] is None


def test_schema_classes_includes_nested_schemas() -> None:
    assert schema_classes(AssignmentOut) == {
        DataClass.ASSIGNMENT_BASIC,
        DataClass.ASSIGNMENT_FINANCIAL,
        DataClass.STAFFING_ROSTER,
        DataClass.STAFFING,
        DataClass.PERSON_RATE,
        DataClass.PERSON_COST,
        DataClass.RATE_MISMATCH_SIGNAL,
    }


def test_a_fully_marked_schema_has_no_unclassified_fields() -> None:
    assert unclassified_fields(AssignmentOut) == []


def test_unclassified_fields_are_found_also_in_nested_schemas() -> None:
    class Leaky(BaseModel):
        marked: Annotated[int, B]
        salary_scale: int

    class Outer(BaseModel):
        name: Annotated[str, A]
        lines: Annotated[list[Leaky], nested()]
        maybe: Annotated[Leaky | None, nested()] = None
        note: str = ""

    assert unclassified_fields(Leaky) == ["salary_scale"]
    assert unclassified_fields(Outer) == ["lines.salary_scale", "note"]
    assert unclassified_fields(Outer, recurse=False) == ["note"]
    with pytest.raises(UnclassifiedFieldError, match="salary_scale"):
        field_classes(Leaky)


def test_wrong_use_of_markers_is_reported() -> None:
    class Inner(BaseModel):
        value: Annotated[int, B]

    class Twice(BaseModel):
        value: Annotated[int, A, B]

    class NestedOnPlainValue(BaseModel):
        value: Annotated[int, nested()]

    class ClassOnSchema(BaseModel):
        inner: Annotated[Inner, B]

    class NoMarkerOnSchema(BaseModel):
        inner: Inner

    assert unclassified_fields(Twice) == ["value"]
    assert unclassified_fields(NestedOnPlainValue) == ["value"]
    assert unclassified_fields(ClassOnSchema) == ["inner"]
    assert unclassified_fields(NoMarkerOnSchema) == ["inner"]


def test_recursive_schemas_terminate() -> None:
    class Node(BaseModel):
        name: Annotated[str, A]
        children: Annotated[list["Node"], nested()] = []

    Node.model_rebuild()
    assert unclassified_fields(Node) == []
    assert schema_classes(Node) == {DataClass.ASSIGNMENT_BASIC}
    tree = Node(name="root", children=[Node(name="leaf")])
    assert build_response(tree, {DataClass.ASSIGNMENT_BASIC}) == {
        "name": "root",
        "children": [{"name": "leaf", "children": []}],
    }
    assert build_response(tree, set()) == {"children": [{"children": []}]}


def test_build_response_leaves_out_fields_instead_of_nulling_them() -> None:
    value = _assignment()
    out = build_response(value, {DataClass.ASSIGNMENT_BASIC, DataClass.STAFFING_ROSTER})
    assert out == {
        "id": str(value.id),
        "name": "Opdracht Alfa",
        "totals": {},
        "team": [
            {"person_id": str(value.team[0].person_id), "person_name": "Persoon Een"}
        ],
        "by_role": {
            "developer": {
                "person_id": str(value.team[0].person_id),
                "person_name": "Persoon Een",
            }
        },
    }
    assert "amount_cents" not in out["team"][0]
    assert "margin_cents" not in out["team"][0]


def test_build_response_with_everything_equals_the_plain_dump() -> None:
    value = _assignment()
    assert build_response(value, set(DataClass)) == value.model_dump(mode="json")


def test_build_response_with_nothing_holds_no_values() -> None:
    assert build_response(_assignment(), set()) == {
        "totals": {},
        "team": [{}],
        "by_role": {"developer": {}},
    }


def test_build_response_keeps_an_absent_nested_object_empty() -> None:
    value = AssignmentOut(id=uuid4(), name="Opdracht Beta")
    out = build_response(value, set(DataClass))
    assert out["totals"] is None and out["team"] == [] and out["by_role"] == {}


def test_build_response_takes_the_permitted_set_literally() -> None:
    """Implication is the decider's business, not the filter's."""
    out = build_response(_assignment(), {DataClass.STAFFING})
    assert set(out["team"][0]) == {"fte_pct", "start_date"}


def test_build_response_refuses_an_unmarked_schema() -> None:
    class Unmarked(BaseModel):
        secret: int

    with pytest.raises(UnclassifiedFieldError):
        build_response(Unmarked(secret=1), set(DataClass))


@pytest.mark.parametrize(
    ("subject", "visible"),
    [
        (
            "planner",
            {"person_id", "person_name", "fte_pct", "start_date", "category_differs"},
        ),
        ("colleague", {"person_id", "person_name"}),
        ("lezer", set()),
        ("peer_client", set()),
        ("peer_parent", set()),
        (
            "owner",
            {
                "person_id",
                "person_name",
                "fte_pct",
                "start_date",
                "rate_category",
                "amount_cents",
                "margin_cents",
                "category_differs",
            },
        ),
    ],
)
async def test_decision_and_filter_together(
    world, subject: str, visible: set[str]
) -> None:
    """End to end: what the decider permits is exactly what the response holds."""
    line = _assignment().team[0]
    resource = Resource.allocation(world.own, world.member)
    permitted = await permitted_classes(
        world.decider,
        world.subject(subject),
        resource,
        schema_classes(AllocationOut),
        world.context,
        Action.READ,
    )
    assert set(build_response(line, permitted)) == visible
