"""The Researcher: the second plug-in, and the test of whether the first was luck.

It answers one question — *what do sources say about this anomaly?* — and
refuses every neighbouring one. It does not decide whether the anomaly matters,
does not update the target object, does not accept its own claims, and does not
invent an explanation when nobody supplied one.

```python
observer.install(Researcher(provider))
result = observer.invoke("researcher", inputs=[anomaly])
result.findings["topics"]["cause"]   # 'UNKNOWN' is a legitimate answer
```

The chassis was not modified to make this work, and there is no
``ResearchObserver``. A researcher and an anomaly listener are different kinds
of thinking plugged into the same board.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aiop import AIOPObject
from aiop.provenance import utcnow
from observer.capability import CapabilityCard, CapabilityContext, CapabilityOutcome
from profiles.observer import Permission
from profiles.research import TOPICS

from . import findings as findings_module
from .findings import Investigation
from .provider import (
    ResearchProvider,
    ResearchRequest,
    SilentResearchProvider,
    questions_for,
)

CAPABILITY = "researcher"
VERSION = "0.1"

CARD = CapabilityCard.build(
    capability=CAPABILITY,
    version=VERSION,
    description=(
        "Investigates an anomaly against supplied research sources and files "
        "what they said as Evidence, with Claims for the propositions that "
        "evidence bears on. Reports what it could not establish rather than "
        "filling the hole: it gathers and attributes, it does not adjudicate."
    ),
    accepts=("Anomaly",),
    produces=("Evidence", "Claim"),
    requires=(
        Permission.READ,
        Permission.RESEARCH,
        Permission.CREATE_OBJECT,
        Permission.RELATE_OBJECTS,
    ),
)


@dataclass
class Researcher:
    """Investigation as a capability, with its sources behind an interface."""

    provider: ResearchProvider = field(default_factory=SilentResearchProvider)
    topics: Tuple[str, ...] = TOPICS
    card: CapabilityCard = CARD

    # -- the capability interface -----------------------------------------
    def run(self, context: CapabilityContext) -> CapabilityOutcome:
        created: List[AIOPObject] = []
        read: List[str] = []
        investigations: List[Investigation] = []

        for anomaly in context.inputs:
            investigation = self.investigate(context, anomaly)
            investigations.append(investigation)
            created.extend(investigation.created)
            read.extend([anomaly.id, *investigation.read])

        return CapabilityOutcome(
            status="COMPLETE",
            created=created,
            read=sorted(dict.fromkeys(read)),
            findings={
                "provider": self.provider.name,
                "provider_version": self.provider.version,
                "anomalies": [item.anomaly for item in investigations],
                "evidence": [obj.id for item in investigations for obj in item.evidence],
                "claims": [obj.id for item in investigations for obj in item.claims],
                "contested": [
                    obj.id for item in investigations for obj in item.contested
                ],
                "unresolved": sorted(
                    {
                        outcome.topic
                        for item in investigations
                        for outcome in item.topics
                        if outcome.status
                        in (findings_module.UNKNOWN, findings_module.UNREACHABLE)
                    }
                ),
                "investigations": [item.to_dict() for item in investigations],
            },
            note=f"{len(investigations)} anomaly(ies) investigated",
        )

    # -- the work ----------------------------------------------------------
    def investigate(
        self, context: CapabilityContext, anomaly: AIOPObject
    ) -> Investigation:
        """Ask the sources about one anomaly and write down what they said."""
        context.require(Permission.READ)
        store = context.store
        if not store.contains(anomaly.id):
            context.require(Permission.CREATE_OBJECT)
            store.add(anomaly)

        request = self.ask(context, anomaly)

        context.require(Permission.RESEARCH)
        response = self.provider.research(request)

        if response.findings:
            context.require(Permission.CREATE_OBJECT, Permission.RELATE_OBJECTS)

        return findings_module.assemble(
            store=store,
            anomaly=anomaly,
            request=request,
            response=response,
            researcher=self.card.id,
            at=context.now or utcnow(),
            context=context.context,
        )

    def ask(self, context: CapabilityContext, anomaly: AIOPObject) -> ResearchRequest:
        """Restate the anomaly as questions, carrying facts and not opinions.

        The anomaly's score and disposition are deliberately left behind. A
        source told that something is already thought to be a big deal is a
        source being led.
        """
        target = anomaly.get("target") or _first(anomaly.related("about"))
        wanted = context.parameters.get("topics") or self.topics
        return ResearchRequest(
            anomaly=anomaly.id,
            target=target,
            target_property=anomaly.get("target_property"),
            observed_state=anomaly.get("observed_state"),
            expected_state=anomaly.get("expected_state"),
            magnitude=anomaly.get("magnitude"),
            observed_at=anomaly.get("detected_at"),
            asked_at=context.now,
            questions=questions_for(
                target=target,
                target_property=anomaly.get("target_property"),
                observed_state=anomaly.get("observed_state"),
                expected_state=anomaly.get("expected_state"),
                topics=tuple(wanted),
            ),
            parameters=dict(context.parameters),
        )


def _first(values: Sequence[str]) -> Optional[str]:
    return values[0] if values else None


def unresolved(outcome: CapabilityOutcome) -> Dict[str, Any]:
    """The topics an investigation left open, for callers that want only those."""
    return {
        investigation["anomaly"]: [
            topic
            for topic, status in investigation["topics"].items()
            if status in (findings_module.UNKNOWN, findings_module.UNREACHABLE)
        ]
        for investigation in outcome.findings.get("investigations", ())
    }


__all__ = ["CAPABILITY", "CARD", "Researcher", "VERSION", "unresolved"]
