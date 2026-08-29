"""Which results the world has moved past.

A result carries the fingerprint of the inputs it was computed from. Reading
those same inputs again and re-fingerprinting them answers "is this still
true?" without re-running the function.

Finding the affected results is a lookup, not a scan: the store already indexes
relations in both directions, so the derivation edges a result draws to its
sources are, read backwards, the dependents of those sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from aiop import AIOPObject
from store import ObjectStore

from .binding import UnresolvedBinding, resolve
from .calculation import CalculationSchema, bindings_of, fingerprint, is_result


@dataclass(frozen=True)
class Staleness:
    """Why a result is or is not still current."""

    result: AIOPObject
    stale: bool
    reason: str
    recorded_fingerprint: str = ""
    current_fingerprint: str = ""

    def __bool__(self) -> bool:
        return self.stale


def check(
    store: ObjectStore, result: AIOPObject, schema: CalculationSchema
) -> Staleness:
    """Compare the inputs a result was computed from with the world today."""
    recorded = result.get(schema.fingerprint_property, "")
    if not recorded:
        return Staleness(result, True, "the result carries no input fingerprint")

    function_name = result.get(schema.function_property, "")
    try:
        current = fingerprint(function_name, resolve(bindings_of(result, schema), store))
    except UnresolvedBinding as missing:
        return Staleness(result, True, f"an input no longer resolves: {missing}", recorded)

    if current != recorded:
        return Staleness(result, True, "an input value has changed", recorded, current)
    return Staleness(result, False, "inputs unchanged", recorded, current)


def is_stale(store: ObjectStore, result: AIOPObject, schema: CalculationSchema) -> bool:
    return check(store, result, schema).stale


def results(
    store: ObjectStore, schema: CalculationSchema, current_only: bool = True
) -> List[AIOPObject]:
    """Every result object in the store."""
    if current_only:
        return store.current(types=[schema.result_type])
    return store.objects(types=[schema.result_type])


def stale(
    store: ObjectStore, schema: CalculationSchema, current_only: bool = True
) -> List[AIOPObject]:
    """The results whose inputs no longer match what they were computed from."""
    return [
        result
        for result in results(store, schema, current_only)
        if is_stale(store, result, schema)
    ]


def dependents_of(
    store: ObjectStore,
    object_id: str,
    schema: CalculationSchema,
    result_type: Optional[str] = None,
) -> List[AIOPObject]:
    """The objects derived from ``object_id`` — an index lookup, not a sweep."""
    wanted = result_type if result_type is not None else schema.result_type
    seen = []
    for relation in store.inbound(object_id, schema.derivation_predicate):
        dependent = store.find(relation.subject)
        if dependent is None or dependent in seen:
            continue
        if wanted and not dependent.has_type(wanted):
            continue
        seen.append(dependent)
    return seen


def invalidated_by(
    store: ObjectStore, object_id: str, schema: CalculationSchema
) -> List[AIOPObject]:
    """The results that depend on ``object_id`` and have actually gone stale."""
    return [
        result
        for result in dependents_of(store, object_id, schema)
        if is_result(result, schema) and is_stale(store, result, schema)
    ]
