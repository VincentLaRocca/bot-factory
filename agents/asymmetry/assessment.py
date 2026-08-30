"""The judgement, and the object that carries it.

Two things live here, deliberately separated. A :class:`ReasoningProvider` is
whatever forms an opinion — v0.1 ships a deterministic, rule-based one, and a
model-backed provider would implement the same protocol without any other part
of the system changing. Everything else in this module turns an opinion into an
ordinary Information Object: judgements written down where they can be
inspected, disagreed with and superseded, never merged into the facts they were
formed from.

An assessment also records the fingerprint of the objects it was formed from,
so the same question the reasoning layer answers for a calculation — "is this
still true?" — can be answered for a conclusion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from aiop import AIOPObject, Provenance, State
from store import ObjectStore

from .completeness import Completeness, Status
from .policy import AnalysisPolicy

#: Synergy and edge verdicts.
ESTABLISHED = "ESTABLISHED"
PARTIAL = "PARTIAL"
UNKNOWN = "UNKNOWN"
NO_IDENTIFIED_EDGE = "NO_IDENTIFIED_EDGE"

SYNERGY_GROUP = "synergy"


@dataclass(frozen=True)
class Dossier:
    """Everything the reasoner is allowed to reason from, and nothing else."""

    opportunity: AIOPObject
    completeness: Completeness
    policy: AnalysisPolicy
    gaps: Sequence[AIOPObject] = ()
    claims: Sequence[AIOPObject] = ()
    results: Dict[str, AIOPObject] = field(default_factory=dict)
    unavailable: Sequence[Tuple[str, str]] = ()
    cluster: Sequence[str] = ()

    def value(self, function: str) -> Optional[float]:
        """A calculated figure, or ``None`` when it could not be calculated."""
        result = self.results.get(function)
        return None if result is None else result.get("value")

    def known(self, dimension: str) -> Optional[object]:
        finding = self.completeness.by_name(dimension)
        return finding.value if finding.known else None

    def unknowns(self) -> List[str]:
        return [
            f.name
            for f in sorted(
                self.completeness.gaps(),
                key=lambda f: (-f.dimension.decision_impact, f.name),
            )
        ]


@dataclass(frozen=True)
class Judgement:
    """An opinion about an opportunity, with its reasons attached."""

    bull_case: str
    base_case: str
    bear_case: str
    confidence: float
    recommended_action: str
    priority: str
    next_action: str
    reason_for_next_action: str
    probabilities: Dict[str, float] = field(default_factory=dict)
    strengths: Sequence[str] = ()
    weaknesses: Sequence[str] = ()
    risks: Sequence[str] = ()
    primary_unknowns: Sequence[str] = ()
    invalidation_conditions: Sequence[str] = ()


class ReasoningProvider(Protocol):
    """Whatever forms the judgement — rules today, possibly a model tomorrow."""

    name: str

    def assess(self, dossier: Dossier) -> Judgement:
        """Form an opinion from the dossier, inventing no values."""


class DeterministicAnalyst:
    """A rule-based reasoner: no model, no network, no randomness.

    Every sentence it writes is assembled from figures that are already in the
    graph. Where a figure is missing it says so rather than reaching for a
    plausible number, which is the only reason a v0.1 without an LLM is worth
    having at all.
    """

    name = "deterministic/0.1"

    def assess(self, dossier: Dossier) -> Judgement:
        completeness = dossier.completeness.score
        expected_value = dossier.value("expected_value")
        asymmetry = dossier.value("asymmetry_score")
        probability = self._joint_probability(dossier)
        unknowns = dossier.unknowns()

        strengths, weaknesses, risks = self._observations(dossier)
        action, priority, next_action, reason = self._recommend(
            dossier, completeness, expected_value, asymmetry, unknowns
        )

        return Judgement(
            bull_case=self._bull(dossier, probability),
            base_case=self._base(dossier, expected_value, completeness),
            bear_case=self._bear(dossier, probability),
            probabilities=(
                {}
                if probability is None
                else {
                    "success": round(probability, 4),
                    "failure": round(1.0 - probability, 4),
                }
            ),
            strengths=strengths,
            weaknesses=weaknesses,
            risks=risks,
            primary_unknowns=unknowns[:5],
            invalidation_conditions=self._invalidation(dossier),
            confidence=self._confidence(dossier, completeness, expected_value),
            recommended_action=action,
            priority=priority,
            next_action=next_action,
            reason_for_next_action=reason,
        )

    # -- the numbers -------------------------------------------------------
    def _joint_probability(self, dossier: Dossier) -> Optional[float]:
        factors = [
            dossier.known("people.execution_probability"),
            dossier.known("technology.success_probability"),
            dossier.known("market.adoption_probability"),
        ]
        if any(factor is None for factor in factors):
            return None
        probability = 1.0
        for factor in factors:
            probability *= float(factor)
        return probability

    def _confidence(
        self, dossier: Dossier, completeness: float, expected_value: Optional[float]
    ) -> float:
        supported = [f for f in dossier.completeness if f.known]
        share = len(supported) / max(len(dossier.completeness), 1)
        calculated = 0.0 if expected_value is None else 1.0
        contested = any(f.contested for f in dossier.completeness)
        confidence = 0.5 * completeness + 0.3 * share + 0.2 * calculated
        return round(max(0.0, confidence - (0.15 if contested else 0.0)), 2)

    # -- the cases ---------------------------------------------------------
    def _bull(self, dossier: Dossier, probability: Optional[float]) -> str:
        upside = dossier.known("asymmetry.upside")
        if upside is None:
            return "No upside figure is established, so there is no bull case to state."
        if probability is None:
            return (
                f"The upside of {upside:,.0f} is realised, though the odds of getting "
                "there are not yet established."
            )
        return (
            f"Execution, the technology and adoption all hold: the upside of "
            f"{upside:,.0f} lands, which today's inputs put at a joint probability "
            f"of {probability:.0%}."
        )

    def _base(
        self, dossier: Dossier, expected_value: Optional[float], completeness: float
    ) -> str:
        if expected_value is None:
            missing = ", ".join(name for name, _ in dossier.unavailable) or "inputs"
            return (
                "Expected value cannot be calculated yet: "
                f"{missing} is missing an input. The picture is "
                f"{completeness:.0%} complete."
            )
        return (
            f"On the inputs as they stand the expected value is {expected_value:,.0f}, "
            f"from a picture that is {completeness:.0%} complete."
        )

    def _bear(self, dossier: Dossier, probability: Optional[float]) -> str:
        downside = dossier.known("asymmetry.downside")
        if downside is None:
            return "The downside is not established, which is itself the bear case."
        if probability is None:
            return f"The downside of {downside:,.0f} is lost at unquantified odds."
        return (
            f"Any one of execution, the technology or adoption fails — "
            f"{1.0 - probability:.0%} of the time on today's inputs — and the "
            f"{downside:,.0f} at risk is lost."
        )

    # -- the reasons -------------------------------------------------------
    def _observations(
        self, dossier: Dossier
    ) -> Tuple[List[str], List[str], List[str]]:
        strengths: List[str] = []
        weaknesses: List[str] = []
        risks: List[str] = []

        for finding in dossier.completeness:
            if finding.contested:
                risks.append(
                    f"{finding.name} is disputed by the evidence on file "
                    f"({len(finding.contradiction)} contradicting source(s))."
                )
            elif finding.status is Status.UNSUPPORTED:
                weaknesses.append(f"{finding.name} is asserted but unsupported.")
            elif finding.status is Status.UNREACHABLE:
                weaknesses.append(
                    f"{finding.name} has no {finding.dimension.target_type} to live on."
                )

        for name in ("people.execution_probability", "technology.success_probability"):
            value = dossier.known(name)
            if value is not None and float(value) >= 0.7:
                strengths.append(f"{name} is evidenced at {float(value):.0%}.")
            elif value is not None and float(value) < 0.5:
                risks.append(f"{name} is only {float(value):.0%}.")

        asymmetry = dossier.value("asymmetry_score")
        if asymmetry is not None and asymmetry >= dossier.policy.material_asymmetry:
            strengths.append(
                f"Probability-weighted payoff is {asymmetry:.1f}x the weighted downside."
            )
        return sorted(set(strengths)), sorted(set(weaknesses))[:6], sorted(set(risks))[:6]

    def _invalidation(self, dossier: Dossier) -> List[str]:
        declared = dossier.opportunity.get("invalidation_conditions")
        if declared:
            return list(declared)
        conditions = []
        for name in (
            "people.execution_probability",
            "technology.success_probability",
            "market.adoption_probability",
        ):
            value = dossier.known(name)
            if value is not None:
                conditions.append(
                    f"Evidence putting {name} materially below {float(value):.0%}."
                )
        return conditions

    # -- the recommendation --------------------------------------------------
    def _recommend(
        self,
        dossier: Dossier,
        completeness: float,
        expected_value: Optional[float],
        asymmetry: Optional[float],
        unknowns: Sequence[str],
    ) -> Tuple[str, str, str, str]:
        policy = dossier.policy
        top_gap = dossier.gaps[0] if dossier.gaps else None
        gap_name = top_gap.get("dimension") if top_gap is not None else (
            unknowns[0] if unknowns else "nothing outstanding"
        )

        contested = [f for f in dossier.completeness if f.contested]
        if contested:
            return (
                "RESEARCH",
                "HIGH",
                f"Settle the contradiction over {contested[0].name}.",
                "Evidence on file disagrees, and no figure should be trusted until it does not.",
            )
        if expected_value is None:
            return (
                "RESEARCH",
                "HIGH",
                f"Resolve {gap_name}.",
                "Expected value cannot be calculated while a declared input is unknown.",
            )
        if completeness < policy.minimum_completeness:
            return (
                "RESEARCH",
                "MEDIUM",
                f"Resolve {gap_name}.",
                f"The picture is {completeness:.0%} complete against a "
                f"{policy.minimum_completeness:.0%} threshold.",
            )
        if expected_value <= policy.material_expected_value:
            return (
                "REJECT",
                "LOW",
                "Archive unless the downside or the odds change.",
                f"Expected value is {expected_value:,.0f} on a reasonably complete picture.",
            )
        if asymmetry is not None and asymmetry < policy.material_asymmetry:
            return (
                "WATCH",
                "MEDIUM",
                "Re-examine when a material input moves.",
                f"Positive expected value, but the payoff is only {asymmetry:.1f}x "
                f"against a {policy.material_asymmetry:.1f}x threshold.",
            )
        access = dossier.opportunity.get("access_path")
        if access:
            return (
                "INVESTIGATE_INVESTMENT",
                "HIGH",
                f"Work the access path: {str(access).rstrip('.')}.",
                f"Expected value of {expected_value:,.0f} with a materially lopsided payoff.",
            )
        return (
            "CONTACT",
            "HIGH",
            "Find a way in: no access path is on file.",
            f"Expected value of {expected_value:,.0f}, but nothing says how we would take part.",
        )


# -- synergy and edge ------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    """A status, why it was reached, and what it was read from."""

    status: str
    rationale: str
    score: Optional[float] = None
    sources: Sequence[str] = ()


def synergy(dossier: Dossier) -> Verdict:
    """Whether human and AI genuinely need each other here.

    "Uses AI" is not synergy. The verdict is ESTABLISHED only when all four
    synergy dimensions — what each side contributes, and why neither is
    sufficient alone — are answered and evidenced.
    """
    findings = [
        f for f in dossier.completeness if f.dimension.group == SYNERGY_GROUP
    ]
    if not findings:
        return Verdict(UNKNOWN, "The specification asks nothing about synergy.")

    known = [f for f in findings if f.known]
    score = round(len(known) / len(findings), 2)
    sources = sorted({source for f in known for source in f.support})

    if len(known) == len(findings):
        return Verdict(
            ESTABLISHED,
            "Both contributions are described and evidenced, and each side is "
            "explicitly insufficient alone: "
            + "; ".join(f"{f.name} = {f.value}" for f in known[:2]),
            score,
            sources,
        )
    if known:
        missing = ", ".join(f.name for f in findings if not f.known)
        return Verdict(
            PARTIAL,
            f"Some of the synergy case is established; {missing} is not.",
            score,
            sources,
        )
    return Verdict(
        UNKNOWN,
        "Nothing on file distinguishes this from an opportunity that merely uses AI.",
        0.0,
        (),
    )


def our_edge(dossier: Dossier, policy: AnalysisPolicy) -> Verdict:
    """Why we, specifically, might be unusually placed — or why not."""
    required = dossier.opportunity.get("requires_capabilities") or []
    if not policy.capabilities:
        return Verdict(
            UNKNOWN,
            "The policy declares no capabilities, so no edge can be established.",
        )
    if not required:
        return Verdict(
            UNKNOWN,
            "The opportunity does not say what capabilities it needs.",
        )
    shared = sorted(set(policy.capabilities) & set(required))
    if not shared:
        return Verdict(
            NO_IDENTIFIED_EDGE,
            "None of our declared capabilities are among the ones this needs: "
            + ", ".join(sorted(required))
            + ".",
        )
    return Verdict(
        ESTABLISHED,
        "We hold " + ", ".join(shared) + ", which this opportunity requires.",
        round(len(shared) / len(set(required)), 2),
    )


# -- the objects -----------------------------------------------------------


def fingerprint(store: ObjectStore, sources: Sequence[str], completeness: float) -> str:
    """A digest of the objects a judgement rests on, as they stand now."""
    payload = {
        "completeness": completeness,
        "sources": sorted(
            [source, _source_state(store, source)] for source in set(sources)
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_state(store: ObjectStore, source: str) -> str:
    obj = store.find(source)
    if obj is None:
        return "absent"
    marker = obj.get("inputFingerprint") or obj.get("claimed_value") or obj.get("value")
    return f"{obj.state.value}:{marker}"


def assessment_id(root: str, digest: str) -> str:
    return f"{root}#assessment-{digest[:12]}"


def build(
    store: ObjectStore,
    dossier: Dossier,
    judgement: Judgement,
    synergy_verdict: Verdict,
    edge_verdict: Verdict,
    agent: str,
    context: object,
    reasoner: str,
) -> Tuple[AIOPObject, List[AIOPObject]]:
    """Write the judgement down: an Assessment, a synergy view and an edge."""
    sources = _sources(dossier)
    digest = fingerprint(store, sources, dossier.completeness.score)
    root = dossier.opportunity.id

    assessment = AIOPObject(
        id=assessment_id(root, digest),
        types=["Assessment"],
        context=context,
        state=State.ACTIVE,
        properties={
            "bull_case": judgement.bull_case,
            "base_case": judgement.base_case,
            "bear_case": judgement.bear_case,
            "probabilities": dict(judgement.probabilities),
            "strengths": list(judgement.strengths),
            "weaknesses": list(judgement.weaknesses),
            "risks": list(judgement.risks),
            "primary_unknowns": list(judgement.primary_unknowns),
            "invalidation_conditions": list(judgement.invalidation_conditions),
            "confidence": judgement.confidence,
            "recommended_action": judgement.recommended_action,
            "priority": judgement.priority,
            "next_action": judgement.next_action,
            "reason_for_next_action": judgement.reason_for_next_action,
            "completeness": dossier.completeness.score,
            "sources": list(sources),
            "inputFingerprint": digest,
        },
    )
    assessment.attest(
        Provenance(
            agent=agent,
            method="inferred",
            source=root,
            confidence=judgement.confidence,
            note=f"judged by {reasoner} over {len(sources)} objects",
        )
    )
    assessment.relate("about", root)
    for source in sources:
        assessment.relate("derivedFrom", source)

    companions = [
        _verdict_object(
            f"{root}#synergy-{digest[:12]}",
            "SynergyAssessment",
            synergy_verdict,
            root,
            agent,
            context,
            "human_ai_synergy_score",
        ),
        _verdict_object(
            f"{root}#edge-{digest[:12]}",
            "OurEdge",
            edge_verdict,
            root,
            agent,
            context,
            "score",
        ),
    ]
    synergy_object, edge_object = companions
    assessment.relate("synergyAssessment", synergy_object.id)
    assessment.relate("ourEdge", edge_object.id)
    for companion in companions:
        assessment.relate("derivedFrom", companion.id)
    return assessment, companions


def _verdict_object(
    identifier: str,
    type_name: str,
    verdict: Verdict,
    root: str,
    agent: str,
    context: object,
    score_property: str,
) -> AIOPObject:
    obj = AIOPObject(
        id=identifier,
        types=[type_name],
        context=context,
        state=State.ACTIVE,
        properties={"status": verdict.status, "rationale": verdict.rationale},
    )
    if verdict.score is not None:
        obj.set(score_property, verdict.score)
    obj.attest(Provenance(agent=agent, method="inferred", source=root))
    obj.relate("about", root)
    for source in verdict.sources:
        obj.relate("derivedFrom", source)
    return obj


def _sources(dossier: Dossier) -> List[str]:
    """Everything the judgement rests on: results, claims and evidence."""
    sources = {result.id for result in dossier.results.values()}
    sources.update(claim.id for claim in dossier.claims)
    for finding in dossier.completeness:
        sources.update(finding.support)
        sources.update(finding.contradiction)
    return sorted(sources)


def check(store: ObjectStore, assessment: AIOPObject) -> Tuple[bool, str]:
    """Whether an assessment still rests on the graph it was formed from."""
    recorded = assessment.get("inputFingerprint")
    if not recorded:
        return True, "the assessment carries no input fingerprint"

    sources = assessment.get("sources", [])
    missing = [source for source in sources if not store.contains(source)]
    if missing:
        return True, f"{len(missing)} source object(s) are no longer in the store"

    superseded = [
        source
        for source in sources
        if store.get(source).state is State.SUPERSEDED
    ]
    completeness = assessment.get("completeness", 0.0)
    current = fingerprint(store, sources, completeness)
    if superseded:
        return True, f"{len(superseded)} source object(s) have been superseded"
    if current != recorded:
        return True, "a source object has changed"
    return False, "sources unchanged"


def is_stale(store: ObjectStore, assessment: AIOPObject) -> bool:
    return check(store, assessment)[0]


def current_assessments(store: ObjectStore, root: str) -> List[AIOPObject]:
    """Standing assessments about one opportunity, newest identifier first."""
    return sorted(
        (
            store.get(relation.subject)
            for relation in store.inbound(root, "about")
            if store.contains(relation.subject)
            and store.get(relation.subject).has_type("Assessment")
            and store.get(relation.subject).state is not State.SUPERSEDED
        ),
        key=lambda obj: obj.id,
    )


__all__ = [
    "DeterministicAnalyst",
    "Dossier",
    "ESTABLISHED",
    "Judgement",
    "NO_IDENTIFIED_EDGE",
    "PARTIAL",
    "ReasoningProvider",
    "UNKNOWN",
    "Verdict",
    "assessment_id",
    "build",
    "check",
    "current_assessments",
    "fingerprint",
    "is_stale",
    "our_edge",
    "synergy",
]
