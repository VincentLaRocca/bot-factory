"""Adversarial claim validation as an Observer plug-in."""

from .evaluator import (
    CLAIM_TYPES,
    CONTRADICTED,
    Evaluation,
    SUPPORTED,
    UNRESOLVED,
    UNTESTABLE,
    VERDICTS,
    ValidationPolicy,
    WEAKLY_SUPPORTED,
    evaluate_claim,
)
from .validator import CAPABILITY, CARD, VERSION, Validator

__all__ = [
    "CAPABILITY",
    "CARD",
    "CLAIM_TYPES",
    "CONTRADICTED",
    "Evaluation",
    "SUPPORTED",
    "UNRESOLVED",
    "UNTESTABLE",
    "VERDICTS",
    "VERSION",
    "ValidationPolicy",
    "Validator",
    "WEAKLY_SUPPORTED",
    "evaluate_claim",
]
