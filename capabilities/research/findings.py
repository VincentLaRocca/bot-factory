"""Turning what a source said into Evidence, and Evidence into Claims.

The ordering is the whole discipline:

```
Source  ->  Evidence  ->  Claim
```

A finding never becomes a fact. It becomes an addressable Evidence object
naming where it came from; the Evidence points at a Claim; and the Claim
records whether the evidence gathered stands behind it, disagrees about it, or
is merely adjacent to it. Nothing here writes a value onto a target object —
that is what a validator would do, and there isn't one.

Two rules survive contact with awkward data:

* **Contradiction survives.** Evidence disagreeing with a claim is stored,
  linked as ``contradicts``, and the claim becomes ``CONTESTED``. Nothing is
  averaged and no source is quietly dropped.
* **Unknown survives.** A topic no source answered ends ``UNKNOWN``, and a
  topic no source could be consulted about ends ``UNREACHABLE``. Neither is
  filled in with the most plausible story.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aiop import AIOPObject, Provenance, State
from profiles.research import RESEARCH_CONTEXT
from store import ObjectStore

from .provider import Finding, ResearchRequest, ResearchResponse

SUPPORTED = "SUPPORTED"
CONTESTED = "CONTESTED"
UNSUPPORTED = "UNSUPPORTED"

KNOWN = "KNOWN"
UNKNOWN = "UNKNOWN"
UNREACHABLE = "UNREACHABLE"


@dataclass
class TopicOutcome:
    """One question, what came back, and what that amounts to."""

    topic: str
    question: str
    status: str
    evidence: List[AIOPObject] = field(default_factory=list)
    claims: List[AIOPObject] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "question": self.question,
            "status": self.status,
            "evidence": [obj.id for obj in self.evidence],
            "claims": [obj.id for obj in self.claims],
        }


@dataclass
class Investigation:
    """One anomaly investigated: what was asked, found, and written down."""

    anomaly: str
    request: ResearchRequest
    response: ResearchResponse
    topics: List[TopicOutcome] = field(default_factory=list)
    created: List[AIOPObject] = field(default_factory=list)
    read: List[str] = field(default_factory=list)

    @property
    def evidence(self) -> List[AIOPObject]:
        return [obj for topic in self.topics for obj in topic.evidence]

    @property
    def claims(self) -> List[AIOPObject]:
        return [obj for topic in self.topics for obj in topic.claims]

    @property
    def contested(self) -> List[AIOPObject]:
        return [claim for claim in self.claims if claim.get("status") == CONTESTED]

    def status_of(self, topic: str) -> str:
        for outcome in self.topics:
            if outcome.topic == topic:
                return outcome.status
        return UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly": self.anomaly,
            "target": self.request.target,
            "provider": self.response.provider,
            "provider_version": self.response.version,
            "questions": [question.to_dict() for question in self.request.questions],
            "topics": {outcome.topic: outcome.status for outcome in self.topics},
            "evidence": [obj.id for obj in self.evidence],
            "claims": [obj.id for obj in self.claims],
            "contested": [obj.id for obj in self.contested],
        }


def digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:8]


def evidence_id(anomaly: str, finding: Finding) -> str:
    """A stable id: the same source saying the same thing is one piece of evidence."""
    return f"{anomaly}#evidence-{digest(finding.source, finding.topic, finding.content)}"


def claim_id(subject: str, proposition: str) -> str:
    """A stable id: the same proposition about the same subject is one claim."""
    return f"{subject}#claim-{digest(proposition)}"


def build_evidence(
    finding: Finding,
    anomaly: str,
    researcher: str,
    subject: str,
    at: datetime,
    context: Any = None,
) -> AIOPObject:
    """One finding, written down with where it came from still attached."""
    properties: Dict[str, Any] = {
        "title": finding.source_name or finding.source,
        "content": finding.content,
        "dimension": finding.topic,
        "stance": finding.stance,
        "source": finding.source,
        "source_type": finding.source_type,
        "source_kind": finding.source_kind,
        "confidence": finding.confidence,
        "retrieved_at": at.isoformat(),
        "independent": finding.independence_group is None,
    }
    if finding.source_name:
        properties["source_name"] = finding.source_name
    if finding.source_date is not None:
        properties["source_date"] = finding.source_date
    if finding.independence_group is not None:
        properties["independence_group"] = finding.independence_group
    if finding.reliability is not None:
        properties["reliability"] = finding.reliability
    if finding.claimed_value is not None:
        properties["claimed_value"] = finding.claimed_value
    if finding.claimed_property is not None:
        properties["target_property"] = finding.claimed_property

    evidence = AIOPObject(
        id=evidence_id(anomaly, finding),
        types=["Evidence"],
        context=context if context is not None else list(RESEARCH_CONTEXT),
        state=State.ACTIVE,
        properties=properties,
    )
    evidence.attest(
        Provenance(
            agent=researcher,
            method="researched",
            source=finding.source,
            confidence=finding.confidence,
            generated_at=at,
            note=f"{finding.source_type} consulted about {finding.topic}",
        )
    )
    evidence.relate("investigatedFrom", anomaly)
    evidence.relate("about", subject)
    return evidence


def build_claim(
    proposition: str,
    subject: str,
    topic: str,
    anomaly: str,
    researcher: str,
    at: datetime,
    claimed_property: Optional[str] = None,
    claimed_value: Any = None,
    context: Any = None,
) -> AIOPObject:
    """A proposition the evidence bears on. Status is decided once it is linked."""
    properties: Dict[str, Any] = {
        "statement": proposition,
        "dimension": topic,
        "status": UNSUPPORTED,
        "proposed_by": researcher,
    }
    if claimed_property is not None:
        properties["target_property"] = claimed_property
    if claimed_value is not None:
        properties["claimed_value"] = claimed_value

    claim = AIOPObject(
        id=claim_id(subject, proposition),
        types=["Claim"],
        context=context if context is not None else list(RESEARCH_CONTEXT),
        state=State.ACTIVE,
        properties=properties,
    )
    claim.attest(
        Provenance(
            agent=researcher,
            method="derived",
            source=anomaly,
            generated_at=at,
            note=f"proposed while investigating {topic}",
        )
    )
    claim.relate("about", subject)
    claim.relate("derivedFrom", anomaly)
    return claim


def judge(supporting: Sequence[AIOPObject], contradicting: Sequence[AIOPObject]) -> str:
    """Where a claim stands with what is currently attached to it.

    Not a verdict on truth: a claim is ``SUPPORTED`` when evidence stands
    behind it and nothing found disagrees, which is a statement about the
    evidence gathered, not about the world.
    """
    if contradicting:
        return CONTESTED
    if supporting:
        return SUPPORTED
    return UNSUPPORTED


def assemble(
    store: ObjectStore,
    anomaly: AIOPObject,
    request: ResearchRequest,
    response: ResearchResponse,
    researcher: str,
    at: datetime,
    context: Any = None,
) -> Investigation:
    """Write the findings into the graph, and say what each topic amounts to."""
    investigation = Investigation(
        anomaly=anomaly.id, request=request, response=response
    )
    subject = request.target

    for question in request.questions:
        findings = response.for_topic(question.topic)
        outcome = TopicOutcome(
            topic=question.topic,
            question=question.question,
            status=UNKNOWN,
        )

        by_claim: Dict[str, List[Tuple[Finding, AIOPObject]]] = {}
        for finding in findings:
            stored = _store(store, build_evidence(
                finding=finding,
                anomaly=anomaly.id,
                researcher=researcher,
                subject=finding.subject or subject,
                at=at,
                context=context,
            ), investigation)
            outcome.evidence.append(stored)
            by_claim.setdefault(finding.proposition, []).append((finding, stored))

        for proposition in sorted(by_claim):
            pairs = by_claim[proposition]
            first = pairs[0][0]
            claim = _store(store, build_claim(
                proposition=proposition,
                subject=first.subject or subject,
                topic=question.topic,
                anomaly=anomaly.id,
                researcher=researcher,
                at=at,
                claimed_property=first.claimed_property,
                claimed_value=first.claimed_value,
                context=context,
            ), investigation)

            for finding, evidence in pairs:
                _link(store, evidence, finding.stance, claim.id)

            # Read the claim's support back out of the graph rather than from
            # this run's findings: evidence filed by an earlier investigation
            # still bears on the claim, and a later contradiction has to be
            # able to unsettle a claim that once looked supported.
            supporting = _bearing(store, claim.id, "supports")
            contradicting = _bearing(store, claim.id, "contradicts")
            qualifying = _bearing(store, claim.id, "qualifies")

            claim.set("status", judge(supporting, contradicting))
            claim.set("supporting", [obj.id for obj in supporting])
            claim.set("contradicting", [obj.id for obj in contradicting])
            claim.set("qualifying", [obj.id for obj in qualifying])
            claim.set("confidence", _confidence(supporting))
            claim.set(
                "independence_groups",
                sorted(
                    {
                        str(obj.get("independence_group"))
                        for obj in supporting
                        if obj.get("independence_group") is not None
                    }
                ),
            )
            store.reindex(claim.id)
            outcome.claims.append(claim)

        outcome.status = _epistemic(outcome, question.topic, response)
        investigation.topics.append(outcome)

    investigation.read = sorted(dict.fromkeys(investigation.read))
    return investigation


def _epistemic(
    outcome: TopicOutcome, topic: str, response: ResearchResponse
) -> str:
    """What investigation established about one topic.

    ``UNREACHABLE`` and ``UNKNOWN`` are kept apart on purpose: not being able
    to ask is a different state of the world from asking and being told
    nothing, and a later validator will want to know which happened.
    """
    if not outcome.evidence:
        return UNREACHABLE if topic in response.unreachable else UNKNOWN
    if any(claim.get("status") == SUPPORTED for claim in outcome.claims):
        return KNOWN
    return UNSUPPORTED


def _bearing(store: ObjectStore, claim: str, predicate: str) -> List[AIOPObject]:
    """Every stored object standing in one relation to a claim, by id."""
    found = [store.find(relation.subject) for relation in store.inbound(claim, predicate)]
    return sorted(
        (obj for obj in found if obj is not None and obj.state is State.ACTIVE),
        key=lambda obj: obj.id,
    )


def _confidence(supporting: Sequence[AIOPObject]) -> float:
    """The mean confidence of the evidence behind a claim, and nothing cleverer.

    Deliberately not a consensus score: agreeing sources do not multiply here,
    because whether they are independent is the validator's question.
    """
    if not supporting:
        return 0.0
    values = [float(obj.get("confidence", 0.5)) for obj in supporting]
    return round(sum(values) / len(values), 4)


def _store(
    store: ObjectStore, obj: AIOPObject, investigation: Investigation
) -> AIOPObject:
    """Add the object, or hand back the one the graph already has.

    Identity is a digest of what the object says, so a second identical run
    re-uses what is there instead of filing a duplicate opinion.
    """
    existing = store.find(obj.id)
    if existing is not None:
        investigation.read.append(existing.id)
        return existing
    stored = store.add(obj)
    investigation.created.append(stored)
    return stored


def _link(store: ObjectStore, subject: AIOPObject, predicate: str, target: str) -> None:
    if target in subject.related(predicate):
        return
    subject.relate(predicate, target)
    if store.contains(subject.id):
        store.reindex(subject.id)


__all__ = [
    "CONTESTED",
    "Investigation",
    "KNOWN",
    "SUPPORTED",
    "TopicOutcome",
    "UNKNOWN",
    "UNREACHABLE",
    "UNSUPPORTED",
    "assemble",
    "build_claim",
    "build_evidence",
    "claim_id",
    "evidence_id",
    "judge",
]
