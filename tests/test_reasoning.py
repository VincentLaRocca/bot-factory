"""Calculations: declared inputs, results as objects, lineage, staleness.

The demonstration the layer exists for: assemble the cluster around an
opportunity, calculate its expected value from five properties of four
independently addressable objects, let new evidence move one of them, and watch
the system work out for itself which conclusions it has to take back.
"""

import tokenize
from pathlib import Path

import pytest

import reasoning
from aiop import AIOPObject, Provenance, State
from aiop.validation import validate_document, validate_object
from profiles import (
    DEMO_CALCULATION_SCHEMA,
    DEMO_FUNCTIONS,
    DEMO_PROFILE,
    DEPENDENTS_VIEW,
    LINEAGE_VIEW,
    VALUATION_VIEW,
)
from reasoning import (
    ArgumentMismatch,
    Binding,
    Calculation,
    FunctionRegistry,
    MalformedCalculation,
    ReasoningEngine,
    UnknownFunction,
    UnresolvedBinding,
    dependents_of,
    fingerprint,
    invalidated_by,
    is_stale,
    stale,
)

OPPORTUNITY = "urn:aiop:opportunity:harbour-q2-retrofit"
COMPANY = "urn:aiop:company:harbour-forge"
TECHNOLOGY = "urn:aiop:technology:induction-retrofit"
MARKET = "urn:aiop:market:uk-industrial-heat"
SARAH = "urn:aiop:person:sarah"
FIELD_TRIAL = "urn:aiop:evidence:field-trial"
TEARDOWN = "urn:aiop:evidence:competitor-teardown"
CALCULATION = "urn:aiop:calculation:harbour-q2-asymmetry"
LEGACY_CALCULATION = "urn:aiop:calculation:harbour-q2-expected-value"
STORY = "urn:aiop:story:the-long-field"
AUDIT = "urn:aiop:evidence:delivery-audit"

#: 1_800_000 * (0.62 * 0.71 * 0.55) - 320_000 * (1 - 0.62 * 0.71 * 0.55)
EXPECTED_VALUE = 193273.2

#: The same, once execution probability moves from 0.62 to 0.74.
REVISED_EXPECTED_VALUE = 292616.4


def new_evidence(store, execution_probability: float) -> AIOPObject:
    """Evidence arrives, and the company's execution probability moves."""
    evidence = AIOPObject(
        types="Evidence",
        id=AUDIT,
        state=State.ACTIVE,
        properties={"title": "Delivery audit of the last four retrofits"},
    )
    evidence.attest(Provenance(agent="urn:aiop:agent:analyst", method="observed"))
    evidence.relate("supports", COMPANY, fidelity="audited")
    store.add(evidence)

    company = store.get(COMPANY)
    company.set("execution_probability", execution_probability)
    company.attest(
        Provenance(
            agent="urn:aiop:agent:analyst",
            method="revised",
            source=AUDIT,
            confidence=0.9,
        )
    )
    return evidence


# -- the cluster the question needs -----------------------------------


def test_the_valuation_cluster_assembles_around_the_opportunity(reasoning_store):
    cluster = reasoning_store.cluster(OPPORTUNITY, VALUATION_VIEW)

    assert set(cluster.ids) == {
        OPPORTUNITY,
        COMPANY,
        SARAH,
        TECHNOLOGY,
        MARKET,
        FIELD_TRIAL,
        TEARDOWN,
        CALCULATION,
        LEGACY_CALCULATION,
    }
    assert STORY not in cluster


def test_the_reasoning_world_is_valid_under_the_profile(reasoning_documents):
    for name, document in reasoning_documents.items():
        result = validate_document(document, DEMO_PROFILE)
        assert result.is_valid, f"{name}: {[i.message for i in result.errors]}"


# -- what a calculation declares --------------------------------------


def test_a_calculation_declares_five_properties_of_four_objects(engine):
    calculation = engine.calculation(CALCULATION)

    assert calculation.function_name == "expected_value"
    assert [b.variable for b in calculation.bindings] == [
        "upside",
        "downside",
        "execution_probability",
        "success_probability",
        "adoption_probability",
    ]
    assert calculation.sources == sorted({COMPANY, MARKET, OPPORTUNITY, TECHNOLOGY})


def test_every_binding_resolves_to_its_own_source_property(engine):
    resolved = engine.calculation(CALCULATION).resolve(engine.store)

    assert {item.variable: item.value for item in resolved} == {
        "upside": 1800000,
        "downside": 320000,
        "execution_probability": 0.62,
        "success_probability": 0.71,
        "adoption_probability": 0.55,
    }
    execution = next(i for i in resolved if i.variable == "execution_probability")
    assert execution.binding.source == COMPANY
    assert execution.binding.source_property == "execution_probability"


def test_a_binding_reads_the_store_rather_than_a_copy(engine):
    binding = Binding("execution_probability", COMPANY, "execution_probability")

    assert binding.resolve(engine.store).value == 0.62
    engine.store.get(COMPANY).set("execution_probability", 0.74)
    assert binding.resolve(engine.store).value == 0.74


