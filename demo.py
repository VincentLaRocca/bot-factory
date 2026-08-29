"""Assemble the demonstration clusters and print them.

    python demo.py            # summaries
    python demo.py --json     # the deterministic asymmetry cluster document
"""

import json
import sys
from pathlib import Path

from aiop import AIOPObject
from profiles import ASYMMETRY_VIEW, CHARACTER_VIEW, LINEAGE_VIEW, VERSION_PREDICATE
from store import ObjectStore

WORLD = Path(__file__).parent / "examples" / "world"
SARAH = "urn:aiop:person:sarah"
SCOUT = "urn:aiop:animal:scout"
OPPORTUNITY = "urn:aiop:opportunity:harbour-q2-retrofit"
CALCULATION = "urn:aiop:calculation:harbour-q2-expected-value"


def load_world() -> ObjectStore:
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    for path in sorted(WORLD.glob("*.jsonld")):
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
    ]

    if "--json" in sys.argv:
        print(clusters[1].to_json())
        return

    for cluster in clusters:
        describe(cluster)


if __name__ == "__main__":
    main()
