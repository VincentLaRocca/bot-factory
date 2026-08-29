# bot-factory

Minimal reference implementation of **AIOP** — the AI Object Protocol: a
dependency-free Python core for objects that carry their own types, relations,
lifecycle state and provenance, and serialise to JSON-LD.

Core is universal. It knows nothing about `Person`, `owns` or `Calculation`:
domain vocabulary and rules live in a **profile** above Core — including on the
wire, where `aiop/context.jsonld` defines the envelope and
`profiles/context.jsonld` the demo vocabulary, and documents compose the two.

On top of Core sits the **object store and cluster layer**: objects go in, are
indexed in both directions, and are assembled on demand into the temporary
cluster that answers a particular question. A cluster owns nothing — it holds
identifiers and resolves the store's own instances.

This is **AIOP Core v0.1** plus **Store + Graph/Cluster v0.1**.

## Layout

```
aiop/         universal core: object, relation, provenance, state, validation,
              context.jsonld (envelope terms only)
store/        repository, relation index, traversal, View, ObjectCluster and
              the cluster context.jsonld — domain-neutral, Core-agnostic
profiles/     domain layer — the demo profile, its views and context.jsonld,
              used by examples and tests
examples/     a connected sample graph, plus world/ — the demonstration world
tests/        core, validation, relationship, store and cluster suites
docs/         AIOP_CORE.md, AIOP_STORE.md — the protocol and the layer above it
demo.py       assembles and prints the demonstration clusters
```

## Install

```bash
pip install -e ".[dev]"
```

Python 3.9+, no runtime dependencies.

## Quick start

```python
from aiop import AIOPObject, Provenance, State, validate_object
from profiles import DEMO_PROFILE

ada = AIOPObject(types=["Person", "Agent"], id="urn:aiop:person:ada")
ada.set("name", "Ada Okafor").transition(State.ACTIVE)
ada.attest(Provenance(agent="urn:aiop:agent:onboarding-bot", confidence=1.0))

biscuit = AIOPObject(types=["Dog", "Animal"], properties={"name": "Biscuit", "breed": "Border Collie"})
ada.relate("owns", biscuit, since="2022-06-01")

validate_object(ada, DEMO_PROFILE).raise_for_errors()
print(ada.to_jsonld())
```

An object may declare several types; profile requirements accumulate across all
of them. Validation without a profile checks the protocol envelope only, so a
type Core has never heard of is perfectly valid.

Load and check the bundled graph:

```python
import json, pathlib
from aiop import AIOPObject, validate_graph
from profiles import DEMO_PROFILE

objects = [
    AIOPObject.from_jsonld(json.loads(p.read_text()))
    for p in pathlib.Path("examples").glob("*.jsonld")
]
assert validate_graph(objects, profile=DEMO_PROFILE).is_valid
```

## Clusters

```python
from profiles import ASYMMETRY_VIEW
from store import ObjectStore

store = ObjectStore()
store.load(documents)                       # JSON-LD in, objects out
cluster = store.cluster("urn:aiop:opportunity:harbour-q2-retrofit", ASYMMETRY_VIEW)

cluster.objects()[0] is store.get(cluster.ids[0])   # True — nothing is copied
print(cluster.to_json())                            # deterministic JSON-LD
```

A `View` says how far to walk, in which direction, and across which predicates
and types; views are questions, so they live in the profile. `demo.py` runs the
four demonstration clusters (character, asymmetry, a Scout-local walk that never
touches the commercial half of the graph, and calculation lineage).

## Test

```bash
pytest
```

## Docs

[docs/AIOP_CORE.md](docs/AIOP_CORE.md) covers the Core/profile split (modules
and contexts), multiple `@type` values, the recursive `Story → Character → Dog`
composition pattern, per-variable calculation lineage, the state machine, and
provenance — where each attestation keeps its own confidence and Core never
combines them.

[docs/AIOP_STORE.md](docs/AIOP_STORE.md) covers the store interface, relation
indexing, traversal and views, version awareness, and the cluster envelope.
