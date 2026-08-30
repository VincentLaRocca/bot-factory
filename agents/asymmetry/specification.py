"""What an Asymmetry Analyst wants to know about an opportunity.

The specification is a catalogue of dimensions: each one names an object type,
a property on it, how much the decision turns on it, and how likely it is to be
resolvable. Nothing here computes anything. It is the analyst's idea of a
complete picture, written down where it can be inspected, versioned and
disagreed with rather than buried in a prompt.

A dimension having no value is a legitimate outcome. The point of enumerating
them is to be able to say precisely *which* things are unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

#: The groups the specification is organised into, in reporting order.
GROUPS: Tuple[str, ...] = (
    "opportunity",
    "synergy",
    "asymmetry",
    "technology",
    "people",
    "market",
    "access",
    "judgment",
)


@dataclass(frozen=True)
class Dimension:
    """One thing worth knowing, and where it would be written down."""

    name: str
    group: str
    target_type: str
    property: str
    decision_impact: float
    resolvability: float
    description: str
    evidence_required: bool = False
    required_evidence: Tuple[str, ...] = ()
    numeric: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.decision_impact, "decision_impact"),
            (self.resolvability, "resolvability"),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{self.name}: {label} must be between 0 and 1")
        if self.group not in GROUPS:
            raise ValueError(f"{self.name}: '{self.group}' is not a known group")


@dataclass(frozen=True)
class AnalysisSpecification:
    """The dimensions an analysis covers, and the version of that opinion."""

    version: str
    dimensions: Sequence[Dimension]
    description: str = field(default="", compare=False)

    def __iter__(self):
        return iter(self.dimensions)

    def __len__(self) -> int:
        return len(self.dimensions)

    def by_name(self, name: str) -> Dimension:
        for dimension in self.dimensions:
            if dimension.name == name:
                return dimension
        raise KeyError(name)

    def find(self, name: str) -> Optional[Dimension]:
        for dimension in self.dimensions:
            if dimension.name == name:
                return dimension
        return None

    def in_group(self, group: str) -> List[Dimension]:
        return [d for d in self.dimensions if d.group == group]

    def groups(self) -> List[str]:
        present = {d.group for d in self.dimensions}
        return [group for group in GROUPS if group in present]

    def target_types(self) -> List[str]:
        return sorted({d.target_type for d in self.dimensions})

    def properties_of(self, target_type: str) -> Dict[str, Dimension]:
        return {
            d.property: d for d in self.dimensions if d.target_type == target_type
        }


def _d(*args, **kwargs) -> Dimension:
    return Dimension(*args, **kwargs)


#: The v0.1 catalogue. Impact and resolvability are deliberately coarse: they
#: exist to order research, not to pretend at precision.
ASYMMETRY_SPECIFICATION = AnalysisSpecification(
    version="asymmetry-analysis/0.1",
    description="What must be known before an asymmetric bet can be judged.",
    dimensions=(
        # -- the opportunity itself ------------------------------------
        _d(
            name="opportunity.problem",
            group="opportunity",
            target_type="Opportunity",
            property="problem",
            decision_impact=0.8,
            resolvability=0.9,
            description="The problem the opportunity exists to solve.",
        ),
        _d(
            name="opportunity.proposed_solution",
            group="opportunity",
            target_type="Opportunity",
            property="proposed_solution",
            decision_impact=0.7,
            resolvability=0.9,
            description="What is actually being built or backed.",
        ),
        _d(
            name="opportunity.target_customer",
            group="opportunity",
            target_type="Opportunity",
            property="target_customer",
            decision_impact=0.6,
            resolvability=0.8,
            description="Who pays, or who benefits enough that someone will.",
        ),
        _d(
            name="opportunity.significance",
            group="opportunity",
            target_type="Opportunity",
            property="significance",
            decision_impact=0.6,
            resolvability=0.5,
            description="What changes in the world if this works.",
        ),
        _d(
            name="opportunity.novelty",
            group="opportunity",
            target_type="Opportunity",
            property="novelty",
            decision_impact=0.5,
            resolvability=0.5,
            description="Why this is not simply available already.",
        ),
        _d(
            name="opportunity.maturity",
            group="opportunity",
            target_type="Opportunity",
            property="stage",
            decision_impact=0.5,
            resolvability=0.9,
            description="How far along it is.",
        ),
        # -- human x AI synergy ----------------------------------------
        _d(
            name="synergy.human_contribution",
            group="synergy",
            target_type="Opportunity",
            property="human_contribution",
            decision_impact=0.8,
            resolvability=0.6,
            evidence_required=True,
            required_evidence=("what the people do that the model cannot",),
            description="What the human uniquely contributes.",
        ),
        _d(
            name="synergy.ai_contribution",
            group="synergy",
            target_type="Opportunity",
            property="ai_contribution",
            decision_impact=0.8,
            resolvability=0.7,
            evidence_required=True,
            required_evidence=("what the system does that people cannot at this cost",),
            description="What the AI uniquely contributes.",
        ),
        _d(
            name="synergy.why_human_alone_insufficient",
            group="synergy",
            target_type="Opportunity",
            property="why_human_alone_insufficient",
            decision_impact=0.7,
            resolvability=0.6,
            description="Why people on their own do not solve this.",
        ),
        _d(
            name="synergy.why_ai_alone_insufficient",
            group="synergy",
            target_type="Opportunity",
            property="why_ai_alone_insufficient",
            decision_impact=0.7,
            resolvability=0.6,
            description="Why a model on its own does not solve this either.",
        ),
        # -- asymmetry --------------------------------------------------
        _d(
            name="asymmetry.upside",
            group="asymmetry",
            target_type="Opportunity",
            property="upside",
            decision_impact=1.0,
            resolvability=0.6,
            numeric=True,
            evidence_required=True,
            required_evidence=("comparable outcomes", "addressable spend"),
            description="The plausible upside if it works.",
        ),
        _d(
            name="asymmetry.downside",
            group="asymmetry",
            target_type="Opportunity",
            property="downside",
            decision_impact=1.0,
            resolvability=0.8,
            numeric=True,
            evidence_required=True,
            required_evidence=("cost of participation", "recoverable value on failure"),
            description="What is actually at risk if it does not.",
        ),
        _d(
            name="asymmetry.cost_of_participation",
            group="asymmetry",
            target_type="Opportunity",
            property="cost_of_participation",
            decision_impact=0.6,
            resolvability=0.9,
            numeric=True,
            description="What taking part costs before any outcome.",
        ),
        _d(
            name="asymmetry.time_required",
            group="asymmetry",
            target_type="Opportunity",
            property="time_required",
            decision_impact=0.4,
            resolvability=0.8,
            description="How long participation ties up attention.",
        ),
        # -- technology --------------------------------------------------
        _d(
            name="technology.success_probability",
            group="technology",
            target_type="Technology",
            property="success_probability",
            decision_impact=0.9,
            resolvability=0.5,
            numeric=True,
            evidence_required=True,
            required_evidence=("trial results", "deployments at comparable scale"),
            description="The odds the technology does what it claims.",
        ),
        _d(
            name="technology.maturity",
            group="technology",
            target_type="Technology",
            property="maturity",
            decision_impact=0.5,
            resolvability=0.8,
            description="How proven the core technology is.",
        ),
        _d(
            name="technology.defensibility",
            group="technology",
            target_type="Technology",
            property="defensibility",
            decision_impact=0.7,
            resolvability=0.3,
            evidence_required=True,
            required_evidence=("patents", "data or distribution advantage"),
            description="What stops the obvious competitor copying it.",
        ),
        _d(
            name="technology.bottleneck",
            group="technology",
            target_type="Technology",
            property="bottleneck",
            decision_impact=0.5,
            resolvability=0.6,
            description="What the whole thing waits on.",
        ),
        # -- people and execution ------------------------------------------
        _d(
            name="people.execution_probability",
            group="people",
            target_type="Company",
            property="execution_probability",
            decision_impact=1.0,
            resolvability=0.6,
            numeric=True,
            evidence_required=True,
            required_evidence=(
                "founder operating history",
                "previous ventures",
                "delivery record",
            ),
            description="The odds this team ships what it says it will.",
        ),
        _d(
            name="people.expertise",
            group="people",
            target_type="Person",
            property="expertise",
            decision_impact=0.6,
            resolvability=0.8,
            description="The relevant expertise of the key people.",
        ),
        _d(
            name="people.execution_history",
            group="people",
            target_type="Person",
            property="execution_history",
            decision_impact=0.7,
            resolvability=0.6,
            evidence_required=True,
            required_evidence=("what they have previously delivered",),
            description="What they have already done, not what they intend.",
        ),
        # -- market ----------------------------------------------------------
        _d(
            name="market.adoption_probability",
            group="market",
            target_type="Market",
            property="adoption_probability",
            decision_impact=0.9,
            resolvability=0.5,
            numeric=True,
            evidence_required=True,
            required_evidence=("procurement behaviour", "comparable adoption curves"),
            description="The odds the market takes it up in the window that matters.",
        ),
        _d(
            name="market.addressable_market",
            group="market",
            target_type="Market",
            property="addressable_market",
            decision_impact=0.6,
            resolvability=0.6,
            numeric=True,
            description="How much spend is actually reachable.",
        ),
        _d(
            name="market.competitors",
            group="market",
            target_type="Market",
            property="competitors",
            decision_impact=0.5,
            resolvability=0.7,
            description="Who else is already in the way.",
        ),
        _d(
            name="market.regulatory_factors",
            group="market",
            target_type="Market",
            property="regulatory_factors",
            decision_impact=0.6,
            resolvability=0.7,
            description="What a regulator can do to this.",
        ),
        _d(
            name="market.timing",
            group="market",
            target_type="Market",
            property="timing",
            decision_impact=0.5,
            resolvability=0.4,
            description="Why now rather than three years ago or hence.",
        ),
        # -- access -----------------------------------------------------------
        _d(
            name="access.access_path",
            group="access",
            target_type="Opportunity",
            property="access_path",
            decision_impact=0.8,
            resolvability=0.7,
            description="How we could take part at all.",
        ),
        # -- judgment ----------------------------------------------------------
        _d(
            name="judgment.invalidation_conditions",
            group="judgment",
            target_type="Opportunity",
            property="invalidation_conditions",
            decision_impact=0.6,
            resolvability=0.7,
            description="What would tell us we are wrong.",
        ),
    ),
)

__all__ = [
    "ASYMMETRY_SPECIFICATION",
    "AnalysisSpecification",
    "Dimension",
    "GROUPS",
]
