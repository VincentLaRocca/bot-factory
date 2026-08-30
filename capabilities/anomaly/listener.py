"""The Anomaly Listener: the first plug-in, and the proof the chassis works.

It answers one question — *is something meaningfully different here?* — and
refuses the next one. It holds no memory of its own: the comparison history
comes out of the store every time, so the same observation read against a
different past gives a different answer, which is the entire point of putting
memory in AIOP rather than in an agent.

```python
observer.install(AnomalyListener())
result = observer.invoke("anomaly_listener", inputs=[observation])
result.findings["disposition"]   # 'ESCALATE'
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aiop import AIOPObject
from observer import observation as observation_module
from observer.capability import CapabilityCard, CapabilityContext, CapabilityOutcome
from profiles.observer import Permission

from . import anomaly as anomaly_module
from .anomaly import AnomalyPolicy, DEFAULT_POLICY
from .detectors import Comparison, DEFAULT_DETECTORS, DetectorRegistry

CAPABILITY = "anomaly_listener"
VERSION = "0.1"

CARD = CapabilityCard.build(
    capability=CAPABILITY,
    version=VERSION,
    description=(
        "Compares an observation against the stored history of the same target "
        "and property and reports whether something is meaningfully different. "
        "Produces an Anomaly, never an Opportunity: it detects difference, it "
        "does not judge value."
    ),
    accepts=("Observation",),
    produces=("Anomaly",),
    requires=(
        Permission.READ,
        Permission.OBSERVE,
        Permission.CREATE_OBJECT,
        Permission.RELATE_OBJECTS,
    ),
)


@dataclass
class Detection:
    """One observation, what it was compared against, and what came of it."""

    observation: AIOPObject
    history: Sequence[AIOPObject]
    signals: Sequence[Any]
    score: float
    disposition: str
    anomaly: Optional[AIOPObject] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation": self.observation.id,
            "target": self.observation.get("target"),
            "target_property": self.observation.get("target_property"),
            "compared_with": [obj.id for obj in self.history],
            "score": self.score,
            "disposition": self.disposition,
            "dimensions": [signal.dimension for signal in self.signals],
            "reasons": [signal.reason for signal in self.signals],
            "anomaly": self.anomaly.id if self.anomaly is not None else None,
        }


@dataclass
class AnomalyListener:
    """Difference detection, as a capability rather than as a kind of observer."""

    policy: AnomalyPolicy = DEFAULT_POLICY
    detectors: DetectorRegistry = field(default_factory=lambda: DEFAULT_DETECTORS)
    card: CapabilityCard = CARD

    # -- the capability interface -----------------------------------------
    def run(self, context: CapabilityContext) -> CapabilityOutcome:
        created: List[AIOPObject] = []
        read: List[str] = []
        detections: List[Detection] = []

        for observation in context.inputs:
            detection, written, seen = self.listen(context, observation)
            detections.append(detection)
            created.extend(written)
            read.extend(seen)

        highest = max((d.score for d in detections), default=0.0)
        return CapabilityOutcome(
            status="COMPLETE",
            created=created,
            read=sorted(dict.fromkeys(read)),
            findings={
                "score": highest,
                "disposition": self.policy.disposition(highest),
                "anomalies": [
                    d.anomaly.id for d in detections if d.anomaly is not None
                ],
                "detections": [d.to_dict() for d in detections],
            },
            note=f"{len(detections)} observation(s) compared",
        )

    # -- the work ----------------------------------------------------------
    def listen(
        self, context: CapabilityContext, observation: AIOPObject
    ) -> Tuple[Detection, List[AIOPObject], List[str]]:
        """Compare one observation with the store's memory of its subject."""
        store = context.store
        created: List[AIOPObject] = []

        # The observation may be brand new, or may already be part of the
        # graph. Either way it belongs in the store before anything is derived
        # from it: an anomaly whose evidence was never persisted is hearsay.
        if not store.contains(observation.id):
            context.require(Permission.CREATE_OBJECT)
            created.append(observation_module.record(store, observation))

        history = self.recall(context, observation)
        comparison = Comparison(
            target=observation.get("target"),
            value=observation.get("value"),
            target_property=observation.get("target_property"),
            values=tuple(anomaly_module.comparison_values(history)),
            at=observation_module.observed_at(observation),
            expected_range=self.expected_range(context, observation),
        )
        signals = self.detectors.run(comparison)
        score = anomaly_module.score_of(signals)
        disposition = self.policy.disposition(score)

        anomaly: Optional[AIOPObject] = None
        if disposition != "IGNORE" or self.policy.record_ignored:
            context.require(Permission.CREATE_OBJECT, Permission.RELATE_OBJECTS)
            anomaly = anomaly_module.build(
                observation=observation,
                signals=signals,
                history=history,
                detected_by=self.card.id,
                detector_version=self.card.version,
                observer=context.observer,
                policy=self.policy,
                detected_at=context.now,
                context=context.context,
            )
            existing = store.find(anomaly.id)
            anomaly = existing if existing is not None else store.add(anomaly)
            if existing is None:
                created.append(anomaly)

        detection = Detection(
            observation=observation,
            history=history,
            signals=signals,
            score=score,
            disposition=disposition,
            anomaly=anomaly,
        )
        read = [observation.id, *(obj.id for obj in history)]
        return detection, created, read

    def recall(
        self, context: CapabilityContext, observation: AIOPObject
    ) -> List[AIOPObject]:
        """The remembered observations this one is read against.

        Memory is the store's, not the listener's: same reading, different
        history, different answer — and any process can inspect the history
        that produced a score.
        """
        context.require(Permission.READ)
        return observation_module.history(
            store=context.store,
            target=observation.get("target"),
            target_property=observation.get("target_property"),
            before=observation_module.observed_at(observation),
            exclude=(observation.id,),
        )

    def expected_range(
        self, context: CapabilityContext, observation: AIOPObject
    ) -> Optional[Tuple[float, float]]:
        """A declared expectation, if the mission or caller supplied one."""
        ranges = context.parameters.get("expected_range") or {}
        key = observation.get("target_property")
        declared = ranges.get(key) if isinstance(ranges, dict) else None
        if declared is None:
            return None
        low, high = declared
        return float(low), float(high)


__all__ = [
    "AnomalyListener",
    "CAPABILITY",
    "CARD",
    "Detection",
    "VERSION",
]
