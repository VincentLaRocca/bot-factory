"""Core AIOP object model.

An :class:`AIOPObject` is the atomic unit of the AI Object Protocol: an
identified, multi-typed bag of properties carrying its own state, provenance
and outbound relations, serialisable to JSON-LD.

Core is domain-agnostic: it never interprets a type name or a predicate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Union

from .provenance import Provenance
from .relation import Relation
from .state import State

#: The Core context. Profiles publish their own, and documents compose them
#: by giving ``@context`` an array.
CONTEXT_URI = "https://aiop.dev/context.jsonld"

TypeSpec = Union[str, Sequence[str], None]
ContextSpec = Union[str, List[Any]]


def new_id(prefix: str = "urn:aiop") -> str:
    """Return a fresh globally unique object identifier."""
    return f"{prefix}:{uuid.uuid4()}"


def normalise_types(spec: TypeSpec) -> List[str]:
    """Coerce a JSON-LD ``@type`` value into an ordered list of type names."""
    if spec is None:
        return []
    if isinstance(spec, str):
        return [spec]
    seen: List[str] = []
    for name in spec:
        if name and name not in seen:
            seen.append(name)
    return seen


@dataclass
class AIOPObject:
    """A single protocol object, carrying one or more semantic types."""

    types: List[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    context: ContextSpec = CONTEXT_URI
    properties: Dict[str, Any] = field(default_factory=dict)
    state: State = State.DRAFT
    provenance: List[Provenance] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.types = normalise_types(self.types)
        if isinstance(self.state, str):
            self.state = State(self.state)

    # -- types --------------------------------------------------------
    @property
    def type(self) -> str:
        """The primary (first) type, or ``""`` when untyped."""
        return self.types[0] if self.types else ""

    def has_type(self, name: str) -> bool:
        return name in self.types

    def add_type(self, name: str) -> "AIOPObject":
        if name and name not in self.types:
            self.types.append(name)
        return self

    # -- properties ---------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def set(self, key: str, value: Any) -> "AIOPObject":
        self.properties[key] = value
        return self

    def __contains__(self, key: str) -> bool:
        return key in self.properties

    # -- state --------------------------------------------------------
    def transition(self, target: State) -> "AIOPObject":
        """Move the object to ``target``, rejecting illegal transitions."""
        self.state = self.state.transition_to(target)
        return self

    # -- provenance ---------------------------------------------------
    def attest(self, provenance: Provenance) -> "AIOPObject":
        self.provenance.append(provenance)
        return self

    @property
    def latest_provenance(self) -> Optional[Provenance]:
        if not self.provenance:
            return None
        return max(self.provenance, key=lambda p: p.generated_at)

    # -- relations ----------------------------------------------------
    def relate(
        self,
        predicate: str,
        target: "AIOPObject | str",
        **attributes: Any,
    ) -> Relation:
        """Create and attach an outbound relation to ``target``."""
        target_id = target.id if isinstance(target, AIOPObject) else target
        relation = Relation(
            subject=self.id,
            predicate=predicate,
            object=target_id,
            attributes=dict(attributes),
        )
        self.relations.append(relation)
        return relation

    def related(self, predicate: Optional[str] = None) -> List[str]:
        """Identifiers of objects this object points at."""
        return [
            r.object
            for r in self.relations
            if predicate is None or r.predicate == predicate
        ]

    def __iter__(self) -> Iterator[Relation]:
        return iter(self.relations)

    # -- serialisation ------------------------------------------------
    def to_jsonld(self) -> Dict[str, Any]:
        document: Dict[str, Any] = {
            "@context": self.context,
            "@id": self.id,
            "@type": self.types[0] if len(self.types) == 1 else list(self.types),
            "state": self.state.value,
        }
        document.update(self.properties)
        if self.provenance:
            document["provenance"] = [p.to_dict() for p in self.provenance]
        if self.relations:
            document["relations"] = [r.to_dict() for r in self.relations]
        return document

    @classmethod
    def from_jsonld(cls, document: Dict[str, Any]) -> "AIOPObject":
        reserved = {"@context", "@id", "@type", "state", "provenance", "relations"}
        properties = {k: v for k, v in document.items() if k not in reserved}
        return cls(
            id=document.get("@id", new_id()),
            context=document.get("@context", CONTEXT_URI),
            types=normalise_types(document.get("@type")),
            properties=properties,
            state=State(document.get("state", State.DRAFT.value)),
            provenance=[Provenance.from_dict(p) for p in document.get("provenance", [])],
            relations=[Relation.from_dict(r) for r in document.get("relations", [])],
        )


def index(objects: Iterable[AIOPObject]) -> Dict[str, AIOPObject]:
    """Index objects by identifier."""
    return {obj.id: obj for obj in objects}


def of_type(objects: Iterable[AIOPObject], name: str) -> List[AIOPObject]:
    """Every object carrying ``name`` among its types."""
    return [obj for obj in objects if obj.has_type(name)]
