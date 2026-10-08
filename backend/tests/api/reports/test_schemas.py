"""Every response field of the reports has exactly one data class."""

import inspect

import pytest
from pydantic import BaseModel

from grip.access import unclassified_fields
from grip.schema import reports

_SCHEMAS = [
    schema
    for _name, schema in inspect.getmembers(reports, inspect.isclass)
    if issubclass(schema, BaseModel) and schema.__module__ == reports.__name__
]


def test_the_module_has_schemas():
    assert len(_SCHEMAS) > 20


@pytest.mark.parametrize("schema", _SCHEMAS, ids=lambda s: s.__name__)
def test_no_unclassified_fields(schema):
    assert unclassified_fields(schema) == []
