"""Two-way relation indexing.

An object's relations are stored on the object itself, which makes outward
traversal trivial and inward traversal a full scan. ``RelationIndex`` keeps the
reverse adjacency as well, so "what points at this?" costs the same as "what
does this point at?" — the difference between waking one neighbourhood and
waking the whole graph.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set

from aiop import Relation


class RelationIndex:
    """Outward and inward adjacency over a set of relations."""

    def __init__(self, relations: Iterable[Relation] = ()) -> None:
        self._out: Dict[str, List[Relation]] = defaultdict(list)
        self._in: Dict[str, List[Relation]] = defaultdict(list)
        self.add(relations)

    def __len__(self) -> int:
        return sum(len(edges) for edges in self._out.values())

    def add(self, relations: Iterable[Relation]) -> "RelationIndex":
        for relation in relations:
            if relation in self._out[relation.subject]:
                continue
            self._out[relation.subject].append(relation)
            self._in[relation.object].append(relation)
        return self

    def remove(self, relations: Iterable[Relation]) -> "RelationIndex":
        for relation in relations:
            if relation in self._out[relation.subject]:
                self._out[relation.subject].remove(relation)
            if relation in self._in[relation.object]:
                self._in[relation.object].remove(relation)
        return self

    def replace(self, subject: str, relations: Iterable[Relation]) -> "RelationIndex":
        """Swap every outbound edge of ``subject`` for ``relations``."""
        self.remove(list(self._out.get(subject, [])))
        return self.add(relations)

    def outbound(self, object_id: str, predicate: Optional[str] = None) -> List[Relation]:
        return self._matching(self._out.get(object_id, []), predicate)

    def inbound(self, object_id: str, predicate: Optional[str] = None) -> List[Relation]:
        return self._matching(self._in.get(object_id, []), predicate)

    def neighbours(self, object_id: str, predicate: Optional[str] = None) -> Set[str]:
        """Identifiers one hop away, in either direction."""
        return {r.object for r in self.outbound(object_id, predicate)} | {
            r.subject for r in self.inbound(object_id, predicate)
        }

    def predicates(self) -> Set[str]:
        return {relation.predicate for relation in self.relations()}

    def relations(self) -> List[Relation]:
        return [relation for edges in self._out.values() for relation in edges]

    @staticmethod
    def _matching(
        relations: Iterable[Relation], predicate: Optional[str]
    ) -> List[Relation]:
        return [r for r in relations if predicate is None or r.predicate == predicate]
