"""Asymmetry Analyst v0.1: the first process to reason over AIOP.

The analyst is an application on top of the stack, not a layer in it. It reads
Information Objects, works out what it does not know, asks for evidence, runs
the calculations whose inputs exist, and writes its conclusions back as more
Information Objects. It stores no knowledge of its own: when the run ends,
everything it learned is in the graph, addressable by anything else.

```python
from agents.asymmetry import AsymmetryAnalyst, MockResearchProvider

analyst = AsymmetryAnalyst(store, research=MockResearchProvider(findings))
run = analyst.run("urn:aiop:opportunity:clinical-triage")
run.assessment.get("recommended_action")
```

The rule the whole package is built around: **unknown is acceptable, guessing
is not.** A missing input stops a calculation; it never gets a plausible value.
"""

from .analyst import AGENT, VERSION, AnalysisRun, AsymmetryAnalyst, cluster_fingerprint
from .assessment import (
    ESTABLISHED,
    NO_IDENTIFIED_EDGE,
    PARTIAL,
    UNKNOWN,
    DeterministicAnalyst,
    Dossier,
    Judgement,
    ReasoningProvider,
    Verdict,
    current_assessments,
    is_stale,
    our_edge,
    synergy,
)
from .claims import ACCEPTED, CONTESTED, UNSUPPORTED, ClaimOutcome, claim_id, contested
from .completeness import Completeness, Finding, Status, assess
from .gaps import Ranking, discover, gap_id, rank
from .policy import ACTIONS, CAUTIOUS_POLICY, DEFAULT_POLICY, AnalysisPolicy
from .research import (
    ChainedResearchProvider,
    MockResearchProvider,
    NoResearchProvider,
    ResearchProvider,
    StoreResearchProvider,
    evidence,
)
from .specification import ASYMMETRY_SPECIFICATION, AnalysisSpecification, Dimension
from .views import ANALYSIS_VIEW, DOSSIER_VIEW, SUPPORT_VIEW

__all__ = [
    "ACCEPTED",
    "ACTIONS",
    "AGENT",
    "ANALYSIS_VIEW",
    "ASYMMETRY_SPECIFICATION",
    "AnalysisPolicy",
    "AnalysisRun",
    "AnalysisSpecification",
    "AsymmetryAnalyst",
    "CAUTIOUS_POLICY",
    "CONTESTED",
    "ChainedResearchProvider",
    "ClaimOutcome",
    "Completeness",
    "DEFAULT_POLICY",
    "DOSSIER_VIEW",
    "DeterministicAnalyst",
    "Dimension",
    "Dossier",
    "ESTABLISHED",
    "Finding",
    "Judgement",
    "MockResearchProvider",
    "NO_IDENTIFIED_EDGE",
    "NoResearchProvider",
    "PARTIAL",
    "Ranking",
    "ReasoningProvider",
    "ResearchProvider",
    "SUPPORT_VIEW",
    "Status",
    "StoreResearchProvider",
    "UNKNOWN",
    "UNSUPPORTED",
    "VERSION",
    "Verdict",
    "assess",
    "claim_id",
    "cluster_fingerprint",
    "contested",
    "current_assessments",
    "discover",
    "evidence",
    "gap_id",
    "is_stale",
    "our_edge",
    "rank",
    "synergy",
]
