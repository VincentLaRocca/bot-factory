"""How cautious this analyst is, written down rather than assumed.

Every threshold the analyst applies — how much evidence makes a claim, how
complete a picture has to be before a recommendation is worth making, what
counts as a big enough expected value to act on — lives in one value object.
Two runs under the same policy over the same graph produce the same objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

#: The actions the analyst may recommend.
ACTIONS: Tuple[str, ...] = (
    "WATCH",
    "RESEARCH",
    "CONTACT",
    "BUILD",
    "INVESTIGATE_INVESTMENT",
    "REJECT",
    "ARCHIVE",
)


@dataclass(frozen=True)
class AnalysisPolicy:
    """The thresholds and capabilities one analysis run is conducted under."""

    name: str = "default"
    version: str = "0.1"

    #: A claim needs this many independent pieces of supporting evidence
    #: before its value may be written onto an object.
    minimum_evidence: int = 1
    #: and evidence weaker than this is recorded but never acted on.
    minimum_confidence: float = 0.5

    #: Dimensions below this decision impact are not worth a gap object.
    gap_importance_threshold: float = 0.4
    #: At most this many gaps are researched in one run, highest priority first.
    maximum_research: int = 8

    #: How complete the picture must be before the analyst will recommend
    #: anything other than more research.
    minimum_completeness: float = 0.6
    #: An expected value below this is not interesting whatever the ratio.
    material_expected_value: float = 0.0
    #: and the payoff has to be at least this lopsided to be worth the trouble.
    material_asymmetry: float = 1.5

    #: What we can actually bring, for the OurEdge assessment. An empty set
    #: means no edge can be established, which is a legitimate answer.
    capabilities: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        """A deterministic description, recorded on the execution record."""
        return {
            "name": self.name,
            "version": self.version,
            "minimum_evidence": self.minimum_evidence,
            "minimum_confidence": self.minimum_confidence,
            "gap_importance_threshold": self.gap_importance_threshold,
            "maximum_research": self.maximum_research,
            "minimum_completeness": self.minimum_completeness,
            "material_expected_value": self.material_expected_value,
            "material_asymmetry": self.material_asymmetry,
            "capabilities": list(self.capabilities),
        }


#: The policy the demonstration runs under: one solid source is enough to
#: record a value, and we claim two capabilities.
DEFAULT_POLICY = AnalysisPolicy(
    name="asymmetry-default",
    capabilities=("clinical-informatics", "ai-systems-integration"),
)

CAUTIOUS_POLICY = AnalysisPolicy(
    name="asymmetry-cautious",
    minimum_evidence=2,
    minimum_confidence=0.75,
    minimum_completeness=0.8,
    material_asymmetry=2.5,
)

POLICIES: Dict[str, AnalysisPolicy] = {
    policy.name: policy for policy in (DEFAULT_POLICY, CAUTIOUS_POLICY)
}

__all__ = [
    "ACTIONS",
    "AnalysisPolicy",
    "CAUTIOUS_POLICY",
    "DEFAULT_POLICY",
    "POLICIES",
]
