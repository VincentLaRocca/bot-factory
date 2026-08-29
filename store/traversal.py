"""Breadth-first traversal of a store, bounded by a :class:`View`.

The walk only ever asks the index for the edges of objects it has already
admitted, so the cost is the size of the neighbourhood, never the size of the
graph.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from aiop import Relation

from .view import Direction, View

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from .repository import ObjectRepository


@dataclass(frozen=True)
class Step:
    """One crossed edge, and how far from the root it was crossed."""

    relation: Relation
    depth: int
    direction: Direction

    @property
    def source(self) -> str:
        return self.relation.subject if self.direction is Direction.OUT else self.relation.object

    @property
    def target(self) -> str:
        return self.relation.object if self.direction is Direction.OUT else self.relation.subject


@dataclass(frozen=True)
class Traversal:
    """What a walk found: the objects reached, and the edges that reached them."""

    root: str
    depths: Dict[str, int] = field(default_factory=dict)
    steps: Tuple[Step, ...] = ()

    @property
    def ids(self) -> List[str]:
        return sorted(self.depths)

    def depth_of(self, object_id: str) -> Optional[int]:
        return self.depths.get(object_id)

    def at_depth(self, depth: int) -> List[str]:
        return sorted(i for i, d in self.depths.items() if d == depth)

    @property
    def relations(self) -> List[Relation]:
        return [step.relation for step in self.steps]


def traverse(store: "ObjectRepository", root: str, view: View) -> Traversal:
    """Walk outward from ``root``, admitting only what ``view`` allows.

    The root is always admitted, even when the view would not otherwise take
    an object of its type: a cluster is assembled *around* a starting object.
    """
    store.get(root)  # fail loudly on an unknown starting point

    depths: Dict[str, int] = {root: 0}
    steps: List[Step] = []
    queue = deque([root])

    while queue:
        current = queue.popleft()
        depth = depths[current]
        if depth >= view.depth:
            continue

        for direction, relation in _edges(store, current, view):
            neighbour = relation.object if direction is Direction.OUT else relation.subject
            obj = store.find(neighbour)
            if obj is None or not view.admits(obj):
                continue
            steps.append(Step(relation=relation, depth=depth + 1, direction=direction))
            if neighbour not in depths:
                depths[neighbour] = depth + 1
                queue.append(neighbour)

    return Traversal(root=root, depths=depths, steps=tuple(steps))


def _edges(store: "ObjectRepository", object_id: str, view: View) -> List[Tuple[Direction, Relation]]:
    """The edges of ``object_id`` the view is willing to cross, in a stable order."""
    edges: List[Tuple[Direction, Relation]] = []
    if view.direction.includes(Direction.OUT):
        edges += [(Direction.OUT, r) for r in store.outbound(object_id)]
    if view.direction.includes(Direction.IN):
        edges += [(Direction.IN, r) for r in store.inbound(object_id)]
    return [
        (direction, relation)
        for direction, relation in edges
        if view.admits_predicate(relation.predicate)
    ]
