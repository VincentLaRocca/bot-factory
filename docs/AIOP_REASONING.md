# AIOP Calculation & Reasoning v0.1

The layer where the graph starts doing intellectual work.

```
Information Object → Store → Relationship Graph → View → Cluster → Calculation → Result
```

A calculation declares what it consumes. Evaluating it produces another
Information Object. Because that result records the values it read and a
fingerprint of them, the system can tell later that it is no longer true — and
because the derivation edges are indexed both ways, it can tell *which* results
a single changed property has just invalidated without touching anything else.

## The shape of a calculation

```json
{
  "@id": "urn:aiop:calculation:harbour-q2-asymmetry",
  "@type": "Calculation",
  "function": "expected_value",
  "inputs": [
    {"variable": "upside",                "source": "urn:aiop:opportunity:harbour-q2-retrofit", "sourceProperty": "upside"},
    {"variable": "downside",              "source": "urn:aiop:opportunity:harbour-q2-retrofit", "sourceProperty": "downside"},
    {"variable": "execution_probability", "source": "urn:aiop:company:harbour-forge",           "sourceProperty": "execution_probability"},
    {"variable": "success_probability",   "source": "urn:aiop:technology:induction-retrofit",   "sourceProperty": "success_probability"},
    {"variable": "adoption_probability",  "source": "urn:aiop:market:uk-industrial-heat",       "sourceProperty": "adoption_probability"}
  ]
}
```

Five properties of four independently addressable objects. The calculation
holds no values of its own: each binding is a pointer read from the store at the
moment of evaluation, so a calculation cannot quietly go on using a figure the
world has moved past. A binding that cannot be resolved — no such object, no
such property — raises `UnresolvedBinding` rather than contributing a zero.

## Functions are named, never executed as text

A calculation names a function; the engine resolves the name in a
`FunctionRegistry` of ordinary Python callables. There is no `eval` of stored
expression text anywhere in `reasoning/`, and a test asserts there never is: a
stored string the engine would execute is a stored string that anything
upstream of the store can make the engine execute.

The registry checks the signature, so a calculation that declares the wrong
variables fails with `ArgumentMismatch` instead of computing something
plausible from the wrong inputs.

```python
@DEMO_FUNCTIONS.function("expected_value")
def expected_value(upside, downside, execution_probability, success_probability, adoption_probability):
    probability = execution_probability * success_probability * adoption_probability
    return upside * probability - downside * (1.0 - probability)
```

Expected value is a modelling decision about opportunities, not a universal
truth about objects, so it lives in `profiles/calculations.py`.

## The result is an ordinary object

```python
engine = ReasoningEngine(store, DEMO_FUNCTIONS, DEMO_CALCULATION_SCHEMA)
result = engine.evaluate("urn:aiop:calculation:harbour-q2-asymmetry")

result.get("value")            # 193273.2
store.get(result.id) is result # True — nothing special-cased it into existence
```

It has its own `@id`, its own state, its own provenance (`method="calculated"`,
`source` = the calculation), the snapshot of values it was computed from, and
one `derivedFrom` edge per source carrying the variable and property it took:

```json
{"predicate": "derivedFrom",
 "object": "urn:aiop:company:harbour-forge",
 "attributes": {"variable": "execution_probability", "sourceProperty": "execution_probability"}}
```

So lineage is not a separate mechanism. `LINEAGE_VIEW` walks those edges out of
a result exactly as it walks any other neighbourhood, and `DEPENDENTS_VIEW`
walks them back in.

## Staleness is a comparison, not a guess

Each result stores `inputFingerprint`: a SHA-256 of the function name and the
resolved inputs, canonically serialised. Re-reading the same bindings and
re-fingerprinting them answers "is this still true?" without re-running
anything.

```python
new_evidence(store)                       # execution_probability 0.62 → 0.74
engine.invalidated_by(COMPANY)            # [the expected-value result]
engine.check(result).reason               # "an input value has changed"
```

`invalidated_by` is an inbound index lookup on `derivedFrom` — the cost is the
number of things that actually read the changed object, not the size of the
graph. A source that has been deleted counts as staleness too, with the reason
saying so.

## Recomputation supersedes, it does not overwrite

```python
replacement = engine.recompute_stale()[0]

replacement.get("value")          # 292616.4
original.state                    # State.SUPERSEDED — still there, still 193273.2
store.history_of(replacement.id)  # [replacement, original]
```

The new result draws a `supersedes` edge at the old one, so the store's existing
version machinery gives the history of a conclusion for free, and the wrong
answer survives with the inputs that made it look right. Re-evaluating an
unchanged calculation is idempotent: same fingerprint, same standing result, no
new object.

## What the layer does not know

`reasoning/` names no domain vocabulary — not `Opportunity`, not `upside`, not
`derivedFrom`. Every term arrives through a `CalculationSchema`:

```python
DEMO_CALCULATION_SCHEMA = CalculationSchema(
    result_type="Result",
    function_property="function",
    inputs_property="inputs",
    value_property="value",
    fingerprint_property="inputFingerprint",
    calculation_property="calculation",
    variable_key="variable",
    source_key="source",
    source_property_key="sourceProperty",
    derivation_predicate="derivedFrom",
    version_predicate="supersedes",
)
```

exactly as the store takes its version predicate as configuration rather than
knowing the word. Swap the schema and the registry, and the same engine reasons
in another domain.

## Modules

| Module | Responsibility |
| --- | --- |
| `reasoning/binding.py` | `Binding(variable, source, source_property)` and its resolution against the store |
| `reasoning/functions.py` | The registry of named pure functions and its signature checking |
| `reasoning/calculation.py` | `CalculationSchema`, reading a calculation object, input fingerprinting |
| `reasoning/staleness.py` | Fingerprint comparison, `dependents_of`, `invalidated_by`, `stale` |
| `reasoning/engine.py` | `evaluate`, `recompute`, `recompute_stale`, result identity and lineage |
| `profiles/calculations.py` | The demo schema and the formulas themselves |

Run `python demo.py` to see the cluster assembled, the expected value
calculated, the audit land, and the conclusion recomputed.