def test_an_unresolvable_binding_fails_loudly(engine):
    with pytest.raises(UnresolvedBinding):
        Binding("x", "urn:aiop:company:missing", "execution_probability").resolve(
            engine.store
        )
    with pytest.raises(UnresolvedBinding):
        Binding("x", COMPANY, "nonexistent_property").resolve(engine.store)


def test_a_calculation_without_a_function_or_inputs_is_refused(engine):
    empty = Calculation(AIOPObject(types="Calculation"), DEMO_CALCULATION_SCHEMA)

    with pytest.raises(MalformedCalculation):
        empty.function_name
    with pytest.raises(MalformedCalculation):
        empty.bindings


# -- functions are named, never executed as text ----------------------


def test_functions_are_resolved_by_name_from_a_registry():
    assert DEMO_FUNCTIONS.names() == ["expected_value", "payoff_ratio"]
    assert DEMO_FUNCTIONS.get("expected_value").variables == (
        "upside",
        "downside",
        "execution_probability",
        "success_probability",
        "adoption_probability",
    )
    with pytest.raises(UnknownFunction):
        DEMO_FUNCTIONS.get("os.system")


def test_a_function_refuses_variables_it_did_not_ask_for():
    with pytest.raises(ArgumentMismatch):
        DEMO_FUNCTIONS.apply("payoff_ratio", {"upside": 10.0})
    with pytest.raises(ArgumentMismatch):
        DEMO_FUNCTIONS.apply("payoff_ratio", {"upside": 10.0, "downside": 2.0, "x": 1})
    assert DEMO_FUNCTIONS.apply("payoff_ratio", {"upside": 10.0, "downside": 2.0}) == 5.0


def test_an_engine_can_only_run_what_its_registry_holds(reasoning_store):
    barren = ReasoningEngine(reasoning_store, FunctionRegistry(), DEMO_CALCULATION_SCHEMA)

    with pytest.raises(UnknownFunction):
        barren.evaluate(CALCULATION)


# -- the result is an ordinary Information Object ---------------------


def test_the_result_is_the_expected_value(engine):
    result = engine.evaluate(CALCULATION)

    assert result.get("value") == pytest.approx(EXPECTED_VALUE)
    assert result.get("function") == "expected_value"
    assert result.get("calculation") == CALCULATION


def test_the_result_is_stored_addressable_and_valid(engine):
    result = engine.evaluate(CALCULATION)

    assert engine.store.get(result.id) is result
    assert result.has_type("Result")
    assert result.state is State.ACTIVE
    assert validate_object(result, DEMO_PROFILE).is_valid
    assert AIOPObject.from_jsonld(result.to_jsonld()).to_jsonld() == result.to_jsonld()


def test_the_result_carries_its_own_provenance(engine):
    result = engine.evaluate(CALCULATION)

    record = result.latest_provenance
    assert record.method == "calculated"
    assert record.source == CALCULATION
    assert record.agent == engine.agent


# -- lineage ------------------------------------------------------------


def test_the_result_records_an_edge_to_every_object_it_read(engine):
    result = engine.evaluate(CALCULATION)

    lineage = {
        (relation.object, relation.attributes.get("variable"))
        for relation in result
        if relation.predicate == "derivedFrom"
    }
    assert lineage == {
        (CALCULATION, None),
        (OPPORTUNITY, "upside"),
        (OPPORTUNITY, "downside"),
        (COMPANY, "execution_probability"),
        (TECHNOLOGY, "success_probability"),
        (MARKET, "adoption_probability"),
    }
    properties = {
        relation.attributes.get("sourceProperty")
        for relation in result
        if relation.attributes
    }
    assert properties == {
        "upside",
        "downside",
        "execution_probability",
        "success_probability",
        "adoption_probability",
    }


def test_the_result_keeps_the_values_it_was_computed_from(engine):
    result = engine.evaluate(CALCULATION)

    snapshot = {i["variable"]: i["value"] for i in result.get("inputs")}
    assert snapshot["execution_probability"] == 0.62
    assert {i["source"] for i in result.get("inputs")} == {
        OPPORTUNITY,
        COMPANY,
        TECHNOLOGY,
        MARKET,
    }


def test_lineage_is_walkable_as_an_ordinary_cluster(engine):
    result = engine.evaluate(CALCULATION)

    cluster = engine.store.cluster(result.id, LINEAGE_VIEW)

    assert set(cluster.ids) == {
        result.id,
        CALCULATION,
        OPPORTUNITY,
        COMPANY,
        TECHNOLOGY,
        MARKET,
    }


# -- fingerprints -------------------------------------------------------


def test_the_fingerprint_is_deterministic_and_input_sensitive(engine):
    calculation = engine.calculation(CALCULATION)
    before = calculation.fingerprint(engine.store)

    assert before == calculation.fingerprint(engine.store)
    assert before == fingerprint("expected_value", calculation.resolve(engine.store))

    engine.store.get(COMPANY).set("execution_probability", 0.74)
    assert calculation.fingerprint(engine.store) != before


