"""Profiles: domain vocabularies and rules layered on top of AIOP Core.

Core knows nothing about ``Person``, ``owns`` or ``Calculation``, and its
context (``aiop/context.jsonld``) defines only the protocol envelope.
Everything domain-specific — types, properties, predicates and the JSON-LD
terms for them — lives here, so a deployment can swap or extend the vocabulary
without touching the universal layer.
"""

from .demo import (
    DEMO_CONTEXT,
    DEMO_CONTEXT_FILE,
    DEMO_CONTEXT_URI,
    DEMO_PROFILE,
    DEMO_VOCABULARY,
    VERSION_PREDICATE,
)
from .views import ASYMMETRY_VIEW, CHARACTER_VIEW, DEMO_VIEWS, LINEAGE_VIEW

__all__ = [
    "ASYMMETRY_VIEW",
    "CHARACTER_VIEW",
    "DEMO_CONTEXT",
    "DEMO_CONTEXT_FILE",
    "DEMO_CONTEXT_URI",
    "DEMO_PROFILE",
    "DEMO_VIEWS",
    "DEMO_VOCABULARY",
    "LINEAGE_VIEW",
    "VERSION_PREDICATE",
]
