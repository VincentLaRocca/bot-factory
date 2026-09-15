"""Validator capability: Claim -> evidence checks -> Validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from aiop import AIOPObject
from observer.capability import CapabilityCard, CapabilityContext, CapabilityOutcome
from profiles.observer import Permission

from .evaluator import Evaluation, ValidationPolicy, evaluate_claim

CAPABILITY = "validator"
VERSION = "0.1"

CARD = CapabilityCard.build(
    capability=CAPABILITY,
    version=VERSION,
    description=(
        "Adversarially evaluates the evidence structure around a Claim and "
        "writes a Validation. It does not research, mutate the Claim or its "
        "subject, declare truth, or take action."
    ),
    accepts=("Claim",),
    produces=("Validation",),
    requires=(
        Permission.READ,
        Permission.VALIDATE,
        Permission.CREATE_OBJECT,
        Permission.RELATE_OBJECTS,
    ),
)


@dataclass
class Validator:
    policy: ValidationPolicy = ValidationPolicy()
    card: CapabilityCard = CARD

    def run(self, context: CapabilityContext) -> CapabilityOutcome:
        context.require(Permission.READ, Permission.VALIDATE)
        evaluations: List[Evaluation] = []
        created: List[AIOPObject] = []
        read: List[str] = []

        claim_types = dict(context.parameters.get("claim_types", {}))
        expected_roots = dict(context.parameters.get("expected_roots", {}))
        for claim in context.inputs:
            evaluation = evaluate_claim(
                store=context.store,
                claim=claim,
                validator=self.card.id,
                at=context.now,
                policy=self.policy,
                claim_type=claim_types.get(claim.id),
                expected_roots=expected_roots.get(claim.id, ()),
                context=None,
            )
            evaluations.append(evaluation)
            read.extend(evaluation.read)
            if evaluation.created:
                context.require(Permission.CREATE_OBJECT, Permission.RELATE_OBJECTS)
                created.append(evaluation.validation)

        return CapabilityOutcome(
            created=created,
            read=sorted(dict.fromkeys(read)),
            findings={
                "claims": [item.validation.get("claim") for item in evaluations],
                "validations": [item.validation.id for item in evaluations],
                "verdicts": {
                    item.validation.get("claim"): item.validation.get("verdict")
                    for item in evaluations
                },
                "public_verdicts": {
                    item.validation.get("claim"): item.validation.get("public_verdict")
                    for item in evaluations
                },
                "research_requests": {
                    item.validation.get("claim"): item.validation.get("research_requests")
                    for item in evaluations
                    if item.validation.get("research_requests")
                },
            },
            note=f"{len(evaluations)} claim(s) evaluated adversarially",
        )


__all__ = ["CAPABILITY", "CARD", "VERSION", "Validator"]
