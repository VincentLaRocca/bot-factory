"""The asymmetry application profile: the vocabulary an analyst reasons in.

This is the layer between the generic calculation machinery and the Asymmetry
Analyst itself. It says what a ``Claim``, an ``InformationGap`` or an
``Assessment`` is called and what such an object must carry; the analyst above
decides when to make one, and the layers below never hear about any of it.

The formulas live here for the same reason expected value does: an asymmetry
score is a modelling decision about opportunities, not a truth about objects.
"""

from pathlib import Path

from aiop import CONTEXT_URI, Profile, Vocabulary
from reasoning import FunctionRegistry

from .calculations import DEMO_CALCULATION_SCHEMA, DEMO_FUNCTIONS
from .demo import DEMO_CONTEXT_URI, REQUIRED_PROPERTIES, VERSION_PREDICATE

#: Where this profile publishes its JSON-LD context, and its local copy.
ASYMMETRY_CONTEXT_URI = "https://aiop.dev/profiles/asymmetry/context.jsonld"
ASYMMETRY_CONTEXT_FILE = Path(__file__).with_name("asymmetry-context.jsonld")

#: Analysis documents compose all three contexts: envelope, world, analysis.
ASYMMETRY_CONTEXT = [CONTEXT_URI, DEMO_CONTEXT_URI, ASYMMETRY_CONTEXT_URI]

#: The calculation vocabulary is the demo one: an analyst writing results in a
#: dialect of its own would be a second reasoning layer, which is the mistake
#: this whole architecture exists to avoid.
ASYMMETRY_CALCULATION_SCHEMA = DEMO_CALCULATION_SCHEMA

ASYMMETRY_VOCABULARY = Vocabulary(
    inverses={
        "owns": "ownedBy",
        "parentOf": "childOf",
        "employs": "worksFor",
        "contains": "partOf",
        "derivedFrom": "sourceOf",
        "authorOf": "authoredBy",
        "portrays": "portrayedBy",
        "develops": "developedBy",
        "enables": "enabledBy",
        "supports": "supportedBy",
        "contradicts": "contradictedBy",
        "qualifies": "qualifiedBy",
        "about": "subjectOf",
        "produced": "producedBy",
        "resolves": "resolvedBy",
        "supersedes": "supersededBy",
    },
    symmetric=frozenset({"relatedTo", "siblingOf", "colleagueOf"}),
)

#: What each analysis type must carry to be worth storing. A gap that does not
#: say how important it is cannot be ranked; an assessment that does not say
#: how confident it is cannot be argued with.
ASYMMETRY_REQUIRED_PROPERTIES = {
    "Claim": ["statement", "dimension", "status"],
    "InformationGap": ["dimension", "status", "importance", "research_priority"],
    "Assessment": ["confidence", "recommended_action", "priority"],
    "SynergyAssessment": ["status", "rationale"],
    "OurEdge": ["status", "rationale"],
    "ExecutionRecord": ["agent", "status", "started_at"],
}

ASYMMETRY_PROFILE = Profile(
    name="asymmetry",
    required_properties={**REQUIRED_PROPERTIES, **ASYMMETRY_REQUIRED_PROPERTIES},
    known_types=set(REQUIRED_PROPERTIES) | set(ASYMMETRY_REQUIRED_PROPERTIES),
    vocabulary=ASYMMETRY_VOCABULARY,
)

ASYMMETRY_ONLY_FUNCTIONS = FunctionRegistry()


@ASYMMETRY_ONLY_FUNCTIONS.function(
    "asymmetry_score",
    description=(
        "How lopsided the bet is once probability is taken into account: the "
        "probability-weighted upside as a multiple of the probability-weighted "
        "downside. Above 1 the good case outweighs the bad."
    ),
)
def asymmetry_score(
    upside: float,
    downside: float,
    execution_probability: float,
    success_probability: float,
    adoption_probability: float,
) -> float:
    """The payoff ratio after the probability of getting there."""
    probability = execution_probability * success_probability * adoption_probability
    if downside <= 0 or probability >= 1.0:
        raise ValueError("asymmetry_score needs a positive downside and a probability below 1")
    return (upside * probability) / (downside * (1.0 - probability))


@ASYMMETRY_ONLY_FUNCTIONS.function(
    "execution_adjusted_upside",
    description="The upside discounted by the odds the team actually delivers it.",
)
def execution_adjusted_upside(upside: float, execution_probability: float) -> float:
    """What the good case is worth given who is building it."""
    return upside * execution_probability


#: Everything an asymmetry calculation may name: the world's formulas plus
#: this profile's own.
ASYMMETRY_FUNCTIONS = DEMO_FUNCTIONS.extend(ASYMMETRY_ONLY_FUNCTIONS)

__all__ = [
    "ASYMMETRY_CALCULATION_SCHEMA",
    "ASYMMETRY_CONTEXT",
    "ASYMMETRY_CONTEXT_FILE",
    "ASYMMETRY_CONTEXT_URI",
    "ASYMMETRY_FUNCTIONS",
    "ASYMMETRY_PROFILE",
    "ASYMMETRY_REQUIRED_PROPERTIES",
    "ASYMMETRY_VOCABULARY",
    "VERSION_PREDICATE",
    "asymmetry_score",
    "execution_adjusted_upside",
]
