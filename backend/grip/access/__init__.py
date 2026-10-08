"""Access: one decision function, relations derived from data, data classes on fields.

This package root is free of the database and of FastAPI. The SQL relation
source lives in ``grip.access.sql`` and the route glue in ``grip.access.deps``.
"""

from grip.access.decider import (
    AANVRAGER,
    BEHEERDER,
    LEZER,
    PLANNER,
    TEKENBEVOEGDE,
    Decider,
    LocalDecider,
    decide,
    permitted_classes,
)
from grip.access.fields import (
    FieldClass,
    NestedFields,
    UnclassifiedFieldError,
    build_response,
    field_classes,
    in_class,
    nested,
    schema_classes,
    unclassified_fields,
)
from grip.access.relations import InMemoryRelationSource, RelationSource
from grip.access.types import (
    CORE_DATA_CLASSES,
    IMPLIED_BY,
    AccessRequest,
    Action,
    AssignmentRole,
    Context,
    DataClass,
    Decision,
    PeerRole,
    Resource,
    ResourceKind,
    Subject,
    SubjectKind,
)

__all__ = [
    "AANVRAGER",
    "BEHEERDER",
    "CORE_DATA_CLASSES",
    "IMPLIED_BY",
    "LEZER",
    "PLANNER",
    "TEKENBEVOEGDE",
    "AccessRequest",
    "Action",
    "AssignmentRole",
    "Context",
    "DataClass",
    "Decider",
    "Decision",
    "FieldClass",
    "InMemoryRelationSource",
    "LocalDecider",
    "NestedFields",
    "PeerRole",
    "RelationSource",
    "Resource",
    "ResourceKind",
    "Subject",
    "SubjectKind",
    "UnclassifiedFieldError",
    "build_response",
    "decide",
    "field_classes",
    "in_class",
    "nested",
    "permitted_classes",
    "schema_classes",
    "unclassified_fields",
]
