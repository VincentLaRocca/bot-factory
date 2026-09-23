"""The Validator and Judge must be more constrained than persuasive."""

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import aiop
from aiop import AIOPObject, State, validate_object
from capabilities.judgment import Judge
from capabilities.validation import (
    CONTRADICTED,
    SUPPORTED,
    UNRESOLVED,
    UNTESTABLE,
    ValidationPolicy,
    Validator,
    WEAKLY_SUPPORTED,
    evaluate_claim,
)
from observer import Authority, INTERNAL_AUTHORITY, Mission, Observer, Permission
from profiles import VALIDATION_CONTEXT_FILE, VALIDATION_PROFILE, VERSION_PREDICATE
from store import ObjectStore

from conftest import load_context, opaque_terms, used_terms

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
SUBJECT = "urn:aiop:company:example"

AUTHORITY = Authority.of(
    Permission.READ,
    Permission.VALIDATE,
    Permission.RECOMMEND,
    Permission.CREATE_OBJECT,
    Permission.RELATE_OBJECTS,
)


def claim(statement="Revenue rose 20% year over year", kind="factual"):
    return AIOPObject(
        id="urn:aiop:claim:revenue",
        types=["Claim"],
        state=State.ACTIVE,
        properties={
            "statement": statement,
            "dimension": "event_verification",
            "status": "SUPPORTED",
            "claim_type": kind,
        },
    )


def evidence(identifier, stance="supports", root=None, confidence=0.9, **properties):
    obj = AIOPObject(
        id=f"urn:aiop:evidence:{identifier}",
        types=["Evidence"],
        state=State.ACTIVE,
        properties={
            "title": identifier,
            "content": properties.pop("content", f"Evidence from {identifier}"),
            "source": properties.pop("source", f"urn:source:{identifier}"),
            "source_type": properties.pop("source_type", "filing"),
            "source_kind": properties.pop("source_kind", "primary"),
            "source_date": properties.pop("source_date", "2026-09-14"),
            "dimension": properties.pop("dimension", "event_verification"),
            "stance": stance,
            "confidence": confidence,
            **properties,
        },
    )
    if root is not None:
        obj.set("independence_group", root)
    return obj


def store_with(claim_obj, *items):
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    store.add(claim_obj)
    for item in items:
        item.relate(item.get("stance"), claim_obj.id)
        store.add(item)
    return store


def mission(*capabilities, authority=AUTHORITY):
    return Mission.build(
        objective="Challenge a claim and present a bounded verdict",
        required_capabilities=capabilities,
        authority=authority.granted,
    )


def bench(store, authority=AUTHORITY, with_judge=True):
    observer = Observer("validation bench", store=store, authority=authority)
    observer.install(Validator())
    if with_judge:
        observer.install(Judge())
        observer.assign(mission("validator", "judge", authority=authority))
    else:
        observer.assign(mission("validator", authority=authority))
    observer.register()
    return observer


def validate(bench_obj, claim_obj, **parameters):
    invocation = bench_obj.invoke("validator", inputs=[claim_obj], parameters=parameters)
    return invocation, bench_obj.store.get(invocation.findings["validations"][0])


def test_validator_and_judge_are_plugins_not_chassis_features():
    source = Path(aiop.__file__).parents[1] / "observer"
    forbidden = {"Validator", "Judge", "Validation", "Decision"}
    for path in source.glob("*.py"):
        tree = ast.parse(path.read_text())
        strings = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not (forbidden & names), path
        assert not any(word in value for word in forbidden for value in strings if "example" not in value.lower()), path


def test_capabilities_describe_the_split_before_running():
    store = store_with(claim(), evidence("one"))
    observer = bench(store)
    validator = observer.describe_capability("validator")
    judge = observer.describe_capability("judge")

    assert validator.accepts == ("Claim",)
    assert validator.produces == ("Validation",)
    assert Permission.VALIDATE in validator.requires
    assert judge.accepts == ("Validation",)
    assert judge.produces == ("Decision",)
    assert judge.dependencies == ("validator",)


