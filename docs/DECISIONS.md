# Architecture decisions

Decisions that were not obvious at the time and that a later reader would
otherwise have to reconstruct from the code. Each records what was chosen, what
it was chosen over, and what would justify revisiting it.

## AD-1 — Assessments carry their own input fingerprint

*Status: accepted for v0.1. Made while building the Asymmetry Analyst.*

`reasoning/` knows how to tell that a **calculation Result** is stale: the
result stores a fingerprint of the values its bindings read, and the store's
inbound index turns "this object changed" into "these results are invalid"
without a scan. An `Assessment` is not a Result — it is not produced by a
declared function over declared bindings — so none of that machinery applies to
it, and yet an assessment goes out of date for exactly the same reason.

**Chosen.** The application layer computes its own fingerprint over the sources
an assessment was actually formed from, and the assessment persists both:

```python
"sources": [id, ...],          # evidence, claims, results, the opportunity
"inputFingerprint": sha256(...)  # each source's id, state and value
"completeness": 0.71           # and the completeness it was formed at
```

`assessment.is_stale(store, assessment)` recomputes that digest and compares.
Staleness of an assessment is therefore an application concern, expressed in
application code, over an application-defined notion of "the inputs".

**Rejected: generalise staleness in `reasoning/`.** It would have meant giving
the reasoning layer a concept of "any object derived from any set of objects",
which is most of a general dependency tracker. That is a real option, but it
buys nothing until a second application wants it, and it would have put domain
judgement (*is completeness part of the input? does a superseded source count?*)
into the generic layer. The whole point of the exercise was that the agent sits
on the infrastructure without changing it.

**Revisit when** a second consumer needs derived-object staleness, or when the
duplication between `reasoning/staleness.py` and `assessment.fingerprint` starts
drifting. The generalisation to reach for then is a `Derived` protocol —
"declare your sources, get staleness" — not special-casing `Assessment` in
`reasoning/`.

**Consequence to be aware of:** two fingerprints now exist over the same graph
with different rules. Results fingerprint *values only*; assessments fingerprint
*ids, states and values*, because an assessment cares that a source was
superseded even when the number it carried did not move.

## AD-2 — An accepted claim enriches the target object in place

*Status: accepted for v0.1. Made while building the Asymmetry Analyst.*

When research resolves a gap — say `Company.execution_probability` was unknown
and evidence establishes 0.62 — something has to change in the graph. AIOP's
normal answer to "this object's content changed" is supersession: write a new
version, transition the old to `SUPERSEDED`.

**Chosen.** The Company object is updated in place, with provenance naming the
`Claim` that authorised the value. History is not lost, because the epistemic
history lives in objects of its own:

```
Evidence ──supports──> Claim ──> sets Company.execution_probability
Evidence ──contradicts──> Claim          (contested: value NOT applied)
Claim-2  ──supersedes──> Claim-1         (old claim -> SUPERSEDED)
```

**Rejected: supersede the target object.** Calculations bind to
`(source_id, property)`. Superseding the Company mints a new id, so every
calculation binding pointing at the old one either resolves to a retired object
or has to be rewritten — the graph would need version-following bindings, which
is a much larger change to `reasoning/` and to the meaning of an `@id`. Keeping
the object's identity stable is what lets a calculation be a durable statement
about *that company* rather than about a snapshot of it.

The trade is deliberate: the Company object shows only its current values, and
"what did we believe last month, and why" is answered by reading the Claim and
Evidence chain rather than the object's own history. That is arguably where the
answer belongs — the object never knew *why* it held a value in the first place.

**Revisit when** something needs to reconstruct the full state of a target
object at a past instant. Today that requires replaying claims; if it becomes a
routine need, the fix is a versioned target with version-following bindings, and
it should be taken as a Core/Store decision rather than an agent one.
