"""Structural validation for AIOP objects and JSON-LD documents.

Core validation is universal: it checks the protocol envelope (identity,
types, state, relation and provenance shape, graph integrity) and nothing
else. Domain rules — which types exist and which properties they require —
live in a :class:`Profile` supplied by the layer above Core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from .object import AIOPObject, normalise_types
from .relation import EMPTY_VOCABULARY, Relation, Vocabulary
from .state import State

REQUIRED_JSONLD_KEYS = ("@id", "@type")


@dataclass
class ValidationIssue:
    """A single problem found during validation."""

    path: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"


@dataclass
class ValidationResult:
    """The outcome of validating one object or document."""

    issues: List[ValidationIssue] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.is_valid

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add(self, path: str, message: str, severity: str = "error") -> None:
        self.issues.append(ValidationIssue(path=path, message=message, severity=severity))

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.issues.extend(other.issues)
        return self

    def raise_for_errors(self) -> None:
        if not self.is_valid:
            raise ValidationError(self)


class ValidationError(Exception):
    """Raised by :meth:`ValidationResult.raise_for_errors`."""

    def __init__(self, result: ValidationResult) -> None:
        super().__init__("; ".join(str(i) for i in result.errors))
        self.result = result


@dataclass(frozen=True)
class Profile:
    """Domain rules layered on top of Core.

    ``required_properties`` maps a type name to the properties an object
    carrying that type must provide. Requirements accumulate across every
    type an object declares. ``known_types`` and ``vocabulary``, when given,
    turn unrecognised types and predicates into warnings.
    """

    name: str = "anonymous"
    required_properties: Mapping[str, Sequence[str]] = field(default_factory=dict)
    known_types: Optional[Set[str]] = None
    vocabulary: Vocabulary = EMPTY_VOCABULARY

    def requirements_for(self, types: Sequence[str]) -> List[str]:
        required: List[str] = []
        for name in types:
            for key in self.required_properties.get(name, ()):
                if key not in required:
                    required.append(key)
        return required

    def validate_values(self, types: Sequence[str], values: Mapping[str, Any], path: str):
        result = ValidationResult()
        for key in self.requirements_for(types):
            if values.get(key) in (None, ""):
                result.add(
                    f"{path}.{key}",
                    f"is required by profile '{self.name}' for type(s) {list(types)}",
                )
        if self.known_types is not None:
            for name in types:
                if name not in self.known_types:
                    result.add(
                        f"{path}.@type",
                        f"'{name}' is not declared by profile '{self.name}'",
                        severity="warning",
                    )
        return result

    def validate_predicate(self, predicate: str, path: str) -> ValidationResult:
        result = ValidationResult()
        known = self.vocabulary.predicates()
        if known and predicate not in known:
            result.add(
                path,
                f"'{predicate}' is not declared by profile '{self.name}'",
                severity="warning",
            )
        return result


#: The permissive default: envelope checks only.
CORE_PROFILE = Profile(name="core")


def validate_document(
    document: Dict[str, Any], profile: Profile = CORE_PROFILE
) -> ValidationResult:
    """Validate a raw JSON-LD document before it is parsed."""
    result = ValidationResult()

    if "@context" not in document:
        result.add("@context", "missing JSON-LD context", severity="warning")

    for key in REQUIRED_JSONLD_KEYS:
        if not document.get(key):
            result.add(key, "is required")

    types = normalise_types(document.get("@type"))
    raw_type = document.get("@type")
    if isinstance(raw_type, list) and any(not isinstance(t, str) for t in raw_type):
        result.add("@type", "every type must be a string")

    state = document.get("state")
    if state is not None:
        try:
            State(state)
        except ValueError:
            result.add("state", f"'{state}' is not a known state")

    for position, payload in enumerate(document.get("relations", [])):
        for key in ("subject", "predicate", "object"):
            if not payload.get(key):
                result.add(f"relations[{position}].{key}", "is required")
        predicate = payload.get("predicate")
        if predicate:
            result.merge(
                profile.validate_predicate(predicate, f"relations[{position}].predicate")
            )

    for position, payload in enumerate(document.get("provenance", [])):
        if not payload.get("agent"):
            result.add(f"provenance[{position}].agent", "is required")
        confidence = payload.get("confidence", 1.0)
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            result.add(
                f"provenance[{position}].confidence", "must be a number within [0, 1]"
            )

    reserved = {"@context", "@id", "@type", "state", "provenance", "relations"}
    values = {k: v for k, v in document.items() if k not in reserved}
    result.merge(profile.validate_values(types, values, "$"))
    return result


def validate_object(obj: AIOPObject, profile: Profile = CORE_PROFILE) -> ValidationResult:
    """Validate a materialised :class:`AIOPObject`."""
    result = ValidationResult()

    if not obj.id:
        result.add("id", "is required")
    if not obj.types:
        result.add("types", "at least one type is required")
    if not obj.provenance:
        result.add("provenance", "object has no attestations", severity="warning")

    for position, relation in enumerate(obj.relations):
        if relation.subject != obj.id:
            result.add(
                f"relations[{position}].subject",
                f"expected '{obj.id}', found '{relation.subject}'",
            )
        result.merge(
            profile.validate_predicate(
                relation.predicate, f"relations[{position}].predicate"
            )
        )

    result.merge(profile.validate_values(obj.types, obj.properties, "properties"))
    return result


def validate_graph(
    objects: Iterable[AIOPObject],
    relations: Optional[Iterable[Relation]] = None,
    profile: Profile = CORE_PROFILE,
) -> ValidationResult:
    """Validate a set of objects and check that relations resolve."""
    objects = list(objects)
    result = ValidationResult()
    known: Set[str] = set()

    for obj in objects:
        if obj.id in known:
            result.add(obj.id, "duplicate object identifier")
        known.add(obj.id)
        result.merge(validate_object(obj, profile))

    edges = list(relations) if relations is not None else [
        relation for obj in objects for relation in obj.relations
    ]
    for relation in edges:
        for role in ("subject", "object"):
            reference = getattr(relation, role)
            if reference not in known:
                result.add(
                    f"{relation.predicate}.{role}",
                    f"dangling reference to '{reference}'",
                    severity="warning",
                )
    return result
