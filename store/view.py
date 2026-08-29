"""Views: a declarative statement of which neighbourhood matters.

A ``View`` says what to include — types, predicates, direction, depth, states —
and nothing about how to walk. It is a value object, shared and reused; the
traversal reads it. Views are domain vocabulary, so the concrete ones
(``CHARACTER_VIEW`` and friends) live in a profile, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Iterable, Optional

from aiop import State


class Direction(str, Enum):
    """Which way an edge may be crossed."""

    OUT = "out"
    IN = "in"
    BOTH = "both"

    def includes(self, other: "Direction") -> bool:
        return self is Direction.BOTH or self is other


def _frozen(values: Optional[Iterable[str]]) -> Optional[FrozenSet[str]]:
    return None if values is None else frozenset(values)


@dataclass(frozen=True)
class View:
    """Which objects and edges belong in a cluster.

    ``None`` means "no opinion": a view with no ``predicates`` crosses every
    edge, and one with no ``types`` admits every object. ``depth`` counts hops
    from the starting object, so ``depth=0`` is the object alone.
    """

    name: str = "view"
    depth: int = 1
    direction: Direction = Direction.BOTH
    predicates: Optional[FrozenSet[str]] = None
    exclude_predicates: FrozenSet[str] = frozenset()
    types: Optional[FrozenSet[str]] = None
    states: Optional[FrozenSet[State]] = None
    description: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("depth must not be negative")
        object.__setattr__(self, "predicates", _frozen(self.predicates))
        object.__setattr__(self, "exclude_predicates", frozenset(self.exclude_predicates))
        object.__setattr__(self, "types", _frozen(self.types))
        if self.states is not None:
            object.__setattr__(self, "states", frozenset(self.states))

    # -- predicates -----------------------------------------------------
    def admits_predicate(self, predicate: str) -> bool:
        if predicate in self.exclude_predicates:
            return False
        return self.predicates is None or predicate in self.predicates

    # -- objects --------------------------------------------------------
    def admits_types(self, types: Iterable[str]) -> bool:
        return self.types is None or bool(self.types & set(types))

    def admits_state(self, state: State) -> bool:
        return self.states is None or state in self.states

    def admits(self, obj) -> bool:
        """Whether an object may enter a cluster built with this view."""
        return self.admits_types(obj.types) and self.admits_state(obj.state)

    # -- derivation -----------------------------------------------------
    def at_depth(self, depth: int) -> "View":
        return self.narrow(depth=depth)

    def narrow(self, **changes) -> "View":
        """A copy of this view with some fields replaced."""
        fields = {
            "name": self.name,
            "depth": self.depth,
            "direction": self.direction,
            "predicates": self.predicates,
            "exclude_predicates": self.exclude_predicates,
            "types": self.types,
            "states": self.states,
            "description": self.description,
        }
        fields.update(changes)
        return View(**fields)

    def to_dict(self) -> dict:
        """A deterministic, JSON-safe description of the view."""
        payload = {
            "name": self.name,
            "depth": self.depth,
            "direction": self.direction.value,
        }
        if self.predicates is not None:
            payload["predicates"] = sorted(self.predicates)
        if self.exclude_predicates:
            payload["excludePredicates"] = sorted(self.exclude_predicates)
        if self.types is not None:
            payload["types"] = sorted(self.types)
        if self.states is not None:
            payload["states"] = sorted(state.value for state in self.states)
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "View":
        return cls(
            name=payload.get("name", "view"),
            depth=payload.get("depth", 1),
            direction=Direction(payload.get("direction", "both")),
            predicates=payload.get("predicates"),
            exclude_predicates=payload.get("excludePredicates", ()),
            types=payload.get("types"),
            states=(
                None
                if payload.get("states") is None
                else [State(value) for value in payload["states"]]
            ),
        )


#: Everything one hop out and in — the default when no view is given.
NEIGHBOURHOOD_VIEW = View(name="neighbourhood", depth=1)
