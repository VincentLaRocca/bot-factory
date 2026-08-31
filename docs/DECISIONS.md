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

## AD-3 — Authority composes by intersection

*Status: accepted for v0.1. Made while building the Observer motherboard.*

An observer has a charter; a mission has a grant. When they disagree about
whether the observer may create objects, one of them has to win.

**Chosen.** `observer.grant() == observer.authority ∩ mission.authority`, so
the narrower always wins, and the effective grant is recomputed per invocation
rather than stored. A mission can only ever *narrow* what an observer may do.

**Rejected: union, or mission-as-override.** Either would make a mission a
privilege-granting instrument: anything that can write a Mission object could
then hand an observer `TRANSACT`. Intersection means the charter is a ceiling
that no amount of tasking can raise, which is the property worth having when
missions eventually get written by other agents.

**Consequence.** Granting an observer a new power is deliberately a two-place
edit — charter *and* mission — and `Readiness` exists so the second place is
discoverable: it names the missing permissions instead of failing at runtime.

**Revisit when** delegation arrives (`SPAWN`). A child observer's charter should
be the parent's effective grant, not the parent's charter, or the intersection
leaks one level down.

## AD-4 — An anomaly score is its strongest dimension, not a blend

*Status: accepted for v0.1. Made while building the Anomaly Listener.*

Six detectors fire independently. Something has to turn several signals into
one number that a disposition threshold can be applied to.

**Chosen.** `score = max(signal.score)`, with every dimension's own score,
reason and arithmetic kept alongside on the anomaly.

**Rejected: a weighted blend.** Weighting asserts how the dimensions relate —
whether a 0.4 deviation *and* a 0.4 step change corroborate each other or are
two views of the same jump. They are usually the latter, so a sum would
double-count correlated evidence and manufacture confidence out of arithmetic.
v0.1 has no data with which to fit those weights, and inventing them would make
the score unarguable in the specific way the layer exists to avoid.

**Consequence.** Many weak signals never add up to a strong one. An anomaly that
is only interesting *because* several dimensions agree will currently be scored
as WATCH and looked at by a human, which is the failure direction to prefer.

**Revisit when** there are enough labelled anomalies to fit a combiner. The
signals are stored per-dimension precisely so that it can be fitted
retrospectively over anomalies already in the graph, without re-running history.

## AD-5 — The researcher reuses the analyst's Claim, rather than owning one

*Status: accepted for v0.1. Made while building the Researcher.*

The Researcher needs to say "this proposition is what the evidence bears on".
The Asymmetry Analyst already has a `Claim` type with `statement`, `dimension`
and `status`, and evidence that `supports` or `contradicts` it.

**Chosen.** The same type, the same three required properties, the same three
stance predicates. A researcher claim validates against `ASYMMETRY_PROFILE`,
and a test asserts it. The research profile adds only what is genuinely new —
`Evidence` as a stored type with its source metadata, `investigatedFrom`, and
the derived `supporting`/`contradicting`/`qualifying` lists.

**Rejected: a `ResearchClaim` with its own vocabulary.** It would have been
easier to write and impossible to reconcile: two claim systems in one graph
means every later consumer — validator, judge, analyst — needs to know which
kind it is holding, and the first thing anyone would build is a translation
layer between them. Independent vocabularies are cheap to create and expensive
forever.

**Consequence.** The researcher inherits a constraint it did not choose: claim
status is `SUPPORTED` / `CONTESTED` / `UNSUPPORTED`, and `ACCEPTED` belongs to
whoever adjudicates. That is the right constraint — the researcher must not be
able to promote its own findings — but it does mean the analyst's status
vocabulary is now load-bearing for two capabilities and should change carefully.

**Revisit when** a third producer of claims needs something neither has. The
answer then is to lift `Claim` into a shared profile above both, not to fork it.

## AD-6 — Claim status is read from the graph, not from the run

*Status: accepted for v0.1. Made while building the Researcher.*

An investigation could decide a claim's status from the findings it just
received. It does not: it writes the evidence, then reads every piece of
evidence in the store that bears on the claim — including evidence filed by
earlier runs and by other researchers with other providers — and derives the
status from all of it.

**Chosen.** Status is a function of the graph at the moment of writing.
Contradiction filed tomorrow by a different provider unsettles a claim that
looked `SUPPORTED` today, without anyone re-running the original investigation.

**Rejected: status from the current response.** It makes a claim mean "what one
provider said on one afternoon", and the last writer wins. Worse, it makes the
same claim's status depend on invocation order, which is exactly the kind of
irreproducibility the store exists to prevent.

**Consequence.** A run can change objects it did not create, and the change is
visible in the claim's `supporting`/`contradicting` lists rather than only in
its status. Repeated identical runs are still inert: digest identity means the
same evidence produces the same objects, so nothing accumulates.

**Revisit when** evidence needs retracting. Today nothing is ever withdrawn, so
"read everything that bears on this" and "read everything ever said" are the
same query; a retracted source would make them differ, and the read would need
to become state-aware.
