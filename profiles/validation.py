"""Vocabulary and validation rules for Validation and Decision objects."""

from pathlib import Path

from aiop import CONTEXT_URI, Profile, Vocabulary

from .demo import DEMO_CONTEXT_URI, REQUIRED_PROPERTIES, VERSION_PREDICATE
from .observer import OBSERVER_CONTEXT_URI, OBSERVER_REQUIRED_PROPERTIES
from .research import (
    RESEARCH_CONTEXT_URI,
    RESEARCH_REQUIRED_PROPERTIES,
    RESEARCH_VOCABULARY,
)

VALIDATION_CONTEXT_URI = "https://aiop.dev/profiles/validation/context.jsonld"
VALIDATION_CONTEXT_FILE = Path(__file__).with_name("validation-context.jsonld")

VALIDATION_CONTEXT = [
    CONTEXT_URI,
    DEMO_CONTEXT_URI,
    OBSERVER_CONTEXT_URI,
    RESEARCH_CONTEXT_URI,
    VALIDATION_CONTEXT_URI,
]

VALIDATION_VOCABULARY = Vocabulary(
    inverses={
        **RESEARCH_VOCABULARY.inverses,
        "validationOf": "validatedBy",
        "basedOn": "basisFor",
        "decisionFor": "decidedBy",
    },
    symmetric=frozenset(RESEARCH_VOCABULARY.symmetric),
)

VALIDATION_REQUIRED_PROPERTIES = {
    "Validation": [
        "claim",
        "claim_type",
        "normalized_claim",
        "tests",
        "verdict",
        "public_verdict",
        "confidence",
        "confidence_kind",
        "input_fingerprint",
    ],
    "Decision": [
        "validation",
        "claim",
        "source_verdict",
        "verdict",
        "recommendation",
        "human_review_required",
        "authorized_action",
    ],
}

VALIDATION_PROFILE = Profile(
    name="validation",
    required_properties={
        **REQUIRED_PROPERTIES,
        **OBSERVER_REQUIRED_PROPERTIES,
        **RESEARCH_REQUIRED_PROPERTIES,
        **VALIDATION_REQUIRED_PROPERTIES,
    },
    known_types=(
        set(REQUIRED_PROPERTIES)
        | set(OBSERVER_REQUIRED_PROPERTIES)
        | set(RESEARCH_REQUIRED_PROPERTIES)
        | set(VALIDATION_REQUIRED_PROPERTIES)
    ),
    vocabulary=VALIDATION_VOCABULARY,
)

__all__ = [
    "VALIDATION_CONTEXT",
    "VALIDATION_CONTEXT_FILE",
    "VALIDATION_CONTEXT_URI",
    "VALIDATION_PROFILE",
    "VALIDATION_REQUIRED_PROPERTIES",
    "VALIDATION_VOCABULARY",
    "VERSION_PREDICATE",
]
