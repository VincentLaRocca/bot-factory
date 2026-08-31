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

Above all of it sits the **Observer motherboard**: a chassis with an identity,
slots, a mission and an explicit grant of authority, into which domain
intelligence is installed as an interchangeable **capability**. The chassis
knows no domain, and neither the first capability — the Anomaly Listener — nor
the second — the Researcher, which consumes the first one's output — required a
line of change to it.

This is **AIOP Core v0.1**, **Store + Graph/Cluster v0.1**, **Calculation &
Reasoning v0.1**, **Observer + Anomaly Listener v0.1** and **Researcher v0.1**.

## Layout

```
aiop/         universal core: object, relation, provenance, state, validation,
              context.jsonld (envelope terms only)
store/        repository, relation index, traversal, View, ObjectCluster and
              the cluster context.jsonld — domain-neutral, Core-agnostic
reasoning/    bindings, the named-function registry, calculation evaluation,
              fingerprints, staleness and the engine — no domain vocabulary
observer/     the motherboard — identity, capability registry, missions,
              authority, invocation and execution records; no domain anywhere
capabilities/ interchangeable plug-ins — anomaly/ detects, research/
              investigates what anomaly/ produced
agents/       the Asymmetry Analyst, built on the layers below
profiles/     domain layer — the demo, asymmetry, observer and research
              profiles, their views, calculation schemas and formulas, and
              the contexts
examples/     a connected sample graph, plus world/ — the demonstration world —
              reasoning/, asymmetry/, observer/ and research/
tests/        core, validation, relationship, store, cluster, reasoning,
              asymmetry, observer and researcher suites
docs/         AIOP_CORE.md, AIOP_STORE.md, AIOP_REASONING.md,
              ASYMMETRY_ANALYST.md, OBSERVER.md, RESEARCHER.md, DECISIONS.md
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

## The Observer motherboard

```python
observer = Observer("watchtower", store=store, authority=INTERNAL_AUTHORITY)
observer.install(AnomalyListener())          # a plug-in, not a subclass
observer.assign(mission)                     # refused if a capability is absent

result = observer.invoke("anomaly_listener", inputs=[observation])
result.findings["disposition"]               # 'ESCALATE'
result.record.get("authority")               # what it was actually allowed to do
```

```
Agent = Observer + Capabilities + Mission + Authority + Resources
```

The chassis knows identity, slots, purpose, permission and how to write down
what happened — and nothing about anomalies, medicine or the web. Authority
composes by intersection, so a mission can only narrow a charter, never widen
it: an observer holding the listener but not `CREATE_OBJECT` is refused, and
the refusal is recorded rather than raised.

The Anomaly Listener keeps no memory of its own; it reads history out of the
store, so the same reading against a different past gives a different answer.
It produces an `Anomaly` — a trigger with its arithmetic attached — never an
`Opportunity`. `python3 demo_observer.py` runs the whole arc.

## The second capability, in the same slots

```python
desk.install(Researcher(provider))            # no chassis change, no subclass
found = desk.invoke("researcher", inputs=[anomaly])

found.findings["investigations"][0]["topics"]  # {'cause': 'UNSUPPORTED', ...}
```

The Researcher consumes an `Anomaly` and files what sources said as `Evidence`,
with `Claim` objects for the propositions that evidence bears on — through a
vendor-neutral `ResearchProvider` boundary with no network on this side of it.
It never writes a value onto the target object: `Source → Evidence → Claim` is
as far as a source's word travels. Two filings say *reverse split*, a newswire
says *breakthrough*, and the claim stays `CONTESTED` with all three kept. Where
nobody answered, the topic stays `UNKNOWN`; where nobody could be asked, it is
`UNREACHABLE`. `python3 demo_researcher.py` runs the whole arc.

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

[docs/OBSERVER.md](docs/OBSERVER.md) covers the motherboard: capability cards
and the registry, sensors versus capabilities, authority as intersection,
missions and readiness, observation endpoints and independence groups, the six
anomaly dimensions actually implemented, and execution records.

[docs/RESEARCHER.md](docs/RESEARCHER.md) covers the researcher: the
`Source → Evidence → Claim` ordering, the provider boundary and its fixed
question template, contradiction and the four epistemic states, digest identity
and repeated runs, and the negative test that keeps the chassis ignorant.

[docs/DECISIONS.md](docs/DECISIONS.md) records the decisions worth arguing
with: why assessments carry their own input fingerprint instead of generalising
staleness in `reasoning/`, why an accepted claim enriches its target object in
place instead of superseding it, why authority composes by intersection, and
why an anomaly score is its strongest dimension rather than a blend, and why
the researcher reuses the analyst's Claim vocabulary instead of inventing a
second one.
