"""The Anomaly object: a trigger, written down so someone else can act on it.

An anomaly is not an opportunity, a recommendation or a verdict. It says
"something here is meaningfully different from what came before, and here is
the arithmetic that says so". Deciding whether the difference is *good* is
somebody else's job — a researcher's, a judge's — and the two must stay
separable or the listener starts having opinions about medicine.

The disposition is triage: who looks next, not what it means.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from aiop import AIOPObject, Provenance, State
from aiop.provenance import utcnow
from profiles.observer import OBSERVER_CONTEXT

from observer import observation as observation_module

from .detectors import Signal


@dataclass(frozen=True)
class AnomalyPolicy:
    """Where the thresholds sit, in one place, written down and storable.

    Thresholds are policy, not truth. Somebody has to choose them, so they are
    configuration on the capability rather than constants buried in a branch.
    """

    watch: float = 0.30
    research: float = 0.60
    escalate: float = 0.85
    #: Whether an anomaly scoring below ``watch`` is worth an object at all.
    record_ignored: bool = False

    def disposition(self, score: float) -> str:
        if score >= self.escalate:
            return "ESCALATE"
        if score >= self.research:
            return "RESEARCH"
        if score >= self.watch:
            return "WATCH"
        return "IGNORE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "watch": self.watch,
            "research": self.research,
            "escalate": self.escalate,
            "record_ignored": self.record_ignored,
        }


DEFAULT_POLICY = AnomalyPolicy()


def score_of(signals: Sequence[Signal]) -> float:
    """The strongest dimension, and nothing cleverer than that.

    Combining dimensions into a joint score means asserting how they relate —
    whether two weak signals corroborate or merely repeat — and that is a
    modelling claim v0.1 has no evidence for. The maximum is defensible,
    reproducible and easy to argue with, and every dimension's own score is
    kept alongside it so a better combiner can be fitted later.
    """
    return max((signal.score for signal in signals), default=0.0)


def build(
    observation: AIOPObject,
    signals: Sequence[Signal],
    history: Sequence[AIOPObject],
    detected_by: str,
    detector_version: str,
    observer: str,
    policy: AnomalyPolicy = DEFAULT_POLICY,
    detected_at: Optional[datetime] = None,
    context: Any = None,
) -> AIOPObject:
    """Assemble the anomaly, its reasons and its lineage. Storing is elsewhere."""
    at = detected_at or utcnow()
    score = score_of(signals)
    target = observation.get("target")
    strongest = signals[0] if signals else None
    compared = [obj.id for obj in history]

    properties: Dict[str, Any] = {
        "score": score,
        "disposition": policy.disposition(score),
        "dimensions": [signal.dimension for signal in signals],
        "signals": [signal.to_dict() for signal in signals],
        "reasons": [signal.reason for signal in signals],
        "target": target,
        "target_property": observation.get("target_property"),
        "observed_state": observation.get("value"),
        "expected_state": strongest.expected if strongest else None,
        "magnitude": strongest.magnitude if strongest else None,
        "historical_comparison": {
            "observations": len(compared),
            "values": [obj.get("value") for obj in history],
            "independence_groups": sorted(
                {
                    str(obj.get("independence_group"))
                    for obj in history
                    if obj.get("independence_group") is not None
                }
            ),
        },
        "comparison_context": compared,
        "confidence": observation.get("confidence", 1.0),
        "detected_by": detected_by,
        "detector_version": detector_version,
        "detected_at": at.isoformat(),
        "observer": observer,
        "observed_at": observation.get("observed_at"),
        "input_fingerprint": fingerprint(observation, history),
        "policy": policy.to_dict(),
    }

    anomaly = AIOPObject(
        id=identifier(observation, history, detected_by, detector_version, score),
        types=["Anomaly"],
        context=context if context is not None else list(OBSERVER_CONTEXT),
        state=State.ACTIVE,
        properties=properties,
    )
    anomaly.attest(
        Provenance(
            agent=detected_by,
            method="detected",
            source=observation.id,
            confidence=float(observation.get("confidence", 1.0)),
            generated_at=at,
            note=strongest.reason if strongest else "no dimension triggered",
        )
    )
    if target is not None:
        anomaly.relate("about", target)
    anomaly.relate("derivedFrom", observation.id)
    for identifier_ in compared:
        anomaly.relate("comparedWith", identifier_)
    anomaly.relate("detectedBy", detected_by)
    return anomaly


def fingerprint(observation: AIOPObject, history: Sequence[AIOPObject]) -> str:
    """A digest of exactly what the listener was looking at.

    Same observation, same remembered values, same answer. A different
    history is a different question, and the fingerprint is what says so.
    """
    payload = {
        "observation": [observation.id, observation.get("value")],
        "history": [[obj.id, obj.get("value")] for obj in history],
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def identifier(
    observation: AIOPObject,
    history: Sequence[AIOPObject],
    detected_by: str,
    detector_version: str,
    score: float,
) -> str:
    """A stable id: the same reading against the same memory is one anomaly."""
    digest = hashlib.sha256(
        "|".join(
            [
                fingerprint(observation, history),
                detected_by,
                detector_version,
                f"{score:.4f}",
            ]
        ).encode("utf-8")
    ).hexdigest()[:8]
    return f"{observation.id}#anomaly-{digest}"


def about(store, target: str) -> List[AIOPObject]:
    """Every anomaly standing against a target, newest first."""
    found = [
        store.find(relation.subject)
        for relation in store.inbound(target, "about")
    ]
    anomalies = [
        obj
        for obj in found
        if obj is not None and "Anomaly" in obj.types and obj.state is State.ACTIVE
    ]
    return sorted(anomalies, key=lambda obj: obj.get("detected_at", ""), reverse=True)


def comparison_values(history: Sequence[AIOPObject]) -> List[Any]:
    """The remembered values, oldest first, in the order they were observed."""
    ordered = sorted(history, key=lambda obj: (observation_module.observed_at(obj), obj.id))
    return [obj.get("value") for obj in ordered]


__all__ = [
    "AnomalyPolicy",
    "DEFAULT_POLICY",
    "about",
    "build",
    "comparison_values",
    "fingerprint",
    "identifier",
    "score_of",
]
