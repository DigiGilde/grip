"""Every response field of this slice has exactly one data class."""

import pytest
from pydantic import BaseModel

from grip.access import unclassified_fields
from grip.schema import billing, month_close, quotes, signing


def _response_schemas() -> list[type[BaseModel]]:
    found = []
    for module in (quotes, signing, month_close, billing):
        for name, value in vars(module).items():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
                and not name.endswith("In")
            ):
                found.append(value)
    return found


def test_there_are_schemas_to_check():
    assert len(_response_schemas()) >= 20


@pytest.mark.parametrize("schema", _response_schemas(), ids=lambda s: s.__name__)
def test_no_unclassified_fields(schema):
    assert unclassified_fields(schema) == []
