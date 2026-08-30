"""The neighbourhoods the analyst is allowed to read.

An analyst that loads the whole graph has not understood the question. Each
view here is a bounded, purpose-driven walk: the analysis view gathers what an
opportunity is judged on, the dossier view adds what the analyst itself has
already written about it, and the support view answers "what stands behind this
one object?".
"""

from store import Direction, View

#: The types an asymmetry analysis is permitted to pull in. Narrative objects
#: are not among them: Sarah may be a Character, but the character is not
#: evidence of anything commercial.
ANALYSIS_TYPES = frozenset(
    {
        "Opportunity",
        "Company",
        "Person",
        "Technology",
        "Market",
        "Evidence",
        "Claim",
        "Calculation",
        "Result",
    }
)

#: The graph edges worth crossing to understand an opportunity.
ANALYSIS_PREDICATES = frozenset(
    {
        "enables",
        "enabledBy",
        "owns",
        "ownedBy",
        "develops",
        "developedBy",
        "worksFor",
        "employs",
        "founded",
        "foundedBy",
        "supports",
        "supportedBy",
        "contradicts",
        "contradictedBy",
        "qualifies",
        "qualifiedBy",
        "about",
        "subjectOf",
        "derivedFrom",
        "sourceOf",
        "addresses",
    }
)

#: What the opportunity is judged on: the company behind it, the people in the
#: company, the technology, the market, and the evidence under all of it.
ANALYSIS_VIEW = View(
    name="asymmetry-analysis",
    depth=3,
    direction=Direction.BOTH,
    predicates=ANALYSIS_PREDICATES,
    types=ANALYSIS_TYPES,
    description="Everything an asymmetric opportunity is judged on.",
)

#: The same neighbourhood plus the analyst's own output: gaps, assessments and
#: the records of previous runs.
DOSSIER_VIEW = ANALYSIS_VIEW.narrow(
    name="asymmetry-dossier",
    types=ANALYSIS_TYPES
    | {"InformationGap", "Assessment", "SynergyAssessment", "OurEdge", "ExecutionRecord"},
    description="The analysis neighbourhood plus what the analyst has said about it.",
)

#: What stands behind a single object: the evidence and claims pointing at it.
SUPPORT_VIEW = View(
    name="support",
    depth=1,
    direction=Direction.IN,
    predicates={"supports", "contradicts", "qualifies", "about"},
    description="The evidence and claims bearing on one object.",
)

ANALYSIS_VIEWS = {
    view.name: view for view in (ANALYSIS_VIEW, DOSSIER_VIEW, SUPPORT_VIEW)
}

__all__ = [
    "ANALYSIS_PREDICATES",
    "ANALYSIS_TYPES",
    "ANALYSIS_VIEW",
    "ANALYSIS_VIEWS",
    "DOSSIER_VIEW",
    "SUPPORT_VIEW",
]
