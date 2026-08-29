"""Demo views: which neighbourhood answers which kind of question.

A view is a question shaped as a filter, and questions are domain-specific, so
they live in the profile. The store knows how to walk; the profile knows where
it is worth walking to.
"""

from store import Direction, View

#: Narrative neighbourhood: the story a person appears in and the creatures
#: and characters around them. Deliberately blind to commerce.
CHARACTER_VIEW = View(
    name="character",
    depth=2,
    direction=Direction.BOTH,
    predicates={
        "contains",
        "partOf",
        "owns",
        "ownedBy",
        "portrays",
        "portrayedBy",
        "authorOf",
        "authoredBy",
    },
    description="The story, characters and animals around a person.",
)

#: The case for an opportunity: what enables it, who is behind it, and what
#: evidence and calculation stand under it.
ASYMMETRY_VIEW = View(
    name="asymmetry",
    depth=3,
    direction=Direction.BOTH,
    predicates={
        "enables",
        "enabledBy",
        "develops",
        "developedBy",
        "worksFor",
        "employs",
        "supports",
        "supportedBy",
        "derivedFrom",
        "sourceOf",
    },
    description="Company, technology, people, evidence and calculations behind an opportunity.",
)

#: Everything an expected-value calculation needs, and nothing narrative. The
#: type filter is what keeps the story out: Sarah is a Person and a Character,
#: and only the Person half is any of this view's business.
VALUATION_VIEW = View(
    name="valuation",
    depth=3,
    direction=Direction.BOTH,
    predicates={
        "enables",
        "enabledBy",
        "develops",
        "developedBy",
        "worksFor",
        "employs",
        "contains",
        "partOf",
        "supports",
        "supportedBy",
        "derivedFrom",
        "sourceOf",
    },
    types={
        "Opportunity",
        "Company",
        "Person",
        "Technology",
        "Market",
        "Evidence",
        "Calculation",
        "Result",
    },
    description="Opportunity, company, person, technology, market and evidence.",
)

#: Where a derived value came from, and nothing else.
LINEAGE_VIEW = View(
    name="lineage",
    depth=1,
    direction=Direction.OUT,
    predicates={"derivedFrom"},
    description="The objects a calculation drew its variables from.",
)

#: The other way down the same edges: what depends on this object, and would
#: have to be recomputed if it changed.
DEPENDENTS_VIEW = View(
    name="dependents",
    depth=1,
    direction=Direction.IN,
    predicates={"derivedFrom"},
    description="The calculations and results that read this object.",
)

DEMO_VIEWS = {
    view.name: view
    for view in (
        CHARACTER_VIEW,
        ASYMMETRY_VIEW,
        VALUATION_VIEW,
        LINEAGE_VIEW,
        DEPENDENTS_VIEW,
    )
}
