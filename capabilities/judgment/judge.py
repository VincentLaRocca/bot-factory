"""Judge capability: Validation -> bounded, non-acting Decision.

The Judge reads a Validation; it does not redo the Validator's work.  Its
output is deliberately adjacent to the Claim.  A Decision may carry or weaken
the evidentiary verdict, but it may never upgrade it and never writes through
to the Claim or the real-world subject.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from aiop import AIOPObject, Provenance, State
from capabilities.validation import (
    CONTRADICTED,
    SUPPORTED,
    UNRESOLVED,
    UNTESTABLE,
    VERDICTS,
    WEAKLY_SUPPORTED,
)
from observer.capability import CapabilityCard, CapabilityContext, CapabilityOutcome
from profiles.observer import Permission
from profiles.validation import VALIDATION_CONTEXT

CAPABILITY = "judge"
VERSION = "0.1"

CARD = CapabilityCard.build(
    capability=CAPABILITY,
    version=VERSION,
    description=(
        "Reads a Validation and writes a bounded Decision for human review. "
        "It may preserve or weaken the verdict; it cannot upgrade evidence, "
        "mutate a Claim, or authorize an external action."
    ),
    accepts=("Validation",),
    produces=("Decision",),
    requires=(
        Permission.READ,
        Permission.RECOMMEND,
        Permission.CREATE_OBJECT,
        Permission.RELATE_OBJECTS,
    ),
    dependencies=("validator",),
)

ALLOWED: Dict[str, Set[str]] = {
    SUPPORTED: {SUPPORTED, WEAKLY_SUPPORTED, UNRESOLVED, UNTESTABLE},
    WEAKLY_SUPPORTED: {WEAKLY_SUPPORTED, UNRESOLVED, UNTESTABLE},
    UNRESOLVED: {UNRESOLVED, UNTESTABLE},
    CONTRADICTED: {CONTRADICTED, UNTESTABLE},
    UNTESTABLE: {UNTESTABLE},
}

PUBLIC = {
    SUPPORTED: "PASS",
    WEAKLY_SUPPORTED: "INCONCLUSIVE_COVERAGE",
    UNRESOLVED: "INCONCLUSIVE_EVIDENCE",
    CONTRADICTED: "INVALID",
    UNTESTABLE: "UNTESTABLE",
}

RECOMMENDATION = {
    SUPPORTED: "PRESENT_TO_HUMAN",
    WEAKLY_SUPPORTED: "PRESENT_WITH_LIMITS",
    UNRESOLVED: "SEEK_MORE_EVIDENCE",
    CONTRADICTED: "DO_NOT_RELY",
    UNTESTABLE: "REFRAME_CLAIM",
}


@dataclass
class Judge:
    card: CapabilityCard = CARD

    def run(self, context: CapabilityContext) -> CapabilityOutcome:
        context.require(Permission.READ, Permission.RECOMMEND)
        created: List[AIOPObject] = []
        read: List[str] = []
        decisions: List[AIOPObject] = []
        requested = dict(context.parameters.get("verdicts", {}))

        for validation in context.inputs:
            if not validation.has_type("Validation"):
                raise ValueError(f"'{validation.id}' is not a Validation")
            if not context.store.contains(validation.id):
                raise ValueError(f"validation '{validation.id}' is not in the store")
            decision = self.decide(
                validation,
                requested.get(validation.id),
                context,
            )
            existing = context.store.find(decision.id)
            if existing is None:
                context.require(Permission.CREATE_OBJECT, Permission.RELATE_OBJECTS)
                context.store.add(decision)
                created.append(decision)
            else:
                decision = existing
            decisions.append(decision)
            read.extend([validation.id, validation.get("claim")])

        return CapabilityOutcome(
            created=created,
            read=sorted(dict.fromkeys(item for item in read if item)),
            findings={
                "validations": [item.get("validation") for item in decisions],
                "decisions": [item.id for item in decisions],
                "verdicts": {
                    item.get("claim"): item.get("verdict") for item in decisions
                },
                "human_review_required": True,
                "authorized_action": "NONE",
            },
            note=f"{len(decisions)} provisional decision(s) written for human review",
        )

    def decide(
        self,
        validation: AIOPObject,
        requested: Optional[str],
        context: CapabilityContext,
    ) -> AIOPObject:
        source = validation.get("verdict")
        if source not in VERDICTS:
            raise ValueError(f"validation '{validation.id}' has unknown verdict '{source}'")

        verdict = source
        reasons: List[str] = []
        if requested is not None:
            if requested not in VERDICTS:
                reasons.append(f"ignored unknown requested verdict: {requested}")
            elif requested in ALLOWED[source]:
                verdict = requested
                if verdict != source:
                    reasons.append(f"human-supplied bound weakened {source} to {verdict}")
            else:
                reasons.append(f"refused evidentiary upgrade from {source} to {requested}")

        if not reasons:
            reasons.append("carried the Validator verdict without evidentiary upgrade")

        public = validation.get("public_verdict") if verdict == source else PUBLIC[verdict]
        digest = hashlib.sha256(
            f"{validation.id}|{source}|{verdict}|{requested}".encode("utf-8")
        ).hexdigest()[:12]
        decision = AIOPObject(
            id=f"{validation.id}#decision-{digest}",
            types=["Decision"],
            context=list(VALIDATION_CONTEXT),
            state=State.PROPOSED,
            properties={
                "validation": validation.id,
                "claim": validation.get("claim"),
                "source_verdict": source,
                "verdict": verdict,
                "public_verdict": public,
                "confidence": float(validation.get("confidence", 0.0)),
                "confidence_label": validation.get("confidence_label", "LOW"),
                "confidence_kind": "estimate",
                "recommendation": RECOMMENDATION[verdict],
                "reasons": reasons,
                "research_requests": validation.get("research_requests", []),
                "human_review_required": True,
                "authorized_action": "NONE",
                "decided_at": context.now.isoformat() if context.now else None,
                "calibration": {"observed_outcome": None},
            },
        )
        decision.attest(Provenance(
            agent=self.card.id,
            method="recommended",
            source=validation.id,
            confidence=float(validation.get("confidence", 0.0)),
            generated_at=context.now,
            note="provisional recommendation; human principal retains final authority",
        ))
        decision.relate("basedOn", validation.id)
        claim = validation.get("claim")
        if claim:
            decision.relate("decisionFor", claim)
        return decision


__all__ = ["ALLOWED", "CAPABILITY", "CARD", "Judge", "VERSION"]
