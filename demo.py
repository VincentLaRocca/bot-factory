"""Assemble the demonstration clusters, then calculate on them.

    python demo.py            # summaries
    python demo.py --json     # the deterministic asymmetry cluster document
"""

import json
import sys
from pathlib import Path

from aiop import AIOPObject, Provenance, State
from profiles import (
    ASYMMETRY_VIEW,
    CHARACTER_VIEW,
    DEMO_CALCULATION_SCHEMA,
    DEMO_FUNCTIONS,
    LINEAGE_VIEW,
    VALUATION_VIEW,
    VERSION_PREDICATE,
)
from reasoning import ReasoningEngine
from store import ObjectStore

EXAMPLES = Path(__file__).parent / "examples"
WORLD = EXAMPLES / "world"
REASONING = EXAMPLES / "reasoning"
SARAH = "urn:aiop:person:sarah"
SCOUT = "urn:aiop:animal:scout"
COMPANY = "urn:aiop:company:harbour-forge"
OPPORTUNITY = "urn:aiop:opportunity:harbour-q2-retrofit"
CALCULATION = "urn:aiop:calculation:harbour-q2-expected-value"
EXPECTED_VALUE = "urn:aiop:calculation:harbour-q2-asymmetry"


def load_world() -> ObjectStore:
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    for directory in (WORLD, REASONING):
        for path in sorted(directory.glob("*.jsonld")):
            store.add(AIOPObject.from_jsonld(json.loads(path.read_text())))
    return store


def describe(cluster) -> None:
    print(f"\n{cluster.view.name} view from {cluster.root} — {len(cluster)} objects")
    for obj in cluster:
        depth = cluster.depth_of(obj.id)
        print(f"  {depth}  {'/'.join(obj.types):20} {obj.id}")


def main() -> None:
    store = load_world()
    print(f"{len(store)} objects stored, {len(store.current())} of them current")

    clusters = [
        store.cluster(SARAH, CHARACTER_VIEW),
        store.cluster(OPPORTUNITY, ASYMMETRY_VIEW),
        store.cluster(SCOUT, CHARACTER_VIEW.narrow(depth=1)),
        store.cluster(CALCULATION, LINEAGE_VIEW),
        store.cluster(OPPORTUNITY, VALUATION_VIEW),
    ]

    if "--json" in sys.argv:
        print(clusters[1].to_json())
        return

    for cluster in clusters:
        describe(cluster)

    calculate(store)


def calculate(store: ObjectStore) -> None:
    """Expected value, then the same question after the world moves."""
    engine = ReasoningEngine(store, DEMO_FUNCTIONS, DEMO_CALCULATION_SCHEMA)

    result = engine.evaluate(EXPECTED_VALUE)
    print(f"\nexpected value = {result.get('value'):,.2f}  [{result.id}]")
    for binding in result.get("inputs"):
        print(f"  {binding['variable']:24} {binding['value']:>12}  {binding['source']}")

    audit = AIOPObject(
        types="Evidence",
        id="urn:aiop:evidence:delivery-audit",
        state=State.ACTIVE,
        properties={"title": "Delivery audit of the last four retrofits"},
    )
    audit.attest(Provenance(agent="urn:aiop:agent:analyst", method="observed"))
    audit.relate("supports", COMPANY, fidelity="audited")
    store.add(audit)
    store.get(COMPANY).set("execution_probability", 0.74)
    print(f"\n{audit.id} lands: execution_probability 0.62 -> 0.74")

    for dependent in engine.invalidated_by(COMPANY):
        print(f"  stale: {dependent.id} — {engine.check(dependent).reason}")

    for replacement in engine.recompute_stale():
        print(f"  recomputed = {replacement.get('value'):,.2f}  [{replacement.id}]")

    for version in engine.results_of(EXPECTED_VALUE):
        print(f"  {version.state.value:11} {version.get('value'):>14,.2f}  {version.id}")


if __name__ == "__main__":
    main()