def test_re_evaluating_an_unchanged_calculation_changes_nothing(engine):
    first = engine.evaluate(CALCULATION)
    stored = len(engine.store)

    assert engine.evaluate(CALCULATION) is first
    assert len(engine.store) == stored


# -- staleness ----------------------------------------------------------


def test_new_evidence_makes_the_standing_result_stale(engine):
    result = engine.evaluate(CALCULATION)
    assert not engine.is_stale(result)

    new_evidence(engine.store, 0.74)

    assert engine.is_stale(result)
    assert engine.check(result).reason == "an input value has changed"
    assert [r.id for r in engine.stale()] == [result.id]


def test_the_dependents_of_a_changed_object_are_an_index_lookup(engine):
    result = engine.evaluate(CALCULATION)
    new_evidence(engine.store, 0.74)

    assert [obj.id for obj in engine.dependents_of(COMPANY)] == [result.id]
    assert [obj.id for obj in engine.invalidated_by(COMPANY)] == [result.id]
    assert engine.dependents_of(FIELD_TRIAL) == []

    reachable = engine.store.cluster(COMPANY, DEPENDENTS_VIEW)
    assert result.id in reachable


def test_a_vanished_input_is_staleness_too(engine):
    result = engine.evaluate(CALCULATION)
    engine.store.delete(MARKET)

    assert engine.is_stale(result)
    assert "no longer resolves" in engine.check(result).reason


def test_staleness_helpers_work_without_an_engine(engine):
    result = engine.evaluate(CALCULATION)
    new_evidence(engine.store, 0.74)

    assert is_stale(engine.store, result, DEMO_CALCULATION_SCHEMA)
    assert stale(engine.store, DEMO_CALCULATION_SCHEMA) == [result]
    assert dependents_of(engine.store, COMPANY, DEMO_CALCULATION_SCHEMA) == [result]
    assert invalidated_by(engine.store, COMPANY, DEMO_CALCULATION_SCHEMA) == [result]


# -- recomputation ------------------------------------------------------


def test_recomputation_produces_the_revised_expected_value(engine):
    engine.evaluate(CALCULATION)
    new_evidence(engine.store, 0.74)

    recomputed = engine.recompute_stale()

    assert [r.get("value") for r in recomputed] == [
        pytest.approx(REVISED_EXPECTED_VALUE)
    ]
    assert engine.stale() == []


def test_recomputation_supersedes_rather_than_overwrites(engine):
    original = engine.evaluate(CALCULATION)
    new_evidence(engine.store, 0.74)

    replacement = engine.recompute(original)

    assert replacement.id != original.id
    assert original.state is State.SUPERSEDED
    assert original.get("value") == pytest.approx(EXPECTED_VALUE)
    assert engine.store.get(original.id) is original
    assert replacement.related("supersedes") == [original.id]
    assert engine.current_result(CALCULATION) is replacement


def test_the_history_of_a_conclusion_survives_being_wrong(engine):
    original = engine.evaluate(CALCULATION)
    new_evidence(engine.store, 0.74)
    replacement = engine.recompute(original)

    assert engine.store.history_of(replacement.id) == [replacement, original]
    assert engine.store.latest_of(original.id) is replacement
    assert engine.results_of(CALCULATION) == [replacement, original]
    assert [
        i["value"]
        for i in original.get("inputs")
        if i["variable"] == "execution_probability"
    ] == [0.62]


def test_recomputation_leaves_untouched_results_alone(engine):
    result = engine.evaluate(CALCULATION)

    assert engine.recompute_stale() == []
    assert engine.current_result(CALCULATION) is result
    assert result.state is State.ACTIVE


# -- the reasoning layer knows no domain and runs no text -------------

DOMAIN_TERMS = (
    "Person",
    "Company",
    "Opportunity",
    "Technology",
    "Market",
    "Evidence",
    "upside",
    "downside",
    "probability",
    "expected_value",
    "derivedFrom",
    "supersedes",
)


def reasoning_code() -> dict:
    """Every reasoning module's source with its prose stripped out."""
    sources = {}
    for path in sorted(Path(reasoning.__file__).parent.glob("*.py")):
        with tokenize.open(path) as handle:
            sources[path.name] = "".join(
                token.string
                for token in tokenize.generate_tokens(handle.readline)
                if token.type not in (tokenize.STRING, tokenize.COMMENT)
            )
    return sources


def test_the_reasoning_layer_names_no_domain_vocabulary():
    """Every term it touches arrives through a schema, not a literal."""
    for name, source in reasoning_code().items():
        for term in DOMAIN_TERMS:
            assert term not in source, f"reasoning/{name} mentions '{term}'"


def test_the_reasoning_layer_executes_no_stored_text():
    for name, source in reasoning_code().items():
        for danger in ("eval(", "exec(", "compile(", "import ast", "__import__"):
            assert danger not in source, f"reasoning/{name} uses {danger}"
