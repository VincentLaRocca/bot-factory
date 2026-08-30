# The Observer motherboard, and its first capability

```
Agent = Observer + Capabilities + Mission + Authority + Resources
```

The Observer is the first term and nothing else. It holds an identity, a
version, a store, a set of slots, one mission, a grant of authority and an
audit trail. It does not know how to browse the web, detect an anomaly,
validate a claim, judge an opportunity, calculate an investment, speak in
public, research a company or understand medicine — and no capability may
teach it. Domain intelligence arrives as a plug-in and leaves again without the
chassis noticing.

The architectural claim is testable, so it is tested: `observer/` contains no
occurrence of the string *anomaly* outside prose, there is no
`AnomalyListenerObserver`, and installing the listener required no edit to
`observer/core.py`.

```
AIOP Core -> Store / Graph -> View / Cluster -> Reasoning
                                                    |
                                          Observer motherboard
                                                    |
                                              Capabilities
                                                    |
                                            Anomaly Listener
```

## The chassis

```python
observer = Observer("watchtower", store=store, authority=INTERNAL_AUTHORITY)
observer.install(AnomalyListener())
observer.assign(mission)
result = observer.invoke("anomaly_listener", inputs=[observation])
```

`register()` publishes the observer itself as an `Observer` object, and each
installed capability as a `Capability` object related back to it, so the
question "what is running out there, and what can it do?" is answered by the
graph rather than by reading code.

## Capabilities

A capability is anything with a `card` and a `run(context) -> outcome`. It is a
`Protocol`, not a base class: nothing has to import the chassis to be plugged
into it. The card is the self-description the chassis reasons over:

```python
CapabilityCard.build(
    capability="anomaly_listener", version="0.1",
    description="...",
    accepts=("Observation",), produces=("Anomaly",),
    requires=(Permission.READ, Permission.OBSERVE,
              Permission.CREATE_OBJECT, Permission.RELATE_OBJECTS),
    dependencies=(), compatible_with=("0.1",),
)
```

The registry refuses a duplicate, a capability built against an incompatible
chassis, and one whose declared dependencies are not installed. It answers
`accepting("Observation")` and `producing("Anomaly")`, which is how a future
planner will find the plug-in for a job without being told its name.

The `CapabilityContext` handed to `run()` carries the store, the effective
authority, the inputs, the mission object and the parameters — everything the
capability may touch, and nothing else.

### Sensors are not capabilities

A **sensor** reaches into a source and comes back with a reading. A
**capability** transforms, reasons over or acts on information. Confusing them
is how "read the price feed" and "decide what the price means" end up in the
same object. v0.1 ships `StaticSensor` only — deterministic, offline, no
network anywhere in the package — and `to_observations()` turns readings into
Observation objects with provenance intact.

## Authority

> Capability does not imply authority.

An observer holds capabilities because someone installed them, and authority
because a charter and a mission both allow it. The effective grant is the
**intersection**:

```python
observer.grant()  # observer.authority ∩ mission.authority
```

Intersection, never union, so no combination of charter and mission can produce
a permission neither held: a mission cannot escalate a privilege, and a
broadly-chartered observer cannot use a permission the current mission withheld.
An observer holding the anomaly listener but only `READ`/`OBSERVE` is refused
before the capability runs, and the refusal is recorded.

Refusals come back as an `Invocation` with `status == "REFUSED"`, not as an
exception, because a refusal is an outcome worth storing. `raise_for_status()`
is there for callers who want the exception.

## Missions

A mission is an Information Object: objective, priority, required capabilities,
granted authority, permitted resources, success, termination and escalation
conditions, expected outputs. A mission naming a capability the observer does
not have is not quietly degraded into a smaller mission — `assign()` raises
`MissionNotExecutable`, carrying a `Readiness` that names what is missing:

```
MISSION_NOT_EXECUTABLE
    missing_capabilities: scientific_research
```

## Observations

An observation is an ordinary AIOP object, and it keeps both of its endpoints:
`target` and `observer` are distinct properties and distinct relations
(`about`, `observedBy`, `sensedBy`). `observe()` refuses to let a component
observe itself; apparent self-observation is modelled as one component
observing another, or a state.

