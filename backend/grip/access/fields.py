"""Data classes on the fields of response schemas.

Every field of a response schema is marked with exactly one data class::

    class AllocationOut(BaseModel):
        person_name: Annotated[str, in_class(DataClass.STAFFING_ROSTER)]
        fte_pct: Annotated[Decimal, in_class(DataClass.STAFFING)]
        amount_cents: Annotated[int, in_class(DataClass.PERSON_RATE)]

``build_response`` then produces the response with the fields of classes the
subject may not see left out. They are absent, not null: a client cannot tell
a hidden value from a field that does not exist for it.

A field that only holds other schemas (a list of lines, a nested object) is
marked ``nested()``: it has no class of its own and its content is filtered
field by field.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, get_args

from pydantic import BaseModel

from grip.access.types import DataClass


@dataclass(frozen=True)
class FieldClass:
    """Annotated metadata: the data class of a field."""

    data_class: DataClass


@dataclass(frozen=True)
class NestedFields:
    """Annotated metadata: the field holds schemas that are filtered themselves."""


def in_class(data_class: DataClass) -> FieldClass:
    return FieldClass(data_class)


def nested() -> NestedFields:
    return NestedFields()


class UnclassifiedFieldError(TypeError):
    """A schema has a field without a data class, or with more than one."""


def _markers(model: type[BaseModel], name: str) -> list[FieldClass | NestedFields]:
    return [
        m
        for m in model.model_fields[name].metadata
        if isinstance(m, FieldClass | NestedFields)
    ]


def _nested_models(annotation: Any) -> list[type[BaseModel]]:
    """Every pydantic model reachable through the type arguments of an annotation."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for arg in get_args(annotation):
        found.extend(_nested_models(arg))
    return found


def field_classes(model: type[BaseModel]) -> dict[str, DataClass | None]:
    """The data class per field; ``None`` for a ``nested()`` field.

    Raises ``UnclassifiedFieldError`` for a field that is not marked.
    """
    problems = unclassified_fields(model, recurse=False)
    if problems:
        raise UnclassifiedFieldError(
            f"{model.__name__}: fields without exactly one data class: {problems}"
        )
    result: dict[str, DataClass | None] = {}
    for name in model.model_fields:
        marker = _markers(model, name)[0]
        result[name] = marker.data_class if isinstance(marker, FieldClass) else None
    return result


def unclassified_fields(model: type[BaseModel], *, recurse: bool = True) -> list[str]:
    """Fields that break the rule "exactly one data class per field".

    Returns dotted paths, empty when the schema is fine. Problems are: no
    marker, more than one marker, ``nested()`` on a field that holds no
    schema, and a class marker on a field that does hold one.
    """
    return _unclassified(model, recurse, prefix="", seen=set())


def _unclassified(
    model: type[BaseModel], recurse: bool, prefix: str, seen: set[type[BaseModel]]
) -> list[str]:
    if model in seen:
        return []
    seen.add(model)
    problems: list[str] = []
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        markers = _markers(model, name)
        children = _nested_models(info.annotation)
        if len(markers) != 1:
            problems.append(path)
        elif isinstance(markers[0], NestedFields) != bool(children):
            problems.append(path)
        if recurse:
            for child in children:
                problems.extend(_unclassified(child, recurse, f"{path}.", seen))
    return problems


def schema_classes(model: type[BaseModel]) -> frozenset[DataClass]:
    """Every data class used in the schema, nested schemas included."""
    return frozenset(_schema_classes(model, set()))


def _schema_classes(
    model: type[BaseModel], seen: set[type[BaseModel]]
) -> set[DataClass]:
    if model in seen:
        return set()
    seen.add(model)
    classes: set[DataClass] = set()
    for name, info in model.model_fields.items():
        for marker in _markers(model, name):
            if isinstance(marker, FieldClass):
                classes.add(marker.data_class)
        for child in _nested_models(info.annotation):
            classes |= _schema_classes(child, seen)
    return classes


def build_response(value: BaseModel, permitted: Iterable[DataClass]) -> dict[str, Any]:
    """The JSON-ready response with only the fields of permitted classes.

    ``permitted`` is taken literally: pass what ``permitted_classes`` returned
    for the classes in ``schema_classes(type(value))``.
    """
    allowed = frozenset(permitted)
    return _filter_model(value, value.model_dump(mode="json"), allowed)


def _filter_model(
    value: BaseModel, dumped: Mapping[str, Any], allowed: frozenset[DataClass]
) -> dict[str, Any]:
    model = type(value)
    classes = field_classes(model)
    result: dict[str, Any] = {}
    for name, data_class in classes.items():
        if name not in dumped:
            continue
        if data_class is None:
            result[name] = _filter_value(getattr(value, name), dumped[name], allowed)
        elif data_class in allowed:
            result[name] = dumped[name]
    return result


def _filter_value(value: Any, dumped: Any, allowed: frozenset[DataClass]) -> Any:
    if isinstance(value, BaseModel):
        return _filter_model(value, dumped, allowed)
    if isinstance(value, list | tuple):
        return [
            _filter_value(v, d, allowed) for v, d in zip(value, dumped, strict=True)
        ]
    if isinstance(value, Mapping):
        return {
            dumped_key: _filter_value(v, dumped[dumped_key], allowed)
            for (_k, v), dumped_key in zip(value.items(), dumped, strict=True)
        }
    # ``None`` in an optional nested field, or a plain value where a schema
    # was expected: nothing to filter into, so nothing is passed on.
    return None
