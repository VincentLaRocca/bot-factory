"""Deterministic, adversarial evaluation of a Claim's evidence picture.

The evaluator does not search, persuade, or promote.  It reads the evidence
already committed to the graph, runs explicit mechanical checks, and writes a
new Validation beside the Claim.  Missing evidence is an outcome, not an
invitation to guess.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from aiop import AIOPObject, Provenance, State
from profiles.validation import VALIDATION_CONTEXT
from store import ObjectStore

SUPPORTED = "SUPPORTED"
WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"
UNRESOLVED = "UNRESOLVED"
CONTRADICTED = "CONTRADICTED"
UNTESTABLE = "UNTESTABLE"

VERDICTS = (
    SUPPORTED,
    WEAKLY_SUPPORTED,
    UNRESOLVED,
    CONTRADICTED,
    UNTESTABLE,
)

CLAIM_TYPES = (
    "factual",
    "quantitative",
    "causal",
    "predictive",
    "comparative",
    "interpretive",
    "recommendation",
    "assumption",
)


@dataclass(frozen=True)
class ValidationPolicy:
    """The small set of thresholds v0.1 is willing to assert."""

    minimum_independent_roots: int = 2
    maximum_age_days: Optional[int] = None
    causal_source_types: Tuple[str, ...] = (
        "experiment",
        "randomized_trial",
        "causal_analysis",
        "controlled_study",
    )


@dataclass(frozen=True)
class Evaluation:
    validation: AIOPObject
    evidence: Tuple[AIOPObject, ...]
    created: bool

    @property
    def read(self) -> Tuple[str, ...]:
        return tuple([self.validation.get("claim"), *[obj.id for obj in self.evidence]])


def evaluate_claim(
    store: ObjectStore,
    claim: AIOPObject,
    validator: str,
    at: Optional[datetime] = None,
    policy: ValidationPolicy = ValidationPolicy(),
    claim_type: Optional[str] = None,
    expected_roots: Iterable[str] = (),
    context: Any = None,
) -> Evaluation:
    """Evaluate one stored Claim without changing it or anything it is about."""
    if not claim.has_type("Claim"):
        raise ValueError(f"'{claim.id}' is not a Claim")
    if not store.contains(claim.id):
        raise ValueError(f"claim '{claim.id}' is not in the store")

    evaluated_at = at or datetime.now(timezone.utc)
    kind = claim_type or claim.get("claim_type") or "factual"
    statement = _normalise(claim.get("statement", ""))

    supporting = _bearing(store, claim.id, "supports")
    contradicting = _bearing(store, claim.id, "contradicts")
    qualifying = _bearing(store, claim.id, "qualifies")
    evidence = _unique([*supporting, *contradicting, *qualifying])
    invalid_confidence = [obj for obj in evidence if _confidence_value(obj) is None]

    aligned_support, misaligned = _aligned(claim, supporting)
    roots = _roots(aligned_support)
    expected = tuple(sorted(set(expected_roots)))
    missing_roots = sorted(set(expected) - set(roots))
    assumptions = _as_list(claim.get("assumptions", ()))
    missing: List[str] = []
    failures: List[str] = []
    requests: List[str] = []
    causal_warnings: List[str] = []
    quantitative_checks: List[Dict[str, Any]] = []

    tests: List[Dict[str, Any]] = []
    tests.append(_test("claim_precision", bool(statement), "claim has a non-empty proposition"))
    tests.append(_test(
        "evidence_sufficiency",
        bool(aligned_support),
        f"{len(aligned_support)} aligned supporting item(s)",
    ))
    tests.append(_test(
        "source_independence",
        len(roots) >= policy.minimum_independent_roots,
        f"{len(roots)} independent evidence root(s)",
    ))
    tests.append(_test(
        "coverage_completeness",
        not missing_roots,
        f"{len(missing_roots)} expected evidence root(s) absent",
    ))
    tests.append(_test(
        "claim_evidence_alignment",
        not misaligned,
        f"{len(misaligned)} supporting item(s) have a different dimension",
    ))
    tests.append(_test(
        "contradiction_search",
        not contradicting,
        f"{len(contradicting)} contradicting item(s) retained",
    ))
    tests.append(_test(
        "confidence_format",
        not invalid_confidence,
        f"{len(invalid_confidence)} evidence confidence value(s) are missing, non-numeric, or outside 0..1",
    ))

    if not aligned_support:
        missing.append("aligned supporting evidence")
        requests.append("Find evidence that directly bears on the stated proposition.")
    if aligned_support and len(roots) < policy.minimum_independent_roots:
        missing.append("independent corroboration")
        requests.append("Seek corroboration from a genuinely independent evidence root.")
    if missing_roots:
        missing.append("expected evidence roots: " + ", ".join(missing_roots))
        requests.append("Complete the frozen evidence-root manifest before relying on the claim.")
    if misaligned:
        failures.append("supporting evidence does not align with the claim dimension")
    if contradicting:
        failures.append("counter-evidence directly contradicts the claim")
        requests.append("Resolve or explain the retained contradictory evidence.")
    if invalid_confidence:
        missing.append("valid confidence estimates for every evidence item")
        failures.append("malformed evidence confidence")

    if kind not in CLAIM_TYPES:
        failures.append(f"unknown claim type: {kind}")

    if kind == "causal":
        causal = [obj for obj in aligned_support if _is_causal(obj, policy)]
        passed = bool(causal)
        tests.append(_test(
            "causal_evidence",
            passed,
            f"{len(causal)} supporting item(s) declare a causal method",
        ))
        if not passed:
            causal_warnings.append("A causal claim has correlation or assertion, but no declared causal method.")
            missing.append("causal evidence")
            requests.append("Find evidence using an explicit causal identification method.")

    if kind == "quantitative":
        has_value = "claimed_value" in claim
        matched = [
            obj for obj in aligned_support
            if obj.get("claimed_value") == claim.get("claimed_value")
        ]
        quantitative_checks = [
            _test("declared_value", has_value, "claim declares the value being tested"),
            _test(
                "value_alignment",
                bool(matched) if has_value else False,
                f"{len(matched)} supporting item(s) report the declared value",
            ),
        ]
        tests.extend(quantitative_checks)
        if not has_value:
            failures.append("quantitative claim does not declare claimed_value")
        elif not matched:
            missing.append("evidence for the declared quantitative value")

    stale = _stale(evidence, evaluated_at, policy.maximum_age_days)
    if policy.maximum_age_days is not None:
        tests.append(_test(
            "recency",
            not stale,
            f"{len(stale)} item(s) exceed the {policy.maximum_age_days}-day limit or lack a source date",
        ))
        if stale:
            missing.append("evidence within the declared recency window")
            requests.append("Refresh evidence whose source date is missing or stale.")

    verdict, public_verdict = _verdict(
        statement=statement,
        kind=kind,
        support=aligned_support,
        contradicting=contradicting,
        roots=roots,
        policy=policy,
        causal_warnings=causal_warnings,
        quantitative_checks=quantitative_checks,
        stale=stale,
        missing_roots=missing_roots,
        invalid_confidence=invalid_confidence,
    )
    confidence = _confidence([*aligned_support, *contradicting], verdict)
    counterargument = _strongest(contradicting or qualifying)
    fingerprint = _fingerprint(
        claim, evidence, policy, kind, expected, evaluated_at
    )
    identifier = f"{claim.id}#validation-{fingerprint[:12]}"

    existing = store.find(identifier)
    if existing is not None:
        return Evaluation(existing, tuple(evidence), False)

    properties: Dict[str, Any] = {
        "claim": claim.id,
        "claim_type": kind,
        "normalized_claim": statement,
        "propositions": [statement] if statement else [],
        "evidence": [obj.id for obj in supporting],
        "counter_evidence": [obj.id for obj in contradicting],
        "qualifying_evidence": [obj.id for obj in qualifying],
        "source_universe": [obj.id for obj in evidence],
        "independence_roots": list(roots),
        "expected_independence_roots": list(expected),
        "assumption_ledger": assumptions,
        "tests": tests,
        "contradictions": [_evidence_note(obj) for obj in contradicting],
        "causal_warnings": causal_warnings,
        "quantitative_checks": quantitative_checks,
        "provenance_notes": [_provenance_note(obj) for obj in evidence],
        "missing_information": _dedupe(missing),
        "research_requests": _dedupe(requests),
        "failure_reasons": _dedupe(failures),
        "strongest_counterargument": counterargument,
        "verdict": verdict,
        "public_verdict": public_verdict,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "confidence_kind": "estimate",
        "input_fingerprint": fingerprint,
        "evaluated_at": evaluated_at.isoformat(),
        "calibration": {"observed_outcome": None},
    }
    validation = AIOPObject(
        id=identifier,
        types=["Validation"],
        context=context if context is not None else list(VALIDATION_CONTEXT),
        state=State.ACTIVE,
        properties=properties,
    )
    validation.attest(Provenance(
        agent=validator,
        method="validated",
        source=claim.id,
        confidence=confidence,
        generated_at=evaluated_at,
        note="mechanical evidence-structure evaluation; not a truth declaration",
    ))
    validation.relate("validationOf", claim.id)
    for obj in evidence:
        validation.relate("derivedFrom", obj.id)
    store.add(validation)
    return Evaluation(validation, tuple(evidence), True)


def _bearing(store: ObjectStore, claim: str, predicate: str) -> List[AIOPObject]:
    objects = [store.find(edge.subject) for edge in store.inbound(claim, predicate)]
    return sorted(
        (obj for obj in objects if obj is not None and obj.state is State.ACTIVE),
        key=lambda obj: obj.id,
    )


def _unique(objects: Iterable[AIOPObject]) -> List[AIOPObject]:
    objects_by_id = {obj.id: obj for obj in objects}
    return [objects_by_id[key] for key in sorted(objects_by_id)]


def _aligned(claim: AIOPObject, evidence: Sequence[AIOPObject]) -> Tuple[List[AIOPObject], List[AIOPObject]]:
    dimension = claim.get("dimension")
    if dimension is None:
        return list(evidence), []
    aligned = [obj for obj in evidence if obj.get("dimension") == dimension]
    return aligned, [obj for obj in evidence if obj not in aligned]


def _roots(evidence: Sequence[AIOPObject]) -> Tuple[str, ...]:
    return tuple(sorted({
        str(obj.get("independence_group") or obj.get("source") or obj.id)
        for obj in evidence
    }))


def _is_causal(evidence: AIOPObject, policy: ValidationPolicy) -> bool:
    return bool(evidence.get("causal")) or evidence.get("source_type") in policy.causal_source_types


def _stale(
    evidence: Sequence[AIOPObject], at: datetime, maximum_age_days: Optional[int]
) -> List[AIOPObject]:
    if maximum_age_days is None:
        return []
    stale: List[AIOPObject] = []
    for obj in evidence:
        raw = obj.get("source_date")
        try:
            observed = date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            stale.append(obj)
            continue
        if (at.date() - observed).days > maximum_age_days:
            stale.append(obj)
    return stale


def _verdict(
    statement: str,
    kind: str,
    support: Sequence[AIOPObject],
    contradicting: Sequence[AIOPObject],
    roots: Sequence[str],
    policy: ValidationPolicy,
    causal_warnings: Sequence[str],
    quantitative_checks: Sequence[Mapping[str, Any]],
    stale: Sequence[AIOPObject],
    missing_roots: Sequence[str],
    invalid_confidence: Sequence[AIOPObject],
) -> Tuple[str, str]:
    if not statement or kind not in CLAIM_TYPES:
        return UNTESTABLE, "UNTESTABLE"
    if kind == "quantitative" and any(not check["passed"] for check in quantitative_checks):
        return UNTESTABLE, "UNTESTABLE"
    if invalid_confidence:
        return UNRESOLVED, "INCONCLUSIVE_EVIDENCE"
    if support and contradicting:
        return UNRESOLVED, "MIXED"
    if contradicting and not support:
        return CONTRADICTED, "INVALID"
    if not support:
        return UNRESOLVED, "INCONCLUSIVE_EVIDENCE"
    if causal_warnings or stale:
        return UNRESOLVED, "INCONCLUSIVE_EVIDENCE"
    if missing_roots:
        return UNRESOLVED, "INCONCLUSIVE_COVERAGE"
    if len(roots) < policy.minimum_independent_roots:
        return WEAKLY_SUPPORTED, "INCONCLUSIVE_COVERAGE"
    return SUPPORTED, "PASS"


def _confidence(evidence: Sequence[AIOPObject], verdict: str) -> float:
    if not evidence or verdict == UNTESTABLE:
        return 0.0
    values = [value for obj in evidence if (value := _confidence_value(obj)) is not None]
    if not values:
        return 0.0
    value = min(values)  # the weakest essential reading, never an agreement bonus
    if verdict == WEAKLY_SUPPORTED:
        value = min(value, 0.59)
    if verdict == UNRESOLVED:
        value = min(value, 0.49)
    return round(value, 4)


def _confidence_label(value: float) -> str:
    if value >= 0.8:
        return "HIGH"
    if value >= 0.5:
        return "MEDIUM"
    return "LOW"


def _strongest(evidence: Sequence[AIOPObject]) -> Optional[str]:
    if not evidence:
        return None
    strongest = max(
        evidence,
        key=lambda obj: (_confidence_value(obj) or -1.0, obj.id),
    )
    return strongest.get("content") or strongest.get("title") or strongest.id


def _normalise(statement: Any) -> str:
    return " ".join(str(statement or "").split())


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _test(name: str, passed: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _evidence_note(obj: AIOPObject) -> Dict[str, Any]:
    return {
        "evidence": obj.id,
        "content": obj.get("content"),
        "source": obj.get("source"),
        "confidence": _confidence_value(obj),
    }


def _provenance_note(obj: AIOPObject) -> Dict[str, Any]:
    return {
        "evidence": obj.id,
        "source": obj.get("source"),
        "source_type": obj.get("source_type"),
        "source_date": obj.get("source_date"),
        "independence_root": obj.get("independence_group") or obj.get("source") or obj.id,
    }


def _confidence_value(obj: AIOPObject) -> Optional[float]:
    try:
        value = float(obj.get("confidence"))
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def _fingerprint(
    claim: AIOPObject,
    evidence: Sequence[AIOPObject],
    policy: ValidationPolicy,
    kind: str,
    expected_roots: Sequence[str],
    evaluated_at: datetime,
) -> str:
    payload = {
        "claim": claim.to_jsonld(),
        "claim_type": kind,
        "expected_roots": list(expected_roots),
        "evidence": [obj.to_jsonld() for obj in evidence],
        "policy": {
            "minimum_independent_roots": policy.minimum_independent_roots,
            "maximum_age_days": policy.maximum_age_days,
            "causal_source_types": policy.causal_source_types,
        },
    }
    if policy.maximum_age_days is not None:
        payload["evaluated_on"] = evaluated_at.date().isoformat()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _dedupe(items: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(items))


__all__ = [
    "CLAIM_TYPES",
    "CONTRADICTED",
    "Evaluation",
    "SUPPORTED",
    "UNRESOLVED",
    "UNTESTABLE",
    "VERDICTS",
    "ValidationPolicy",
    "WEAKLY_SUPPORTED",
    "evaluate_claim",
]
