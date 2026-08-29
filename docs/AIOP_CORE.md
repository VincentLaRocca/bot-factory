# AIOP Core

AIOP (AI Object Protocol) is a small, dependency-free way to describe *things*
so that both software and language models can read, extend and audit them.

Every unit of meaning is an **object**. An object knows four things about
itself:

| Concern | Module | Question it answers |
| --- | --- | --- |
| Identity & content | `aiop.object` | *What is this?* |
| Relations | `aiop.relation` | *How does it connect to other things?* |
| State | `aiop.state` | *Where is it in its lifecycle?* |
| Provenance | `aiop.provenance` | *Who said so, how, and how sure are they?* |

## Core and profiles

Core is universal and carries **no domain vocabulary**. It does not know what
a `Person` is, that `owns` has an inverse, or that a `Calculation` needs a
result. It validates the protocol envelope — identity, types, state, the shape
of relations and provenance, graph integrity — and stops there.

Everything domain-specific is a **profile** layered above Core:

```python
from aiop import Profile, Vocabulary

DEMO_PROFILE = Profile(
    name="demo",
    required_properties={"Person": ["name"], "Dog": ["breed"]},
    known_types={"Person", "Dog"},
    vocabulary=Vocabulary(inverses={"owns": "ownedBy"}, symmetric=frozenset({"relatedTo"})),
)
```

Validation takes a profile; without one it applies Core rules only. Types and
predicates a profile does not declare are warnings, never errors, so a document
can carry vocabulary from several profiles at once. `profiles/demo.py` is the
profile used by `examples/` and the test-suite — swap it and Core is untouched.

### Two contexts

The split is the same on the wire. `aiop/context.jsonld` defines only the
envelope (`state`, `relations`, `subject`/`predicate`/`object`, `provenance`,
`agent`, `confidence`, `generatedAt`, …); `profiles/context.jsonld` defines the
demo vocabulary (`Person`, `Dog`, `Character`, `Story`, `Company`,
`Opportunity`, `Calculation`, `owns`, `portrays`, `rate`, …). Documents compose
them:

```json
"@context": [
  "https://aiop.dev/context.jsonld",
  "https://aiop.dev/profiles/demo/context.jsonld"
]
```

An object keeps the context it was parsed with (`obj.context`) and re-emits it,
defaulting to the Core context alone. The test-suite asserts that every term
any example uses resolves in the composed pair, and that no domain term leaks
into the Core context.

## Objects

```python
from aiop import AIOPObject, Provenance, State

ada = AIOPObject(types=["Person", "Agent"], id="urn:aiop:person:ada")
ada.set("name", "Ada Okafor").transition(State.ACTIVE)
ada.attest(Provenance(agent="urn:aiop:agent:onboarding-bot", method="asserted"))
```

### Multiple types

An object carries an **ordered list** of semantic types; `obj.type` is a
convenience for the first (primary) one, and `obj.has_type(name)` tests any of
them. On the wire, `@type` accepts a string or an array, and round-trips in the
form it was given: `["Dog", "Animal"]` stays an array, `"Story"` stays a
scalar. Profile requirements accumulate over every declared type, so a
`["Dog", "Animal"]` object owes the union of both types' properties.

`AIOPObject.from_jsonld` is the exact inverse of `to_jsonld`: reserved keys
(`@id`, `@type`, `state`, `relations`, `provenance`) become fields and
everything else becomes a property. Identifiers are opaque URNs — nothing in
the protocol parses meaning out of one.

## Relations

A relation is a directed triple `subject —predicate→ object`, optionally
carrying attributes (`{"role": "CTO"}`, or the variable binding of a
calculation). Relations live on the subject, so an object always ships with its
outbound edges.

Inverses come from the profile's `Vocabulary`; Core's `EMPTY_VOCABULARY` knows
none, and `relation.inverse()` returns `None` unless a vocabulary is supplied.
Inverses are never implied silently — pass `with_inverse=True` to materialise
them. `RelationGraph` collects edges from many objects and answers `find`,
`neighbours`, `reachable`, `paths`, `subjects_referencing` and `has_cycle`.

### Composition is recursive, never nested

Objects reference each other; they never embed each other. The story in
`examples/` demonstrates the pattern:

```
Story ──contains──▶ Character ──portrays──▶ Dog/Animal
                                              ▲
Person ─────────────────owns──────────────────┘
```

The `Character` is a first-class object with its own identity, state and
provenance, and the animal it portrays is the *same* object the person owns —
independently addressable and reusable by anything else that needs it. Nothing
in this chain is special-cased: each hop is an ordinary object holding ordinary
relations, so the pattern extends to any depth.

## State

```
draft ──▶ proposed ──▶ active ──▶ superseded ──▶ retired
  │           │           │                        ▲
  └───────────┴───────────┴────────────────────────┘
```

Illegal moves raise `InvalidTransition`; `retired` is terminal. `StateMachine`
wraps the same rules and keeps a `StateChange` audit trail with timestamps and
reasons.

## Provenance

Provenance is append-only. Each record names the `agent`, the `method`
(`asserted`, `inferred`, `imported`, `generated`, `computed`, `reviewed`, …),
an optional `source`, a `confidence` in `[0, 1]`, and a UTC timestamp.

`ProvenanceChain` keeps records ordered by time and returns their confidences
untouched (`chain.confidences()`). Core deliberately offers no way to reduce
several attestations to one number: how independent an extraction and its
review really are is a modelling judgement, not a protocol fact, so it belongs
to `Calculation`/`Probability` objects in a profile above Core.

### Lineage of a derived value

A `Calculation` consumes values from several independently addressable objects.
The binding of each variable is explicit — which object, and which property of
it, supplied the value:

```json
"expression": "opportunity_value * commission_rate",
"inputs": [
  {"variable": "opportunity_value", "source": "urn:aiop:opportunity:northwind-q1-retrofit",
   "sourceProperty": "value", "value": 240000},
  {"variable": "commission_rate", "source": "urn:aiop:policy:northwind-commission",
   "sourceProperty": "rate", "value": 0.075}
]
```

The same bindings appear as `derivedFrom` relations carrying `variable` and
`sourceProperty` attributes, so the lineage is traversable from the graph
alone, and one provenance record per source records who bound what. Because
every variable resolves to a live object property, the result is reproducible
from the sources — and demonstrably stale once a source changes. The
test-suite recomputes it both ways.

## Validation

Validation distinguishes **errors** (the document breaks the protocol, or a
profile rule) from **warnings** (usable but suspicious: a missing `@context`,
no attestations, a dangling reference, a type or predicate the profile does not
declare).

```python
from aiop import validate_document, validate_graph
from profiles import DEMO_PROFILE

validate_document(document, DEMO_PROFILE).raise_for_errors()
validate_graph(objects, profile=DEMO_PROFILE)   # duplicate ids, dangling references
```

## Worked example

`examples/` is one connected graph: Ada owns Biscuit, works for Northwind
Robotics and wrote a story whose Collie character portrays that same dog;
Northwind holds a Q1 opportunity and a commission policy, and a calculation
derives the commission from both. Together they exercise multi-typed objects,
every predicate pair, all provenance methods, three lifecycle states and the
full lineage pattern — and `tests/` asserts the graph stays consistent.
