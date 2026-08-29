"""The demo profile exercised by ``examples/`` and the test-suite.

It is an ordinary application profile: nothing here is privileged, and Core
behaves identically without it.
"""

from pathlib import Path

from aiop import CONTEXT_URI, Profile, Vocabulary

#: Where this profile publishes its JSON-LD context, and its local copy.
DEMO_CONTEXT_URI = "https://aiop.dev/profiles/demo/context.jsonld"
DEMO_CONTEXT_FILE = Path(__file__).with_name("context.jsonld")

#: Documents using this profile compose the Core context with the demo one.
DEMO_CONTEXT = [CONTEXT_URI, DEMO_CONTEXT_URI]

DEMO_VOCABULARY = Vocabulary(
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
        "supersedes": "supersededBy",
    },
    symmetric=frozenset({"relatedTo", "siblingOf", "colleagueOf"}),
)

#: Property requirements per type. An object declaring several types must
#: satisfy the union of their requirements.
REQUIRED_PROPERTIES = {
    "Agent": ["name"],
    "Animal": ["name"],
    "Person": ["name"],
    "Dog": ["breed"],
    "Story": ["title"],
    "Character": ["name"],
    "Company": ["name"],
    "Policy": ["rate"],
    "Opportunity": ["title", "value"],
    "Technology": ["name"],
    "Evidence": ["title"],
    "Calculation": ["expression", "inputs", "result"],
}

#: The edge a newer object uses to point at the one it replaces. The store
#: takes this as configuration; the word itself is profile vocabulary.
VERSION_PREDICATE = "supersedes"

DEMO_PROFILE = Profile(
    name="demo",
    required_properties=REQUIRED_PROPERTIES,
    known_types=set(REQUIRED_PROPERTIES),
    vocabulary=DEMO_VOCABULARY,
)
