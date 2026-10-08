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
field by field. Entries that keep nothing are dropped and a nested field
that keeps nothing is absent, so a reader cannot count what it may not see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
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

    Nested content is filtered so that nothing can be counted by a reader who
    may see none of it:

    - a ``nested()`` field is absent when no class of the schemas it holds is
      permitted, whether it holds something or not;
    - a nested object, list entry or mapping entry that keeps no field of its
      own (only empty containers, or nothing) is dropped;
    - a list or mapping whose entries were all dropped is absent, while one
      that was empty to begin with stays empty for a reader who may see its
      content.

    The top-level object is always returned, possibly empty. Decimals are
    written in one notation, see ``canonical_decimal``.
    """
    allowed = frozenset(permitted)
    result, _ = _filter_model(value, value.model_dump(mode="json"), allowed)
    return result


_ABSENT: Any = object()

_classes_cache: dict[type[BaseModel], frozenset[DataClass]] = {}


def _classes_of(model: type[BaseModel]) -> frozenset[DataClass]:
    if model not in _classes_cache:
        _classes_cache[model] = schema_classes(model)
    return _classes_cache[model]


def _filter_model(
    value: BaseModel, dumped: Mapping[str, Any], allowed: frozenset[DataClass]
) -> tuple[dict[str, Any], bool]:
    """The filtered object, and whether it holds anything of substance.

    Substance is a field with a permitted class, or a nested field that kept
    content. An object with only empty containers has none, so its parent
    drops it instead of showing that it exists.
    """
    model = type(value)
    classes = field_classes(model)
    result: dict[str, Any] = {}
    substance = False
    for name, data_class in classes.items():
        if name not in dumped:
            continue
        if data_class is None:
            children = _nested_models(model.model_fields[name].annotation)
            if not any(_classes_of(child) & allowed for child in children):
                continue
            filtered = _filter_value(getattr(value, name), dumped[name], allowed)
            if filtered is _ABSENT:
                continue
            result[name] = filtered
            if filtered:
                substance = True
        elif data_class in allowed:
            result[name] = _canonical(getattr(value, name), dumped[name])
            substance = True
    return result, substance


def canonical_decimal(value: Decimal) -> str:
    """A decimal as the API writes it: plain notation, no trailing zeros.

    The database returns a number with the scale of its column (``0.800``,
    ``30.00``) and a request echoes what was typed (``0.8``). One notation
    on the way out means the same number is always the same string.
    """
    if not value.is_finite():
        return str(value)
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _canonical(value: Any, dumped: Any) -> Any:
    """``dumped`` with every decimal of ``value`` in canonical notation."""
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, list | tuple) and isinstance(dumped, list):
        if len(value) == len(dumped):
            return [_canonical(v, d) for v, d in zip(value, dumped, strict=True)]
        return dumped
    if isinstance(value, Mapping) and isinstance(dumped, Mapping):
        if len(value) == len(dumped):
            return {
                key: _canonical(v, dumped[key])
                for (_k, v), key in zip(value.items(), dumped, strict=True)
            }
        return dumped
    return dumped


def _filter_value(value: Any, dumped: Any, allowed: frozenset[DataClass]) -> Any:
    if isinstance(value, BaseModel):
        filtered, substance = _filter_model(value, dumped, allowed)
        return filtered if substance else _ABSENT
    if isinstance(value, list | tuple):
        if not value:
            return []
        items = [
            item
            for v, d in zip(value, dumped, strict=True)
            if (item := _filter_value(v, d, allowed)) is not _ABSENT
        ]
        return items if items else _ABSENT
    if isinstance(value, Mapping):
        if not value:
            return {}
        entries = {
            dumped_key: item
            for (_k, v), dumped_key in zip(value.items(), dumped, strict=True)
            if (item := _filter_value(v, dumped[dumped_key], allowed)) is not _ABSENT
        }
        return entries if entries else _ABSENT
    # ``None`` in an optional nested field, or a plain value where a schema
    # was expected: nothing to filter into, so nothing is passed on.
    return None
