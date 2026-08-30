# Asymmetry Analyst v0.1

The first agent. It owns no knowledge: it reads the store, notices what is
missing, goes and gets some of it, asks the reasoning layer for the arithmetic,
and writes its conclusion back as ordinary Information Objects.

```
Opportunity @id → Cluster → Completeness → Gaps → Research → Claims/Evidence
                                                       ↓
                             Assessment ← Judgement ← Calculations
```

```python
from agents.asymmetry import AsymmetryAnalyst

analyst = AsymmetryAnalyst(store, research=provider)
run = analyst.run("urn:aiop:opportunity:clinical-triage")

run.completeness.score        # 0.71 — and which dimensions are missing
run.assessment.get("recommended_action")   # INVESTIGATE_INVESTMENT
run.record.get("objects_created")          # everything this run wrote
```

The API takes an `@id`, not a prompt. Everything the analyst reasons over it
fetched itself.

## What it is allowed to know

`agents/asymmetry/specification.py` is the catalogue: every dimension the
analyst judges an opportunity on, in eight groups (opportunity, synergy,
asymmetry, technology, people, market, access, judgment). Each dimension names
the object type and property that answers it, how much the answer moves the
decision, and how resolvable it is.

`profiles/asymmetry.py` holds the vocabulary those dimensions are written in —
the `Claim`, `InformationGap`, `Assessment`, `SynergyAssessment`, `OurEdge` and
`ExecutionRecord` types, their required properties, the calculation functions
and the JSON-LD context. Domain language lives in the profile; only the process
lives in the agent. Neither `aiop/`, `store/` nor `reasoning/` changed to make
this layer possible.

## Four epistemic states, and no fifth

```python
class Status(str, Enum):
    KNOWN        # a value, and evidence standing behind it
    UNSUPPORTED  # a value someone asserted, with nothing behind it
    UNKNOWN      # the object exists, the property is empty
    UNREACHABLE  # there is no such object in the cluster at all
```

An opportunity that claims a £4.2m upside with no evidence is *not* treated as
knowing its upside; a missing Market object is a different failure from an
empty `adoption_probability`, and the analyst reports it as one. Superseded
evidence stops supporting anything, so the moment a claim is replaced the
dimension it supported drops back out of `KNOWN`.

Unknown is acceptable. Guessing is not — the deterministic reasoner writes
"execution probability is not established" rather than a placeholder, and a
calculation whose bindings are missing simply does not run.

## Gaps are objects, and they are ranked

Every unresolved dimension becomes an `InformationGap` object related `about`
the opportunity, and is ranked by a formula you can recompute by hand:

```
research_priority = decision_impact × uncertainty × dependency_weight × resolvability
dependency_weight = 1 + 0.5 × (calculations reading that property)
```

`decision_impact` and `resolvability` come from the dimension catalogue,
`uncertainty` from the epistemic status, and `dependency_weight` from the
calculation schema — so a property that two calculations depend on outranks an
equally unknown one that nothing consumes. Nothing here is a model's opinion.

## Research is a boundary, not a vendor

```python
class ResearchProvider(Protocol):
    def research(self, gap: InformationGap) -> list[AIOPObject]: ...
```

v0.1 ships `StoreResearchProvider` (evidence already sitting in the graph),
`MockResearchProvider` (a fixture directory), `ChainedResearchProvider` and
`NoResearchProvider`. No OpenAI, Anthropic, Gemini or Devin dependency exists
anywhere in the package, and the whole test suite runs without a network.

Findings become `Evidence` objects, which support a `Claim`, which — only if
accepted — sets the property on the target object with provenance naming the
claim. Evidence that disagrees is linked `contradicts` and the claim is
`CONTESTED`: a contested value is never applied. When later evidence moves a
value, a new Claim `supersedes` the old one and the old one transitions to
`SUPERSEDED`; no history is overwritten.

## Assessments go stale too

The reasoning layer knows staleness for calculation results. An Assessment is
not a result, so it carries its own application-level fingerprint over the
sources it was formed from (their ids, states and values) plus the completeness
it was formed at:

```python
is_stale(store, assessment)   # True once a source changed or was superseded
run = analyst.reanalyse(opportunity_id)
run.superseded                # the assessment it replaced, now SUPERSEDED
```

Re-running over an unchanged graph produces the same fingerprint and the
standing assessment is left alone. Re-running after new evidence produces a new
Assessment object and supersedes the old — the previous verdict remains
readable, which is the point.

## Every run leaves a record

An `ExecutionRecord` per run: agent identity and version, profile and policy
version, start and end, the input opportunity, the cluster fingerprint, objects
read, objects created, calculations executed, gaps discovered, status. Enough
to reconstruct what the agent saw. No hidden chain-of-thought is stored — the
reasoning that matters is in the Claims, Evidence and Results it points at.

## The demonstration

`python3 demo_asymmetry.py` runs `examples/asymmetry/`: a deliberately
incomplete Human×AI clinical triage opportunity where research closes some gaps
and leaves others `UNKNOWN`, expected value is calculated only once its inputs
exist, contradictory defensibility evidence stays contested, and then a late
audit moves `execution_probability` 0.62 → 0.78 — invalidating both results,
superseding a claim, staling the assessment, and producing a recomputed
expected value and a replacement assessment.
