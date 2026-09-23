# Validator and Judge v0.1

The Validator and Judge are two capabilities because checking evidence and
deciding what conclusion may be presented are two different powers.

```
Observation -> Anomaly -> Research -> Claim -> Validation -> Decision -> Human
```

Neither capability closes the final arrow. The Human Principal remains the
only authority that may convert a provisional recommendation into working
belief or action.

## Validator

The Validator accepts a stored `Claim` and reads all active `Evidence` objects
that directly `supports`, `contradicts`, or `qualifies` it. It writes an
immutable-by-identity `Validation` beside the claim. Its input fingerprint
includes the claim, committed evidence universe, claim type, and policy; new
evidence produces a new Validation rather than rewriting the old receipt.

The v0.1 checks are deliberately mechanical:

- the proposition is non-empty;
- supporting evidence exists;
- independent evidence roots are counted rather than articles;
- expected evidence roots may be frozen in advance and missing runs are exposed;
- evidence and claim dimensions align;
- counter-evidence is retained;
- causal claims have evidence declaring a causal method;
- quantitative claims declare a value and evidence reports that value;
- recency is enforced only when the policy declares a time window.

The stored verdict vocabulary is `SUPPORTED`, `WEAKLY_SUPPORTED`,
`UNRESOLVED`, `CONTRADICTED`, and `UNTESTABLE`. The public projection is
`PASS`, `INCONCLUSIVE_COVERAGE`, `INCONCLUSIVE_EVIDENCE`, `INVALID`, or
`UNTESTABLE`; evidence on both sides is shown as `MIXED`. These are evaluations
of the evidence structure, not truth declarations.

Confidence is an estimate based on the weakest essential supporting reading.
Agreement never creates a confidence bonus, and repeated reports sharing one
independence root count as one root.

The capability requires `READ`, `VALIDATE`, `CREATE_OBJECT`, and
`RELATE_OBJECTS`. `INTERNAL_AUTHORITY` intentionally lacks `VALIDATE`; a
validation mission therefore needs an explicit charter.

## Judge

The Judge accepts a stored `Validation`, not a raw Claim. It writes a
`PROPOSED` `Decision` beside the Validation and Claim. It does not rerun
research or validation, mutate either input, update the real-world subject, or
authorize an action.

By default it carries the Validator's verdict. A supplied bound may weaken
that verdict; an attempted upgrade is refused and recorded in the Decision's
reasons. Every v0.1 Decision says:

```json
{
  "human_review_required": true,
  "authorized_action": "NONE",
  "confidence_kind": "estimate",
  "calibration": {"observed_outcome": null}
}
```

The Judge requires `READ`, `RECOMMEND`, `CREATE_OBJECT`, and
`RELATE_OBJECTS`. It deliberately has no `TRANSACT` authority.

## Example

```python
from capabilities.judgment import Judge
from capabilities.validation import Validator
from observer import Authority, Observer, Permission

authority = Authority.of(
    Permission.READ,
    Permission.VALIDATE,
    Permission.RECOMMEND,
    Permission.CREATE_OBJECT,
    Permission.RELATE_OBJECTS,
)

bench = Observer("validation bench", store=store, authority=authority)
bench.install(Validator())
bench.install(Judge())

checked = bench.invoke("validator", inputs=[claim])
validation = store.get(checked.findings["validations"][0])

judged = bench.invoke("judge", inputs=[validation])
decision = store.get(judged.findings["decisions"][0])
```

The enclosing mission must grant the same permissions; Observer authority and
mission authority still compose by intersection.
