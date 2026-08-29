"""Typed relations between AIOP objects.

Core knows the *shape* of a relation and how to reason over a graph of them.
It deliberately knows no predicates: which predicates exist, and which are
inverses of one another, is vocabulary supplied by a profile above Core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, Iterator, List, Mapping, Optional, Set


@dataclass(frozen=True)
class Vocabulary:
    """A predicate vocabulary: inverse pairs and self-inverse predicates."""

    inverses: Mapping[str, str] = field(default_factory=dict)
    symmetric: FrozenSet[str] = frozenset()

    def inverse_of(self, predicate: str) -> Optional[str]:
        """Return the inverse of ``predicate``, or ``None`` when unknown."""
        if predicate in self.symmetric:
            return predicate
        if predicate in self.inverses:
            return self.inverses[predicate]
        for forward, backward in self.inverses.items():
            if backward == predicate:
                return forward
        return None

    def predicates(self) -> Set[str]:
        return set(self.inverses) | set(self.inverses.values()) | set(self.symmetric)

    def extend(
        self,
        inverses: Optional[Mapping[str, str]] = None,
        symmetric: Iterable[str] = (),
    ) -> "Vocabulary":
        return Vocabulary(
            inverses={**self.inverses, **(inverses or {})},
            symmetric=self.symmetric | frozenset(symmetric),
        )


#: Core ships an empty vocabulary; profiles provide the domain predicates.
EMPTY_VOCABULARY = Vocabulary()


@dataclass(frozen=True)
class Relation:
    """A directed ``subject -> predicate -> object`` triple."""

    subject: str
    predicate: str
    object: str
    attributes: Dict[str, Any] = field(default_factory=dict, compare=False)

    def inverse(self, vocabulary: Vocabulary = EMPTY_VOCABULARY) -> Optional["Relation"]:
        predicate = vocabulary.inverse_of(self.predicate)
        if predicate is None:
            return None
        return Relation(
            subject=self.object,
            predicate=predicate,
            object=self.subject,
            attributes=dict(self.attributes),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
        }
        if self.attributes:
            payload["attributes"] = dict(self.attributes)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Relation":
        return cls(
            subject=payload["subject"],
            predicate=payload["predicate"],
            object=payload["object"],
            attributes=dict(payload.get("attributes", {})),
        )


class RelationGraph:
    """An in-memory directed multigraph of relations."""

    def __init__(
        self,
        relations: Optional[Iterable[Relation]] = None,
        vocabulary: Vocabulary = EMPTY_VOCABULARY,
    ) -> None:
        self._relations: List[Relation] = list(relations or [])
        self.vocabulary = vocabulary

    def __len__(self) -> int:
        return len(self._relations)

    def __iter__(self) -> Iterator[Relation]:
        return iter(self._relations)

    def add(self, relation: Relation, with_inverse: bool = False) -> "RelationGraph":
        if relation not in self._relations:
            self._relations.append(relation)
        if with_inverse:
            implied = relation.inverse(self.vocabulary)
            if implied is not None and implied not in self._relations:
                self._relations.append(implied)
        return self

    def find(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
    ) -> List[Relation]:
        return [
            r
            for r in self._relations
            if (subject is None or r.subject == subject)
            and (predicate is None or r.predicate == predicate)
            and (object is None or r.object == object)
        ]

    def neighbours(self, subject: str, predicate: Optional[str] = None) -> List[str]:
        return [r.object for r in self.find(subject=subject, predicate=predicate)]

    def reachable(self, start: str, predicate: Optional[str] = None) -> Set[str]:
        """Transitive closure of ``start`` following ``predicate`` edges."""
        seen: Set[str] = set()
        queue = [start]
        while queue:
            current = queue.pop()
            for neighbour in self.neighbours(current, predicate):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return seen

    def paths(
        self, start: str, end: str, predicates: Optional[Iterable[str]] = None
    ) -> List[List[Relation]]:
        """Every acyclic path of relations from ``start`` to ``end``."""
        allowed = set(predicates) if predicates is not None else None
        found: List[List[Relation]] = []

        def walk(node: str, trail: List[Relation], visited: Set[str]) -> None:
            for relation in self.find(subject=node):
                if allowed is not None and relation.predicate not in allowed:
                    continue
                if relation.object in visited:
                    continue
                step = trail + [relation]
                if relation.object == end:
                    found.append(step)
                else:
                    walk(relation.object, step, visited | {relation.object})

        walk(start, [], {start})
        return found

    def subjects_referencing(self, object_id: str) -> Set[str]:
        """Identifiers of every object holding an edge into ``object_id``."""
        return {r.subject for r in self.find(object=object_id)}

    def has_cycle(self, predicate: Optional[str] = None) -> bool:
        nodes = {r.subject for r in self._relations} | {r.object for r in self._relations}
        return any(node in self.reachable(node, predicate) for node in nodes)