Every observation carries an `independence_group`. Ten observers reading the
same wire story share one group and are therefore one source, not ten
confirmations. v0.1 does no consensus arithmetic — it only refuses to lose the
metadata that would make it possible later.

## The Anomaly Listener

It answers one question — *is something meaningfully different here?* — and
refuses the next one. It produces an `Anomaly`, never an `Opportunity`; whether
the difference is *good* is a researcher's job, and the two must stay separable
or the listener starts having opinions about medicine.

It has **no memory of its own**. History comes out of the store on every run:

```
New observation + what the store remembers -> anomaly assessment
```

so the same reading against a different past gives a different answer, and
anyone can inspect the history that produced a score. In the demo, 0.83 after
eight steady weeks scores 1.00 and escalates; the identical reading in a world
where the rig was always noisy scores 0.00 and is ignored.

### The dimensions actually implemented

Six, each with its arithmetic in its own docstring, because a score nobody can
recompute by hand is a score nobody can argue with:

| dimension | fires when | score |
| --- | --- | --- |
| `first_observation` | nothing to compare against | flat 0.3 |
| `deviation_from_expected` | ≥ 2σ from the historical mean | `min(1, σ/4)` |
| `magnitude_of_change` | ≥ 25% step from the previous value | `min(1, abs(delta)/abs(previous))` |
| `categorical_novelty` | a value never recorded for this target | 1.0 |
| `historical_rarity` | seen in ≤ 10% of ≥ 5 observations | `1 − frequency` |
| `threshold_crossing` | outside a range declared by a caller | `min(1, distance/width)` |

Other dimensions are nameable — rate of change, broken historical
relationship, unprecedented combination, new capability — and are deliberately
**not implemented** rather than faked. `DetectorRegistry.extend()` takes new
ones without touching the listener.

The overall score is the **strongest** dimension, not a blend. Blending asserts
how dimensions relate — whether two weak signals corroborate or merely repeat —
and that is a modelling claim v0.1 has no evidence for. Every dimension's own
score is kept alongside, so a better combiner can be fitted later without
rewriting history.

### Disposition is triage

`IGNORE < 0.30 ≤ WATCH < 0.60 ≤ RESEARCH < 0.85 ≤ ESCALATE`, and the thresholds
are configuration on the capability rather than constants in a branch, because
somebody has to choose them and that choice should be storable and arguable.
Disposition says who looks next, not what it means.

### What an anomaly carries

Score, disposition, the dimensions that fired and each signal's own numbers and
reason; observed and expected state; magnitude; the ids it was compared with,
their values and their independence groups; confidence; `detected_by`,
`detector_version`, `detected_at`; an input fingerprint; and the policy in
force. Relations: `derivedFrom` the observation, `about` the target,
`comparedWith` every remembered observation, `detectedBy` the capability.

The same reading against the same memory produces the same anomaly id, so
re-running is idempotent rather than duplicative.

## Execution records

Every invocation writes one, refusals and failures included: observer and
version, chassis, capability and version, mission, the authority actually in
force, what was read, what was created, start and end, status, and the refusal
or error. Enough to reconstruct a decision — and structured rationale only.
No hidden chain of thought is stored, because a record of a mind is not the
same thing as a record of a decision.

## Run it

```bash
python3 demo_observer.py          # the whole arc, narrated
python3 demo_observer.py --json   # the anomaly object itself
python3 -m pytest -q
```

The demo builds an observer with no intelligence in it, watches a mission be
refused for want of a capability, installs the listener, remembers eight weeks
of a cell behaving identically, notices week nine, ignores week ten, catches a
technology demonstrating a capability it has never demonstrated, replays the
same reading against a noisier past, refuses an observer that holds the
capability but not the authority, and refuses a mission nobody can run.

## What is not here

No live sensors, no external APIs, no LLM, no embeddings, no vector store, no
spawning, no consensus arithmetic, no researcher, validator, judge or speaker.
The listener triggers; something else, later, will decide what the trigger
means.