def test_internal_authority_deliberately_cannot_validate():
    claim_obj = claim()
    observer = Observer(
        "validation bench",
        store=store_with(claim_obj, evidence("one")),
        authority=INTERNAL_AUTHORITY,
    )
    observer.install(Validator())
    observer.assign(
        mission("validator", authority=INTERNAL_AUTHORITY),
        strict=False,
    )

    refused = observer.invoke("validator", inputs=[claim_obj])

    assert refused.refused
    assert Permission.VALIDATE in refused.missing_authority


def test_two_independent_roots_support_a_factual_claim():
    claim_obj = claim()
    store = store_with(
        claim_obj,
        evidence("filing", root="issuer-filing", confidence=0.91),
        evidence("audit", root="outside-auditor", confidence=0.84),
    )

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == SUPPORTED
    assert result.get("public_verdict") == "PASS"
    assert result.get("confidence") == 0.84
    assert result.get("confidence_kind") == "estimate"


def test_repetition_from_one_root_is_weak_not_consensus():
    claim_obj = claim()
    store = store_with(
        claim_obj,
        evidence("article-a", root="wire-4471"),
        evidence("article-b", root="wire-4471"),
        evidence("article-c", root="wire-4471"),
    )

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == WEAKLY_SUPPORTED
    assert result.get("public_verdict") == "INCONCLUSIVE_COVERAGE"
    assert result.get("independence_roots") == ["wire-4471"]
    assert "independent corroboration" in result.get("missing_information")


def test_missing_run_from_a_frozen_universe_is_inconclusive_coverage():
    claim_obj = claim()
    store = store_with(
        claim_obj,
        evidence("filing", root="issuer"),
        evidence("audit", root="auditor"),
    )

    _, result = validate(
        bench(store),
        claim_obj,
        expected_roots={claim_obj.id: ["issuer", "auditor", "regulator"]},
    )

    assert result.get("verdict") == UNRESOLVED
    assert result.get("public_verdict") == "INCONCLUSIVE_COVERAGE"
    assert result.get("expected_independence_roots") == ["auditor", "issuer", "regulator"]
    assert any("regulator" in item for item in result.get("missing_information"))


def test_agreement_and_disagreement_remain_mixed():
    claim_obj = claim()
    store = store_with(
        claim_obj,
        evidence("filing", root="issuer"),
        evidence("audit", root="auditor"),
        evidence("correction", stance="contradicts", root="exchange", content="The print was cancelled."),
    )

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == UNRESOLVED
    assert result.get("public_verdict") == "MIXED"
    assert result.get("counter_evidence") == ["urn:aiop:evidence:correction"]
    assert result.get("strongest_counterargument") == "The print was cancelled."


def test_counter_evidence_without_support_contradicts():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("correction", stance="contradicts"))

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == CONTRADICTED
    assert result.get("public_verdict") == "INVALID"


def test_missing_evidence_stays_unresolved_and_requests_research():
    claim_obj = claim()

    _, result = validate(bench(store_with(claim_obj)), claim_obj)

    assert result.get("verdict") == UNRESOLVED
    assert result.get("public_verdict") == "INCONCLUSIVE_EVIDENCE"
    assert result.get("research_requests")


def test_malformed_confidence_becomes_unresolved_instead_of_crashing():
    claim_obj = claim()
    store = store_with(
        claim_obj,
        evidence("bad", root="a", confidence="certain"),
        evidence("good", root="b", confidence=0.9),
    )

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == UNRESOLVED
    assert "malformed evidence confidence" in result.get("failure_reasons")


def test_empty_claim_is_untestable_not_guessed():
    claim_obj = claim(statement="  ")

    _, result = validate(bench(store_with(claim_obj)), claim_obj)

    assert result.get("verdict") == UNTESTABLE
    assert result.get("normalized_claim") == ""


