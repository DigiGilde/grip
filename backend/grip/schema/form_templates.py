"""Response schemas for form templates. All of it is beheer: master data."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

LISTS = in_class(DataClass.MASTER_DATA)


class FormTemplateOut(BaseModel):
    """A stored blank form, without its file contents."""

    id: Annotated[UUID, LISTS]
    name: Annotated[str, LISTS]
    file_name: Annotated[str, LISTS]
    is_active: Annotated[bool, LISTS]
    created_at: Annotated[datetime, LISTS]
    uploaded_by_name: Annotated[str | None, LISTS] = None
    mapped_fields: Annotated[int, LISTS]
    unverified_fields: Annotated[int, LISTS]


class FormFieldOut(BaseModel):
    """A field found in an uploaded form. Never its value."""

    name: Annotated[str, LISTS]
    type: Annotated[str, LISTS]
    states: Annotated[list[str], LISTS]
    has_value: Annotated[bool, LISTS]
    # What the chosen mapping puts in this field, if anything.
    source: Annotated[str | None, LISTS] = None
    label: Annotated[str | None, LISTS] = None


class FormInspectionOut(BaseModel):
    fields: Annotated[list[FormFieldOut], nested()]
    # The form is filled in. It holds names and cannot be a template as is.
    has_values: Annotated[bool, LISTS]
    # Fields of the mapping that the form does not have.
    missing_fields: Annotated[list[str], LISTS]
    # Why the form cannot be used with this mapping, if it cannot.
    problem: Annotated[str | None, LISTS] = None


class BundledMappingOut(BaseModel):
    name: Annotated[str, LISTS]
    title: Annotated[str, LISTS]
    description: Annotated[str | None, LISTS] = None
    mapping: Annotated[dict[str, Any], LISTS]
