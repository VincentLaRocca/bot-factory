"""Turning evidence into claims, and claims — carefully — into values.

Nothing found by research is written onto an object directly. Findings become
an addressable Claim, the evidence points at the claim, and only a claim the
policy accepts is allowed to set a property, with provenance naming the claim
that justified it. Everything else stays visible and unapplied.

Two rules do most of the work here:

* **Contradiction is not averaged away.** Evidence proposing a different value
  contradicts the claim; a contested claim is recorded and refused.
* **An unsupported statement is never promoted to a fact.** Below the policy's
  evidence or confidence threshold, the claim is stored with its status and the
  property is left unknown.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from aiop import AIOPObject, Provenance, State
from store import ObjectStore

from .policy import AnalysisPolicy

ACCEPTED = "ACCEPTED"
CONTESTED = "CONTESTED"
UNSUPPORTED = "UNSUPPORTED"


@dataclass
class ClaimOutcome:
    """What one gap's research produced."""

    gap: AIOPObject
    claim: Optional[AIOPObject] = None
    evidence: List[AIOPObject] = field(default_factory=list)
    applied: bool = False
    status: str = UNSUPPORTED
    target: Optional[str] = None
    value: object = None
    superseded: Optional[str] = None

    @property
    def created(self) -> List[AIOPObject]:
        objects = list(self.evidence)
        if self.claim is not None:
            objects.append(self.claim)
        return objects


def claim_id(target: str, dimension: str) -> str:
    return f"{target}#claim-{dimension.replace('.', '-')}"


def _weight(evidence: AIOPObject) -> Tuple[int, float]:
    """How much a piece of evidence counts: primary and independent first."""
    confidence = float(evidence.get("confidence", 0.5))
    rank = 0
    if evidence.get("source_kind") == "primary":
        rank += 1
    if evidence.get("independent"):
        rank += 1
    return rank, confidence


def _candidates(findings: Sequence[AIOPObject]) -> Dict[str, List[AIOPObject]]:
    """Findings grouped by the value they propose, deterministically keyed."""
    grouped: Dict[str, List[AIOPObject]] = defaultdict(list)
    for finding in findings:
        grouped[repr(finding.get("claimed_value"))].append(finding)
    return grouped


def _leading(grouped: Dict[str, List[AIOPObject]]) -> str:
    """The best-supported proposed value; ties break on the key, not on order."""
    def strength(key: str) -> Tuple[int, float, int, str]:
        group = grouped[key]
        weights = [_weight(item) for item in group]
        return (
            len(group),
            sum(confidence for _, confidence in weights),
            sum(rank for rank, _ in weights),
            key,
        )

    return max(sorted(grouped), key=strength)


def assemble(
    store: ObjectStore,
    gap: AIOPObject,
    findings: Sequence[AIOPObject],
    target: str,
    dimension: str,
    prop: str,
    policy: AnalysisPolicy,
    agent: str,
    context: object,
) -> ClaimOutcome:
    """Store the findings, build the claim they make, and judge it."""
    outcome = ClaimOutcome(gap=gap, target=target)
    if not findings:
        return outcome

    stored: List[AIOPObject] = []
    for finding in findings:
        held = store.find(finding.id)
        stored.append(held if held is not None else store.add(finding))
    outcome.evidence = stored

    grouped = _candidates(stored)
    leading = _leading(grouped)
    supporting = grouped[leading]
    dissenting = [item for key, group in grouped.items() if key != leading for item in group]
    value = supporting[0].get("claimed_value")

    claim, superseded = _claim_for(
        store, target, dimension, prop, value, gap, context
    )
    outcome.superseded = superseded

    confidence = round(
        sum(float(item.get("confidence", 0.5)) for item in supporting) / len(supporting), 4
    )
    claim.set("confidence", confidence)

    for item in supporting:
        _link(store, item, "supports", claim.id)
    for item in dissenting:
        _link(store, item, "contradicts", claim.id)

    status = _judge(supporting, dissenting, confidence, policy)
    claim.set("status", status)
    claim.attest(
        Provenance(
            agent=agent,
            method="derived",
            source=gap.id,
            confidence=confidence,
            note=(
                f"{len(supporting)} supporting, {len(dissenting)} contradicting "
                f"piece(s) of evidence"
            ),
        )
    )

    outcome.claim = claim
    outcome.status = status
    outcome.value = value
    if status == ACCEPTED and value is not None:
        apply(store, claim, target, prop, value, agent, confidence)
        outcome.applied = True
    else:
        _link(store, claim, "qualifies", target)
    store.reindex(claim.id)
    return outcome