def test_causal_claim_requires_declared_causal_evidence():
    claim_obj = claim("The announcement caused the price move", "causal")
    store = store_with(
        claim_obj,
        evidence("news", root="news"),
        evidence("filing", root="issuer"),
    )

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == UNRESOLVED
    assert result.get("causal_warnings")


def test_causal_method_can_satisfy_the_extra_test():
    claim_obj = claim("Treatment caused recovery", "causal")
    store = store_with(
        claim_obj,
        evidence("trial", root="trial", source_type="randomized_trial"),
        evidence("replication", root="replication", source_type="controlled_study"),
    )

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == SUPPORTED


def test_quantitative_claim_must_declare_and_align_its_value():
    claim_obj = claim(kind="quantitative")
    store = store_with(claim_obj, evidence("filing", root="issuer", claimed_value=20))

    _, result = validate(bench(store), claim_obj)

    assert result.get("verdict") == UNTESTABLE
    assert any(check["name"] == "declared_value" and not check["passed"] for check in result.get("tests"))


def test_recency_is_a_declared_policy_not_an_implicit_guess():
    claim_obj = claim()
    store = store_with(
        claim_obj,
        evidence("old-a", root="a", source_date="2020-01-01"),
        evidence("old-b", root="b", source_date="2020-01-02"),
    )
    observer = Observer("freshness bench", store=store, authority=AUTHORITY)
    observer.install(Validator(ValidationPolicy(maximum_age_days=30)))
    observer.assign(mission("validator"))

    _, result = validate(observer, claim_obj)

    assert result.get("verdict") == UNRESOLVED
    assert "evidence within the declared recency window" in result.get("missing_information")


def test_validator_does_not_change_claim_or_subject():
    claim_obj = claim()
    subject = AIOPObject(id=SUBJECT, types=["Company"], state=State.ACTIVE, properties={"name": "Example"})
    claim_obj.relate("about", subject.id)
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    store.add(subject)
    before_claim = json.dumps(claim_obj.to_jsonld(), sort_keys=True)
    before_subject = json.dumps(subject.to_jsonld(), sort_keys=True)

    validate(bench(store), claim_obj)

    assert json.dumps(claim_obj.to_jsonld(), sort_keys=True) == before_claim
    assert json.dumps(subject.to_jsonld(), sort_keys=True) == before_subject


def test_validation_identity_is_recomputable_and_repeat_runs_are_inert():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    observer = bench(store)

    first, first_result = validate(observer, claim_obj)
    second, second_result = validate(observer, claim_obj)

    assert first_result.id == second_result.id
    assert len(first.created) == 1
    assert second.created == ()


def test_new_evidence_produces_a_new_validation_without_overwriting_history():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"))
    observer = bench(store)
    _, first = validate(observer, claim_obj)
    late = evidence("two", root="b")
    late.relate("supports", claim_obj.id)
    store.add(late)

    _, second = validate(observer, claim_obj)

    assert first.id != second.id
    assert store.contains(first.id)
    assert first.get("verdict") == WEAKLY_SUPPORTED
    assert second.get("verdict") == SUPPORTED


def test_judge_writes_adjacent_proposed_decision_and_mutates_nothing():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    observer = bench(store)
    _, validation = validate(observer, claim_obj)
    before_claim = json.dumps(claim_obj.to_jsonld(), sort_keys=True)
    before_validation = json.dumps(validation.to_jsonld(), sort_keys=True)

    judged = observer.invoke("judge", inputs=[validation])
    decision = store.get(judged.findings["decisions"][0])

    assert decision.state is State.PROPOSED
    assert decision.get("verdict") == SUPPORTED
    assert decision.get("human_review_required") is True
    assert decision.get("authorized_action") == "NONE"
    assert json.dumps(claim_obj.to_jsonld(), sort_keys=True) == before_claim
    assert json.dumps(validation.to_jsonld(), sort_keys=True) == before_validation


