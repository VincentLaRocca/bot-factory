"""Bindings: the properties a calculation declares it consumes.

A binding names one variable, one object and one property of that object. It
is a pointer, never a copy: the value is read from the store at the moment of
resolution, so a calculation cannot quietly go on using a figure the world has
moved past.

Resolution fails loudly. A missing object or a missing property is a defect in
the graph, not a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from store import ObjectRepository


class UnresolvedBinding(LookupError):
    """Raised when a binding cannot be read out of the store."""

    def __init__(self, binding: "Binding", reason: str) -> None:
        super().__init__(
            f"{binding.variable} <- {binding.source}.{binding.source_property}: {reason}"
        )
        self.binding = binding
        self.reason = reason


@dataclass(frozen=True)
class Binding:
    """``variable`` takes its value from ``source.source_property``."""

    variable: str
    source: str
    source_property: str

    def resolve(self, store: "ObjectRepository") -> "ResolvedBinding":
        obj = store.find(self.source)
        if obj is None:
            raise UnresolvedBinding(self, "no such object in the store")
        if self.source_property not in obj:
            raise UnresolvedBinding(self, "the object has no such property")
        return ResolvedBinding(binding=self, value=obj.get(self.source_property))

    def to_dict(self, keys: "BindingKeys") -> Dict[str, Any]:
        return {
            keys.variable: self.variable,
            keys.source: self.source,
            keys.source_property: self.source_property,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], keys: "BindingKeys") -> "Binding":
        try:
            return cls(
                variable=payload[keys.variable],
                source=payload[keys.source],
                source_property=payload[keys.source_property],
            )
        except KeyError as missing:
            raise ValueError(f"a binding is missing {missing}") from None


@dataclass(frozen=True)
class ResolvedBinding:
    """A binding and the value it currently reads."""

    binding: Binding
    value: Any

    @property
    def variable(self) -> str:
        return self.binding.variable

    def to_dict(self, keys: "BindingKeys") -> Dict[str, Any]:
        return {**self.binding.to_dict(keys), keys.value: self.value}


@dataclass(frozen=True)
class BindingKeys:
    """What a binding's four fields are called in this vocabulary."""

    variable: str
    source: str
    source_property: str
    value: str


def resolve(
    bindings: Iterable[Binding], store: "ObjectRepository"
) -> List[ResolvedBinding]:
    """Read every binding, in declaration order."""
    return [binding.resolve(store) for binding in bindings]


def values(resolved: Iterable[ResolvedBinding]) -> Dict[str, Any]:
    """The resolved bindings as the keyword arguments of a function."""
    return {item.variable: item.value for item in resolved}
