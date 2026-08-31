"""The research application profile: the vocabulary investigation writes in.

Deliberately not a new claim system. A ``Claim`` here is the analyst's Claim —
same term, same IRI, same required properties — and a ``Claim`` the researcher
proposes is a claim the Asymmetry Analyst can already read. What this profile
adds is where a piece of evidence *came from*: a source, its kind, its date and
the lineage group it belongs to, which is what a future validator will need in
order to decide that three articles quoting one wire story are one source.

The status vocabularies are two, and the difference is the point:

* ``EPISTEMIC_STATES`` describe a research topic — what investigation was able
  to establish, including that it established nothing.
* ``CLAIM_STATES`` describe a proposition — whether the evidence gathered
  stands behind it, disagrees about it, or is not there.

Neither includes ``ACCEPTED``. Accepting a claim is a judgement about how far
evidence should be trusted, and that belongs to the validator that does not
exist yet.
"""

from pathlib import Path

from aiop import CONTEXT_URI, Profile, Vocabulary

from .demo import DEMO_CONTEXT_URI, REQUIRED_PROPERTIES, VERSION_PREDICATE
from .observer import (
    OBSERVER_CONTEXT_URI,
    OBSERVER_REQUIRED_PROPERTIES,
    OBSERVER_VOCABULARY,
)

#: Where this profile publishes its JSON-LD context, and its local copy.
RESEARCH_CONTEXT_URI = "https://aiop.dev/profiles/research/context.jsonld"
RESEARCH_CONTEXT_FILE = Path(__file__).with_name("research-context.jsonld")

#: Research documents compose four: envelope, world, observer, research.
RESEARCH_CONTEXT = [
    CONTEXT_URI,
    DEMO_CONTEXT_URI,
    OBSERVER_CONTEXT_URI,
    RESEARCH_CONTEXT_URI,
]

#: What v0.1 investigation asks about, in the order it asks. A fixed list is
#: the honest v0.1 answer: autonomous question generation is a later problem,
#: and a template that never varies is a template whose output is comparable.
TOPICS = ("event_verification", "cause", "context", "alternative")

#: What investigation was able to establish about a topic. The same four words
#: the analyst's completeness check uses, because they mean the same things —
#: and because "we looked and could not tell" must remain sayable.
EPISTEMIC_STATES = ("KNOWN", "UNSUPPORTED", "UNKNOWN", "UNREACHABLE")

#: Where a proposition stands with the evidence now attached to it.
CLAIM_STATES = ("SUPPORTED", "CONTESTED", "UNSUPPORTED")

#: How a piece of evidence bears on a claim. Disagreement is a stance, not an
#: error to be resolved before storage.
STANCES = ("supports", "contradicts", "qualifies")

RESEARCH_VOCABULARY = Vocabulary(
    inverses={
        **OBSERVER_VOCABULARY.inverses,
        "supports": "supportedBy",
        "contradicts": "contradictedBy",
        "qualifies": "qualifiedBy",
        "investigatedFrom": "investigatedBy",
    },
    symmetric=frozenset(OBSERVER_VOCABULARY.symmetric),
)

#: Evidence must say where it came from, or it is an opinion with a URN.
RESEARCH_REQUIRED_PROPERTIES = {
    "Evidence": ["title", "source", "source_type", "dimension", "stance"],
    "Claim": ["statement", "dimension", "status"],
}

RESEARCH_PROFILE = Profile(
    name="research",
    required_properties={
        **REQUIRED_PROPERTIES,
        **OBSERVER_REQUIRED_PROPERTIES,
        **RESEARCH_REQUIRED_PROPERTIES,
    },
    known_types=(
        set(REQUIRED_PROPERTIES)
        | set(OBSERVER_REQUIRED_PROPERTIES)
        | set(RESEARCH_REQUIRED_PROPERTIES)
    ),
    vocabulary=RESEARCH_VOCABULARY,
)

__all__ = [
    "CLAIM_STATES",
    "EPISTEMIC_STATES",
    "RESEARCH_CONTEXT",
    "RESEARCH_CONTEXT_FILE",
    "RESEARCH_CONTEXT_URI",
    "RESEARCH_PROFILE",
    "RESEARCH_REQUIRED_PROPERTIES",
    "RESEARCH_VOCABULARY",
    "STANCES",
    "TOPICS",
    "VERSION_PREDICATE",
]