def test_judge_can_weaken_a_verdict():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    observer = bench(store)
    _, validation = validate(observer, claim_obj)

    judged = observer.invoke(
        "judge",
        inputs=[validation],
        parameters={"verdicts": {validation.id: UNRESOLVED}},
    )
    decision = store.get(judged.findings["decisions"][0])

    assert decision.get("source_verdict") == SUPPORTED
    assert decision.get("verdict") == UNRESOLVED


def test_judge_refuses_to_upgrade_uncertainty():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="same"))
    observer = bench(store)
    _, validation = validate(observer, claim_obj)

    judged = observer.invoke(
        "judge",
        inputs=[validation],
        parameters={"verdicts": {validation.id: SUPPORTED}},
    )
    decision = store.get(judged.findings["decisions"][0])

    assert validation.get("verdict") == WEAKLY_SUPPORTED
    assert decision.get("verdict") == WEAKLY_SUPPORTED
    assert "refused evidentiary upgrade" in decision.get("reasons")[0]


def test_judge_requires_a_validation_from_the_graph():
    claim_obj = claim()
    observer = bench(store_with(claim_obj))
    floating = AIOPObject(
        id="urn:aiop:validation:floating",
        types=["Validation"],
        state=State.ACTIVE,
        properties={"verdict": UNRESOLVED, "claim": claim_obj.id},
    )

    with pytest.raises(ValueError, match="not in the store"):
        observer.invoke("judge", inputs=[floating])


def test_validation_and_decision_validate_and_round_trip():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    observer = bench(store)
    _, validation = validate(observer, claim_obj)
    judged = observer.invoke("judge", inputs=[validation])
    decision = store.get(judged.findings["decisions"][0])

    for obj in (validation, decision):
        result = validate_object(obj, VALIDATION_PROFILE)
        assert result.is_valid, result.errors
        restored = AIOPObject.from_jsonld(json.loads(json.dumps(obj.to_jsonld())))
        assert restored.to_jsonld() == obj.to_jsonld()


def test_every_validation_term_is_declared_in_its_context():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    observer = bench(store)
    _, validation = validate(observer, claim_obj)
    decision_id = observer.invoke("judge", inputs=[validation]).findings["decisions"][0]
    contexts = [
        load_context(Path(aiop.__file__).with_name("context.jsonld")),
        load_context(Path(aiop.__file__).parents[1] / "profiles" / "context.jsonld"),
        load_context(Path(aiop.__file__).parents[1] / "profiles" / "observer-context.jsonld"),
        load_context(Path(aiop.__file__).parents[1] / "profiles" / "research-context.jsonld"),
        load_context(VALIDATION_CONTEXT_FILE),
    ]
    known = set().union(*contexts)
    opaque = set().union(*(opaque_terms(context) for context in contexts))

    for obj in (validation, store.get(decision_id)):
        assert used_terms(obj.to_jsonld(), opaque) <= known


def test_direct_evaluator_rejects_non_claims():
    obj = AIOPObject(id="urn:aiop:not-a-claim", types=["Observation"], state=State.ACTIVE)
    store = ObjectStore([obj])

    with pytest.raises(ValueError, match="not a Claim"):
        evaluate_claim(store, obj, "urn:validator:test")


def test_execution_records_show_read_write_and_narrow_authority():
    claim_obj = claim()
    store = store_with(claim_obj, evidence("one", root="a"), evidence("two", root="b"))
    observer = bench(store)
    validated, validation = validate(observer, claim_obj)
    judged = observer.invoke("judge", inputs=[validation])

    assert claim_obj.id in validated.record.get("inputs_read")
    assert validation.id in validated.record.get("objects_created")
    assert Permission.VALIDATE.value in validated.record.get("authority")
    assert judged.findings["authorized_action"] == "NONE"
    assert Permission.TRANSACT.value not in judged.record.get("authority")
