"""AIOP — the AI Object Protocol.

A minimal, dependency-free core for representing objects, the relations
between them, their lifecycle state, and the provenance of everything
asserted about them, all serialisable to JSON-LD.

Core carries no domain vocabulary: type names, predicates and the rules
binding them live in a :class:`Profile` layered above Core.
"""

from .object import CONTEXT_URI, AIOPObject, index, new_id, normalise_types, of_type
from .provenance import Provenance, ProvenanceChain
from .relation import EMPTY_VOCABULARY, Relation, RelationGraph, Vocabulary
from .state import InvalidTransition, State, StateChange, StateMachine
from .validation import (
    CORE_PROFILE,
    Profile,
    ValidationError,
    ValidationIssue,
    ValidationResult,
    validate_document,
    validate_graph,
    validate_object,
)

__version__ = "0.1.0"

__all__ = [
    "AIOPObject",
    "CONTEXT_URI",
    "CORE_PROFILE",
    "EMPTY_VOCABULARY",
    "InvalidTransition",
    "Profile",
    "Provenance",
    "ProvenanceChain",
    "Relation",
    "RelationGraph",
    "State",
    "StateChange",
    "StateMachine",
    "ValidationError",
    "ValidationIssue",
    "ValidationResult",
    "Vocabulary",
    "__version__",
    "index",
    "new_id",
    "normalise_types",
    "of_type",
    "validate_document",
    "validate_graph",
    "validate_object",
]
