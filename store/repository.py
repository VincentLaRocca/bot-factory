"""The storage interface, and the in-memory implementation of it.

``ObjectRepository`` is the whole contract a backend has to honour. v0.1 ships
``ObjectStore``, which keeps everything in a dictionary; a database-backed
store implements the same five verbs and callers do not change.

The store holds objects, never copies of them. ``get`` returns the very
instance that was added, so identity — and with it provenance — is preserved by
construction rather than by careful copying.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Iterable, Iterator, List, Optional, Sequence, Set

from aiop import AIOPObject, Relation, State

from .index import RelationIndex

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from .cluster import ObjectCluster
    from .view import View

#: States an object occupies while it is the current word on its subject.
CURRENT_STATES = frozenset(
    {State.DRAFT, State.PROPOSED, State.ACTIVE}
)


class ObjectNotFound(KeyError):
    """Raised when an identifier is not in the store."""

    def __init__(self, object_id: str) -> None:
        super().__init__(object_id)
        self.object_id = object_id


class DuplicateObject(ValueError):
    """Raised when adding an identifier the store already holds."""

    def __init__(self, object_id: str) -> None:
        super().__init__(f"'{object_id}' is already stored")
        self.object_id = object_id


class ObjectRepository(ABC):
    """What any AIOP object store must be able to do."""

    @abstractmethod
    def add(self, obj: AIOPObject) -> AIOPObject:
        """Store a new object, rejecting an identifier already held."""

    @abstractmethod
    def get(self, object_id: str) -> AIOPObject:
        """Return the stored object, raising ``ObjectNotFound``."""

    @abstractmethod
    def update(self, obj: AIOPObject) -> AIOPObject:
        """Replace the object sharing ``obj.id``."""

    @abstractmethod
    def delete(self, object_id: str) -> AIOPObject:
        """Remove and return the object."""

    @abstractmethod
    def ids(self) -> List[str]:
        """Every identifier held, in a stable order."""

    @abstractmethod
    def outbound(self, object_id: str, predicate: Optional[str] = None) -> List[Relation]:
        """Edges leaving ``object_id``."""

    @abstractmethod
    def inbound(self, object_id: str, predicate: Optional[str] = None) -> List[Relation]:
        """Edges arriving at ``object_id``."""

    # -- conveniences expressed in terms of the five verbs above -------
    def find(self, object_id: str) -> Optional[AIOPObject]:
        try:
            return self.get(object_id)
        except ObjectNotFound:
            return None

    def contains(self, object_id: str) -> bool:
        return self.find(object_id) is not None

    def get_many(self, object_ids: Iterable[str]) -> List[AIOPObject]:
        return [self.get(object_id) for object_id in object_ids]

    def __contains__(self, object_id: str) -> bool:
        return self.contains(object_id)

    def __len__(self) -> int:
        return len(self.ids())

    def __iter__(self) -> Iterator[AIOPObject]:
        return iter(self.get_many(self.ids()))

    def cluster(self, root: str, view: "View") -> "ObjectCluster":
        """Assemble the neighbourhood ``view`` describes around ``root``."""
        from .cluster import ObjectCluster

        return ObjectCluster.assemble(self, root, view)


class ObjectStore(ObjectRepository):
    """An in-memory ``ObjectRepository`` with relation indexes.

    ``version_predicate`` names the edge a newer object uses to point at the
    one it replaces. It is a constructor argument rather than a constant
    because the word for it is profile vocabulary, not protocol.
    """

    def __init__(
        self,
        objects: Iterable[AIOPObject] = (),
        version_predicate: Optional[str] = None,
    ) -> None:
        self._objects: Dict[str, AIOPObject] = {}
        self._index = RelationIndex()
        self.version_predicate = version_predicate
        for obj in objects:
            self.add(obj)

    # -- the five verbs -------------------------------------------------
    def add(self, obj: AIOPObject) -> AIOPObject:
        if obj.id in self._objects:
            raise DuplicateObject(obj.id)
        self._objects[obj.id] = obj
        self._index.add(obj.relations)
        return obj

    def get(self, object_id: str) -> AIOPObject:
        try:
            return self._objects[object_id]
        except KeyError:
            raise ObjectNotFound(object_id) from None

    def update(self, obj: AIOPObject) -> AIOPObject:
        previous = self.get(obj.id)
        self._index.remove(previous.relations)
        self._objects[obj.id] = obj
        self._index.add(obj.relations)
        return obj

    def delete(self, object_id: str) -> AIOPObject:
        obj = self.get(object_id)
        self._index.remove(obj.relations)
        del self._objects[object_id]
        return obj

    def ids(self) -> List[str]:
        return sorted(self._objects)

    # -- writes that change an object in place --------------------------
    def reindex(self, object_id: str) -> AIOPObject:
        """Re-read the relations of an object mutated in place."""
        obj = self.get(object_id)
        self._index.replace(object_id, obj.relations)
        return obj

    def put(self, obj: AIOPObject) -> AIOPObject:
        """Add or update, whichever applies."""
        return self.update(obj) if obj.id in self._objects else self.add(obj)

    # -- enumeration ----------------------------------------------------
    def objects(
        self,
        types: Optional[Iterable[str]] = None,
        states: Optional[Iterable[State]] = None,
    ) -> List[AIOPObject]:
        """Stored objects, optionally narrowed by type or lifecycle state."""
        wanted_types = set(types) if types is not None else None
        wanted_states = set(states) if states is not None else None
        return [
            obj
            for obj in self
            if (wanted_types is None or wanted_types & set(obj.types))
            and (wanted_states is None or obj.state in wanted_states)
        ]

    def current(self, types: Optional[Iterable[str]] = None) -> List[AIOPObject]:
        """Objects that have not been superseded or retired."""
        return self.objects(types=types, states=CURRENT_STATES)

    # -- relations ------------------------------------------------------
    @property
    def index(self) -> RelationIndex:
        return self._index

    def relations(self) -> List[Relation]:
        return self._index.relations()

    def outbound(self, object_id: str, predicate: Optional[str] = None) -> List[Relation]:
        return self._index.outbound(object_id, predicate)

    def inbound(self, object_id: str, predicate: Optional[str] = None) -> List[Relation]:
        return self._index.inbound(object_id, predicate)

    def referenced_by(self, object_id: str) -> Set[str]:
        return {relation.subject for relation in self.inbound(object_id)}

    def dangling(self) -> List[Relation]:
        """Relations pointing at identifiers the store does not hold."""
        return [r for r in self.relations() if r.object not in self._objects]

    # -- versions -------------------------------------------------------
    def history_of(self, object_id: str) -> List[AIOPObject]:
        """The object, then everything it supersedes, newest first.

        Requires ``version_predicate``; without one the store has no idea
        which edge means "replaces", and says so.
        """
        if self.version_predicate is None:
            raise ValueError("the store was built without a version_predicate")

        chain: List[AIOPObject] = []
        seen: Set[str] = set()
        current: Optional[str] = object_id
        while current is not None and current not in seen:
            seen.add(current)
            obj = self.find(current)
            if obj is None:
                break
            chain.append(obj)
            older = self.outbound(current, self.version_predicate)
            current = older[0].object if older else None
        return chain

    def latest_of(self, object_id: str) -> AIOPObject:
        """Follow supersession forwards to whatever replaced ``object_id``."""
        if self.version_predicate is None:
            raise ValueError("the store was built without a version_predicate")

        seen: Set[str] = set()
        current = self.get(object_id)
        while current.id not in seen:
            seen.add(current.id)
            newer = [
                r.subject
                for r in self.inbound(current.id, self.version_predicate)
                if r.subject in self._objects
            ]
            if not newer:
                return current
            current = self.get(sorted(newer)[0])
        return current

    # -- bulk loading ---------------------------------------------------
    def load(self, documents: Sequence[dict]) -> "ObjectStore":
        for document in documents:
            self.put(AIOPObject.from_jsonld(document))
        return self