def _claim_for(
    store: ObjectStore,
    target: str,
    dimension: str,
    prop: str,
    value: object,
    gap: AIOPObject,
    context: object,
) -> Tuple[AIOPObject, Optional[str]]:
    """The claim this round's evidence makes, new or standing.

    A standing claim is reused while it says the same thing. When the evidence
    now points at a different value the old claim is superseded rather than
    edited: the sources that supported 0.62 must not silently end up attached
    to a statement about 0.78.
    """
    base = claim_id(target, dimension)
    standing = _standing(store, base)
    if standing is not None and standing.get("claimed_value") == value:
        return standing, None

    identifier = base if standing is None else f"{base}-{_next(store, base)}"
    claim = AIOPObject(
        id=identifier,
        types=["Claim"],
        context=context,
        state=State.ACTIVE,
        properties={
            "statement": _statement(target, prop, value),
            "dimension": dimension,
            "status": UNSUPPORTED,
        },
    )
    if value is not None:
        claim.set("claimed_value", value)
    claim.relate("about", target, dimension=dimension, sourceProperty=prop)
    claim.relate("resolves", gap.id)

    if standing is None:
        return store.add(claim), None

    claim.relate("supersedes", standing.id)
    standing.transition(State.SUPERSEDED)
    store.reindex(standing.id)
    return store.add(claim), standing.id


def _standing(store: ObjectStore, base: str) -> Optional[AIOPObject]:
    """The current claim in a chain, if there is one."""
    candidates = [
        obj
        for obj in store.objects(types=["Claim"])
        if (obj.id == base or obj.id.startswith(f"{base}-"))
        and obj.state is State.ACTIVE
    ]
    return sorted(candidates, key=lambda obj: obj.id)[-1] if candidates else None


def _next(store: ObjectStore, base: str) -> int:
    versions = [
        obj
        for obj in store.objects(types=["Claim"])
        if obj.id == base or obj.id.startswith(f"{base}-")
    ]
    return len(versions) + 1


def _judge(
    supporting: Sequence[AIOPObject],
    dissenting: Sequence[AIOPObject],
    confidence: float,
    policy: AnalysisPolicy,
) -> str:
    if dissenting:
        return CONTESTED
    if len(supporting) < policy.minimum_evidence:
        return UNSUPPORTED
    if confidence < policy.minimum_confidence:
        return UNSUPPORTED
    return ACCEPTED


def apply(
    store: ObjectStore,
    claim: AIOPObject,
    target: str,
    prop: str,
    value: object,
    agent: str,
    confidence: float,
) -> AIOPObject:
    """Write an accepted claim's value onto the object it is about."""
    obj = store.get(target)
    obj.set(prop, value)
    obj.attest(
        Provenance(
            agent=agent,
            method="derived",
            source=claim.id,
            confidence=confidence,
            note=f"{prop} accepted from {claim.id}",
        )
    )
    _link(store, claim, "supports", target)
    return obj


def _statement(target: str, prop: str, value: object) -> str:
    if value is None:
        return f"Evidence bears on {prop} of {target} without proposing a value."
    return f"{prop} of {target} is {value}."


def _link(store: ObjectStore, subject: AIOPObject, predicate: str, target: str) -> None:
    """Draw an edge once, and tell the index about it."""
    if target in subject.related(predicate):
        return
    subject.relate(predicate, target)
    if store.contains(subject.id):
        store.reindex(subject.id)


def contested(store: ObjectStore) -> List[AIOPObject]:
    """Claims the evidence disagrees about."""
    return [
        obj
        for obj in store.objects(types=["Claim"])
        if obj.get("status") == CONTESTED
    ]


__all__ = [
    "ACCEPTED",
    "CONTESTED",
    "ClaimOutcome",
    "UNSUPPORTED",
    "apply",
    "assemble",
    "claim_id",
    "contested",
]
