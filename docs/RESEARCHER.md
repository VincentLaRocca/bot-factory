# The Researcher — the second capability, and the test of the first

The Anomaly Listener proved that *a* capability could be plugged into the
Observer. One plug-in proves very little: a chassis shaped around its only
occupant looks general right up until the second one arrives. The Researcher is
a deliberately different kind of thinking — it consumes what the listener
produces, it talks to the outside world through a provider boundary, and it
writes two object types instead of one — and it went in without a single line
changing in `observer/`.

```
Observation → Anomaly → Researcher → Evidence + Claim
```

```python
desk = Observer("market desk", store=store, authority=DESK_AUTHORITY)
desk.install(AnomalyListener())
desk.install(Researcher(provider))
desk.assign(mission)

noticed = desk.invoke("anomaly_listener", inputs=[observation])
found = desk.invoke("researcher", inputs=[store.get(noticed.findings["anomalies"][0])])
found.findings["investigations"][0]["topics"]["cause"]   # 'UNSUPPORTED'
```

There is no `ResearchObserver`. There is no `if capability == "researcher"`
anywhere in the chassis. `tests/test_researcher.py` asserts the negative
directly: it parses every module in `observer/`, strips the docstrings, and
fails if the words `Research`, `Evidence`, `Claim` or `capabilities.` appear —
and separately asserts that `git diff` against the Observer v0.1 baseline
touches nothing under `observer/`.

## What it is for, and what it refuses

The Researcher answers exactly one question: *what do the sources say about
this anomaly?* It does not decide whether the anomaly matters, does not write a
value onto the target object, does not accept its own claims, does not rank or
score sources against each other, and does not invent an explanation when
nobody supplied one. Each of those is somebody else's job, and most of those
somebodies do not exist yet.

## Source → Evidence → Claim

The ordering is the discipline. A finding never becomes a fact:

| Stage | Object | What it asserts |
| --- | --- | --- |
| Source | — | Nothing. It is a URN and a kind: `exchange_data`, `filing`, `news`. |
| Evidence | `Evidence` | *This source said this, on this date, and here is the text.* |
| Claim | `Claim` | *This proposition is what that evidence bears on* — and whether the evidence gathered stands behind it. |

Evidence points at claims with `supports`, `contradicts` or `qualifies`, and
`investigatedFrom` points back at the anomaly that prompted the question. A
claim is `about` its subject and `derivedFrom` the anomaly. Nothing points at
the target object's properties, which stay exactly as they were.

## Contradiction survives

The demonstration is a share price that prints 42.00 where it has always
printed about four. The exchange's corporate-actions notice and the issuer's
filing both say *1-for-10 reverse split*. A newswire says *product
breakthrough*. All three are stored, all three keep their source and their
independence group, and the claim they bear on ends `CONTESTED` — not averaged,
not majority-voted, not resolved in favour of the more reputable source.

```
CONTESTED: The 2026-02-17 move is the mechanical effect of a 1-for-10 reverse split.
  supporting    Exchange corporate actions notice (corporate_action, group abc-exchange)
  supporting    ABC Corporation regulatory filing (filing, group abc-issuer)
  contradicting Market wire                       (news, group wire-syndicate)
```

A claim's status is a statement about the evidence attached to it, never about
the world: `SUPPORTED` means *evidence stands behind this and nothing found
disagrees*, and it can be unsettled later — a contradiction filed by a second
investigation flips an existing claim to `CONTESTED`, because support is read
back out of the graph rather than from the current run's findings.

## Unknown survives

Four epistemic states, and they are the analyst's four words, meaning the same
things (a test asserts the two vocabularies have not drifted):

| State | Means |
| --- | --- |
| `KNOWN` | A claim on this topic is supported and uncontradicted. |
| `UNSUPPORTED` | Something was found, but nothing settles it — including a contested cause. |
| `UNKNOWN` | The sources were asked and answered nothing. |
| `UNREACHABLE` | No source could be asked at all. |

The last two are kept apart on purpose: *nobody knows* and *we could not look*
are different facts about the world, and a validator will want to know which
happened. A researcher with no sources at all returns four `UNKNOWN`s and
creates zero objects. Silence is recorded, not filled.

## The provider boundary

```python
class ResearchProvider(Protocol):
    name: str
    version: str

    def research(self, request: ResearchRequest) -> ResearchResponse: ...
```

Everything vendor-shaped lives on the far side. v0.1 ships `MockResearchProvider`
(prepared findings, no network), `SilentResearchProvider` (answers nothing,
honestly) and `ChainedResearchProvider` (asks several and *pools* what comes
back — pooling, not merging, so a second provider's disagreement survives into
the graph). A test asserts no module in `capabilities/research/` mentions
`requests`, `urllib`, `openai` or `anthropic`.

The request carries the anomaly's facts — target, property, observed and
expected state, magnitude — and deliberately not its score or disposition. A
source told the move is already thought to be a big deal is a source being led.

The four questions are a fixed template, worded deterministically:

```
Did share_price of ABC really move to 42.0?
What event or mechanism explains share_price of ABC moving to 42.0?
What surrounding facts help interpret share_price of ABC at 42.0, against an expected 4.15?
Is there another plausible explanation for share_price of ABC at 42.0?
```

Autonomous question generation is a later problem. A template that never varies
is a template whose outputs are comparable across runs.

## Identity, and running it twice

Evidence and claim identifiers are digests of what they say — the source plus
topic plus text for evidence, the proposition for a claim. A second identical
run therefore creates nothing: it finds the same objects, re-reads them, and
writes a second execution record saying so. Opinions do not accumulate by
repetition.

## Authority

The card requires `READ`, `RESEARCH`, `CREATE_OBJECT` and `RELATE_OBJECTS`.
`RESEARCH` is not in `INTERNAL_AUTHORITY`, and was deliberately not added to
it: that charter is described as everything an observer can do *to the graph*,
and consulting a source reaches outside it. An observer that researches is
chartered for it by name. An observer holding the capability but not the
permission is refused before the provider is called at all — the test asserts
`provider.asked == []`, because a refusal that still hit the source would be a
refusal in name only.

## What is deliberately absent

No live web browsing, search API, SEC integration or literature API. No LLM
anywhere. No autonomous research planning, no source-reliability scoring, no
consensus, no validator, no judge. Independence groups are *recorded* and never
*scored*: whether three articles quoting one wire story count as one source is
exactly the question the validator will exist to answer, and answering it here
would put the judgement in the layer that gathers the evidence.

`python3 demo_researcher.py` runs the whole arc; `--json` prints the contested
claim.
