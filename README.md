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

Above both sits the **calculation and reasoning layer**: a calculation declares
which properties of which objects it consumes, and evaluating it produces
another Information Object with full lineage. When an input moves, the results
that read it are found by index and recomputed — the old conclusion superseded,
not overwritten.

This is **AIOP Core v0.1**, **Store + Graph/Cluster v0.1** and **Calculation &
Reasoning v0.1**.

## Layout

```
aiop/         universal core: object, relation, provenance, state, validation,
              context.jsonld (envelope terms only)
store/        repository, relation index, traversal, View, ObjectCluster and
              the cluster context.jsonld — domain-neutral, Core-agnostic
reasoning/    bindings, the named-function registry, calculation evaluation,
              fingerprints, staleness and the engine — no domain vocabulary
profiles/     domain layer — the demo profile, its views, its calculation
              schema and formulas, and context.jsonld
examples/     a connected sample graph, plus world/ — the demonstration world —
              and reasoning/, the market and calculation it is valued with
tests/        core, validation, relationship, store, cluster and reasoning suites
docs/         AIOP_CORE.md, AIOP_STORE.md, AIOP_REASONING.md
demo.py       assembles the clusters, then calculates on them
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
demonstration clusters (character, asymmetry, a Scout-local walk that never
touches the commercial half of the graph, calculation lineage, and the valuation
cluster an expected value is calculated from).

## Calculations

```python
from profiles import DEMO_CALCULATION_SCHEMA, DEMO_FUNCTIONS
from reasoning import ReasoningEngine

engine = ReasoningEngine(store, DEMO_FUNCTIONS, DEMO_CALCULATION_SCHEMA)
result = engine.evaluate("urn:aiop:calculation:harbour-q2-asymmetry")

result.get("value")                 # 193273.2 — five properties of four objects
store.get(result.id) is result      # True — a conclusion is an ordinary object

new_evidence(store)                 # execution_probability 0.62 -> 0.74
engine.invalidated_by(COMPANY)      # [result] — an index lookup, not a scan
engine.recompute_stale()            # [292616.4], and the old result superseded
```

A calculation names a function in a registry; no stored text is ever executed.
Each result carries a fingerprint of the inputs it was computed from, which is
what makes staleness a comparison rather than a guess.

## The Asymmetry Analyst

```python
from agents.asymmetry import AsymmetryAnalyst

analyst = AsymmetryAnalyst(store, research=provider)
run = analyst.run("urn:aiop:opportunity:clinical-triage")

run.completeness.score                     # 0.71, and which dimensions are missing
run.gaps                                   # InformationGap objects, ranked
run.assessment.get("recommended_action")   # INVESTIGATE_INVESTMENT
```

The first agent, and it owns no knowledge: given an `@id` it assembles its own
bounded cluster, marks each dimension KNOWN / UNSUPPORTED / UNKNOWN /
UNREACHABLE, writes the gaps out as objects, researches them through a
`ResearchProvider` boundary (no model vendor anywhere in the package), turns
findings into Evidence and Claims, asks the reasoning layer for the arithmetic,
and writes an Assessment with full lineage plus an ExecutionRecord. New
evidence supersedes a claim, stales the results and replaces the assessment
rather than editing it. `python3 demo_asymmetry.py` runs the whole thing.

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

[docs/AIOP_REASONING.md](docs/AIOP_REASONING.md) covers bindings, the named
function registry, results as first-class objects, input fingerprints,
index-driven invalidation, and recomputation by supersession.

[docs/ASYMMETRY_ANALYST.md](docs/ASYMMETRY_ANALYST.md) covers the analyst: the
dimension catalogue, the four epistemic states, ranked information gaps, the
research and reasoning boundaries, claim supersession, and assessment
fingerprints.
