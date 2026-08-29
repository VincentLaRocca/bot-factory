"""Reading a calculation out of the store, and fingerprinting its inputs.

The reasoning layer hard-codes no term. Which property holds the function name,
what a result object is called, which predicate means "derived from" — all of it
is a :class:`CalculationSchema` supplied by a profile, exactly as the store takes
its version predicate as configuration rather than knowing the word.

The fingerprint is a deterministic hash of the function name and the resolved
inputs. Two evaluations agree if and only if the world they read agrees, which
is what makes staleness a comparison rather than a guess.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Sequence

from aiop import AIOPObject

from .binding import Binding, BindingKeys, ResolvedBinding, resolve, values

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from store import ObjectRepository


@dataclass(frozen=True)
class CalculationSchema:
    """The vocabulary a deployment uses to write calculations down.

    ``result_type`` and the property names describe the documents; the two
    predicates describe the edges the engine draws. A profile supplies all of
    them, so no domain word appears in this package.
    """

    result_type: str
    function_property: str
    inputs_property: str
    value_property: str
    fingerprint_property: str
    calculation_property: str
    variable_key: str
    source_key: str
    source_property_key: str
    derivation_predicate: str
    version_predicate: str

    @property
    def binding_keys(self) -> BindingKeys:
        return BindingKeys(
            variable=self.variable_key,
            source=self.source_key,
            source_property=self.source_property_key,
            value=self.value_property,
        )


class MalformedCalculation(ValueError):
    """Raised when an object does not describe a runnable calculation."""


@dataclass(frozen=True)
class Calculation:
    """A stored object read through a schema: a function and its bindings."""

    object: AIOPObject
    schema: CalculationSchema

    @property
    def id(self) -> str:
        return self.object.id

    @property
    def function_name(self) -> str:
        name = self.object.get(self.schema.function_property)
        if not name:
            raise MalformedCalculation(
                f"'{self.object.id}' declares no {self.schema.function_property}"
            )
        return name

    @property
    def bindings(self) -> List[Binding]:
        declared = self.object.get(self.schema.inputs_property)
        if not declared:
            raise MalformedCalculation(
                f"'{self.object.id}' declares no {self.schema.inputs_property}"
            )
        return [
            Binding.from_dict(payload, self.schema.binding_keys) for payload in declared
        ]

    @property
    def sources(self) -> List[str]:
        """The distinct objects this calculation consumes, in a stable order."""
        return sorted({binding.source for binding in self.bindings})

    def resolve(self, store: "ObjectRepository") -> List[ResolvedBinding]:
        """Read every declared input from the store as it stands now."""
        return resolve(self.bindings, store)

    def values(self, store: "ObjectRepository") -> Dict[str, Any]:
        return values(self.resolve(store))

    def fingerprint(self, store: "ObjectRepository") -> str:
        return fingerprint(self.function_name, self.resolve(store))


def fingerprint(function_name: str, resolved: Iterable[ResolvedBinding]) -> str:
    """A deterministic digest of a function and the inputs it was given."""
    payload = {
        "function": function_name,
        "inputs": sorted(
            [
                [item.variable, item.binding.source, item.binding.source_property, item.value]
                for item in resolved
            ]
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def bindings_of(result: AIOPObject, schema: CalculationSchema) -> List[Binding]:
    """The bindings a result object recorded when it was computed."""
    return [
        Binding.from_dict(payload, schema.binding_keys)
        for payload in result.get(schema.inputs_property, [])
    ]


def is_result(obj: AIOPObject, schema: CalculationSchema) -> bool:
    return obj.has_type(schema.result_type)


def input_snapshot(
    resolved: Sequence[ResolvedBinding], schema: CalculationSchema
) -> List[Dict[str, Any]]:
    """The resolved inputs as they are written onto a result object."""
    return [item.to_dict(schema.binding_keys) for item in resolved]
