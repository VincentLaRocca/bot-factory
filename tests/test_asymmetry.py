"""The Asymmetry Analyst: what it knows, what it refuses to guess.

Every test here runs against a deliberately incomplete world with no network
and no model behind it. The analyst is deterministic by construction, so the
same store must always produce the same gaps, the same ranking and the same
recommendation.
"""

from pathlib import Path

import pytest

from agents.asymmetry import (
    ACCEPTED,
    ANALYSIS_VIEW,
    CONTESTED,
    DEFAULT_POLICY,
    AnalysisPolicy,
    AsymmetryAnalyst,
    MockResearchProvider,
    NoResearchProvider,
    StoreResearchProvider,
    Status,
    assess,
    claim_id,
    claims,
    cluster_fingerprint,
    evidence,
    gap_id,
    is_stale,
    our_edge,
    synergy,
)
from agents.asymmetry.assessment import check, fingerprint
from agents.asymmetry.gaps import dependants_of_property, discover, queue, rank
import aiop
from aiop import AIOPObject, State
from profiles import (
    ASYMMETRY_CALCULATION_SCHEMA,
    ASYMMETRY_CONTEXT_FILE,
    ASYMMETRY_FUNCTIONS,
    ASYMMETRY_PROFILE,
    VERSION_PREDICATE,
)
from store import ObjectStore
from reasoning import UnresolvedBinding

from conftest import (
    ASYMMETRY_DIR,
    asymmetry_documents,
    load_context,
    opaque_terms,
    used_terms,
)


def _vocabulary():
    """Every term the three composed contexts define, and the opaque ones."""
    contexts = [
        load_context(ASYMMETRY_CONTEXT_FILE),
        load_context(Path(aiop.__file__).with_name("context.jsonld")),
        load_context(ASYMMETRY_DIR.parents[1] / "profiles" / "context.jsonld"),
    ]
    known = set().union(*contexts)
    opaque = set().union(*(opaque_terms(context) for context in contexts))
    return known, opaque


COMPANY = "urn:aiop:company:vantage-clinical"
TECHNOLOGY = "urn:aiop:technology:triage-copilot"
EXECUTION_VALUE = "people.execution_probability"
EXPECTED_VALUE = "urn:aiop:calculation:clinical-triage-expected-value"


# -- the world it starts from ---------------------------------------------
def test_the_opportunity_starts_incomplete(analyst, opportunity_id):
    completeness = analyst.inspect(analyst.assemble(opportunity_id), opportunity_id)

    assert 0.0 < completeness.score < 1.0
    assert completeness.gaps()
    assert completeness.by_name(EXECUTION_VALUE).status is Status.UNKNOWN
    assert completeness.by_name("access.access_path").known


def test_a_missing_object_is_unreachable_not_unknown(analyst, opportunity_id):
    """No Market object at all is a different failure from an empty field."""
    completeness = analyst.inspect(analyst.assemble(opportunity_id), opportunity_id)
    assert completeness.by_name("market.adoption_probability").status is Status.UNKNOWN

    marketless = ObjectStore(version_predicate=VERSION_PREDICATE)
    marketless.load(
        [
            document
            for document in asymmetry_documents("*.jsonld")
            if "Market" not in document["@type"]
        ]
    )
    blind = AsymmetryAnalyst(marketless)
    reduced = assess(
        marketless,
        blind.assemble(opportunity_id),
        opportunity_id,
        blind.specification,
    )

    assert reduced.by_name("market.adoption_probability").status is Status.UNREACHABLE


def test_an_asserted_value_is_not_a_known_one(analyst, opportunity_id):
    """The opportunity claims an upside; nothing yet stands behind it."""
    completeness = analyst.inspect(analyst.assemble(opportunity_id), opportunity_id)
    upside = completeness.by_name("asymmetry.upside")

    assert upside.status is Status.UNSUPPORTED
    assert upside.value == 4200000
    assert not upside.support


def test_the_cluster_is_bounded(analyst, asymmetry_store, opportunity_id):
    cluster = analyst.assemble(opportunity_id)

    assert len(cluster) < len(asymmetry_store)
    assert all(cluster.depth_of(obj.id) <= ANALYSIS_VIEW.depth for obj in cluster)
    assert not cluster.of_type("Assessment")


# -- gaps -------------------------------------------------------------------
def test_gaps_become_ordinary_objects(analyst, asymmetry_store, opportunity_id):
    run = analyst.run(opportunity_id)
    gap = asymmetry_store.get(gap_id(opportunity_id, "market.competitors"))

    assert gap.types == ["InformationGap"]
    assert gap.get("dimension") == "market.competitors"
    assert gap.get("status") == "UNKNOWN"
    assert gap.get("importance") in ("HIGH", "MEDIUM", "LOW")
    assert gap.get("reason")
    assert opportunity_id in gap.related("about")
    assert gap.get("target") == "urn:aiop:market:uk-primary-care"
    assert gap in run.gaps


def test_gap_ranking_is_the_published_formula(analyst, asymmetry_store, opportunity_id):
    completeness = analyst.inspect(analyst.assemble(opportunity_id), opportunity_id)
    finding = completeness.by_name(EXECUTION_VALUE)
    ranking = rank(finding, asymmetry_store, ASYMMETRY_CALCULATION_SCHEMA)

    expected = round(
        ranking.decision_impact
        * ranking.uncertainty
        * ranking.dependency_weight
        * ranking.resolvability,
        4,
    )
    assert ranking.priority == expected
    assert ranking.dependants


def test_a_gap_a_calculation_depends_on_outranks_one_nothing_reads(
    analyst, asymmetry_store, opportunity_id
):
    completeness = analyst.inspect(analyst.assemble(opportunity_id), opportunity_id)
    consumed = rank(
        completeness.by_name(EXECUTION_VALUE), asymmetry_store, ASYMMETRY_CALCULATION_SCHEMA
    )
    ignored = rank(
        completeness.by_name("market.competitors"),
        asymmetry_store,
        ASYMMETRY_CALCULATION_SCHEMA,
    )

    assert consumed.dependency_weight > ignored.dependency_weight
    assert consumed.priority > ignored.priority


def test_dependants_are_found_through_the_calculation_bindings(asymmetry_store):
    dependants = dependants_of_property(
        asymmetry_store, COMPANY, "execution_probability", ASYMMETRY_CALCULATION_SCHEMA
    )

    assert EXPECTED_VALUE in dependants


def test_ranking_is_stable_across_stores(analyst, opportunity_id, available_evidence):
    """The same graph, analysed twice from scratch, ranks identically."""
    def ranked(store):
        agent = AsymmetryAnalyst(store, research=MockResearchProvider(available_evidence))
        return [
            (gap.id, gap.get("research_priority"))
            for gap in agent.run(opportunity_id).gaps
        ]

    first = ranked(analyst.store)

    fresh = ObjectStore(version_predicate=VERSION_PREDICATE)
    fresh.load(asymmetry_documents("*.jsonld"))

    assert ranked(fresh) == first


def test_the_queue_respects_the_policy_budget(analyst, asymmetry_store, opportunity_id):
    completeness = analyst.inspect(analyst.assemble(opportunity_id), opportunity_id)
    gaps = discover(
        asymmetry_store,
        opportunity_id,
        completeness,
        DEFAULT_POLICY,
        ASYMMETRY_CALCULATION_SCHEMA,
        analyst.agent,
        analyst.context,
    )

    shortlist = queue(gaps, DEFAULT_POLICY.maximum_research)
    priorities = [gap.get("research_priority") for gap in shortlist]

    assert len(shortlist) == DEFAULT_POLICY.maximum_research
    assert priorities == sorted(priorities, reverse=True)


# -- research and claims ----------------------------------------------------
def test_without_research_nothing_is_invented(blind_analyst, opportunity_id):
    run = blind_analyst.run(opportunity_id)

    assert not run.resolved
    assert run.completeness.by_name(EXECUTION_VALUE).status is Status.UNKNOWN
    assert blind_analyst.store.get(COMPANY).get("execution_probability") is None
    assert run.action == "RESEARCH"


def test_evidence_supports_a_claim_which_is_about_the_object(
    analyst, asymmetry_store, opportunity_id
):
    analyst.run(opportunity_id)
    claim = asymmetry_store.get(claim_id(COMPANY, EXECUTION_VALUE))

    assert claim.types == ["Claim"]
    assert claim.get("status") == ACCEPTED
    assert claim.related("about") == [COMPANY]
    supporting = asymmetry_store.inbound(claim.id, "supports")
    assert len(supporting) >= DEFAULT_POLICY.minimum_evidence
    assert all(
        asymmetry_store.get(relation.subject).types == ["Evidence"]
        for relation in supporting
    )


def test_an_accepted_claim_writes_the_value_with_provenance(
    analyst, asymmetry_store, opportunity_id
):
    analyst.run(opportunity_id)
    company = asymmetry_store.get(COMPANY)

    assert company.get("execution_probability") == 0.62
    assert company.latest_provenance.source == claim_id(COMPANY, EXECUTION_VALUE)


def test_contradicted_evidence_leaves_the_claim_contested_and_unapplied(
    asymmetry_store, available_evidence, analyst
):
    """Two independent sources disagree about defensibility; neither wins."""
    findings = available_evidence["technology.defensibility"]
    assert len({item.get("claimed_value") for item in findings}) > 1

    gap = AIOPObject(
        id="urn:aiop:opportunity:clinical-triage#gap-technology-defensibility",
        types=["InformationGap"],
        properties={"dimension": "technology.defensibility", "status": "UNKNOWN"},
    )
    outcome = claims.assemble(
        store=asymmetry_store,
        gap=asymmetry_store.add(gap),
        findings=findings,
        target=TECHNOLOGY,
        dimension="technology.defensibility",
        prop="defensibility",
        policy=DEFAULT_POLICY,
        agent=analyst.agent,
        context=analyst.context,
    )

    assert outcome.status == CONTESTED
    assert not outcome.applied
    assert asymmetry_store.get(TECHNOLOGY).get("defensibility") is None
    assert asymmetry_store.inbound(outcome.claim.id, "contradicts")


def test_an_unsupported_claim_is_not_promoted_to_a_fact(
    asymmetry_store, analyst, opportunity_id
):
    """One weak, non-independent source is a claim, not knowledge."""
    thin = evidence(
        identifier="urn:aiop:evidence:blog-post",
        title="A blog post asserting a number",
        dimension="market.addressable_market",
        claimed_value=99,
        confidence=0.2,
        independent=False,
        source_kind="secondary",
        context=analyst.context,
    )
    policy = AnalysisPolicy(minimum_confidence=0.7)
    gap = asymmetry_store.add(
        AIOPObject(
            id=f"{opportunity_id}#gap-market-addressable_market",
            types=["InformationGap"],
            properties={"dimension": "market.addressable_market", "status": "UNKNOWN"},
        )
    )
    outcome = claims.assemble(
        store=asymmetry_store,
        gap=gap,
        findings=[thin],
        target="urn:aiop:market:uk-primary-care",
        dimension="market.addressable_market",
        prop="addressable_market",
        policy=policy,
        agent=analyst.agent,
        context=analyst.context,
    )

    assert outcome.status != ACCEPTED
    assert not outcome.applied
    assert asymmetry_store.get("urn:aiop:market:uk-primary-care").get(
        "addressable_market"
    ) is None
    assert outcome.claim.related("qualifies") == ["urn:aiop:market:uk-primary-care"]


def test_the_analyst_does_not_care_which_provider_answers(
    asymmetry_store, available_evidence, opportunity_id
):
    """No model, no vendor, no network: a dict of findings is a valid provider."""
    analyst = AsymmetryAnalyst(
        asymmetry_store, research=MockResearchProvider(available_evidence)
    )
    run = analyst.run(opportunity_id)

    assert run.record.get("research_provider") == "mock"
    assert run.resolved


def test_the_store_itself_is_a_research_provider(asymmetry_store, opportunity_id):
    analyst = AsymmetryAnalyst(
        asymmetry_store, research=StoreResearchProvider(asymmetry_store)
    )
    run = analyst.run(opportunity_id)
    resolved = {outcome.gap.get("dimension") for outcome in run.resolved}

    assert "technology.success_probability" in resolved


# -- calculation ------------------------------------------------------------
def test_a_calculation_with_a_missing_input_produces_nothing(
    blind_analyst, opportunity_id
):
    run = blind_analyst.run(opportunity_id)

    assert not run.results
    assert [calculation for calculation, _ in run.unavailable]
    assert all("execution_probability" in reason or reason for _, reason in run.unavailable)


def test_the_analyst_reuses_the_reasoning_engine(blind_analyst, opportunity_id):
    with pytest.raises(UnresolvedBinding):
        blind_analyst.engine.evaluate(EXPECTED_VALUE)


def test_calculations_run_once_their_inputs_exist(analyst, opportunity_id):
    run = analyst.run(opportunity_id)

    assert "expected_value" in run.results
    assert "asymmetry_score" in run.results
    assert not run.unavailable


def test_a_result_carries_its_lineage(analyst, asymmetry_store, opportunity_id):
    run = analyst.run(opportunity_id)
    result = run.results["expected_value"]

    assert COMPANY in result.related("derivedFrom")
    assert EXPECTED_VALUE in result.related("derivedFrom")
    assert result.get("calculation") == EXPECTED_VALUE
    inputs = {binding["variable"]: binding["source"] for binding in result.get("inputs")}
    assert inputs["execution_probability"] == COMPANY
    assert asymmetry_store.get(result.id).state is State.ACTIVE


# -- judgement --------------------------------------------------------------
def test_the_synergy_case_is_assessed_explicitly(analyst, opportunity_id):
    run = analyst.run(opportunity_id)

    assert run.synergy.status in ("ESTABLISHED", "PARTIAL", "UNKNOWN")
    assert run.synergy.rationale
    assert run.assessment.related("derivedFrom")
    companion = analyst.store.get(run.assessment.related("synergyAssessment")[0])
    assert run.assessment.related("ourEdge")
    assert companion.types == ["SynergyAssessment"]
    assert companion.get("status") == run.synergy.status


def test_an_unestablished_edge_is_said_to_be_unestablished(
    asymmetry_store, research, opportunity_id
):
    analyst = AsymmetryAnalyst(
        asymmetry_store,
        research=research,
        policy=AnalysisPolicy(capabilities=()),
    )
    run = analyst.run(opportunity_id)

    assert run.edge.status in ("UNKNOWN", "NO_IDENTIFIED_EDGE")
    assert "edge" in run.edge.rationale.lower() or run.edge.rationale


def test_the_assessment_says_what_it_does_not_know(analyst, opportunity_id):
    run = analyst.run(opportunity_id)

    assert run.assessment.get("primary_unknowns")
    assert run.assessment.get("bull_case")
    assert run.assessment.get("base_case")
    assert run.assessment.get("bear_case")
    assert 0.0 <= run.assessment.get("confidence") <= 1.0
    assert sum(run.assessment.get("probabilities").values()) == pytest.approx(1.0)


def test_the_assessment_is_derived_from_what_it_used(
    analyst, asymmetry_store, opportunity_id
):
    run = analyst.run(opportunity_id)
    lineage = run.assessment.related("derivedFrom")

    assert run.results["expected_value"].id in lineage
    assert any(
        asymmetry_store.get(source).types == ["Claim"]
        for source in lineage
        if asymmetry_store.contains(source)
    )
    assert run.assessment.related("about") == [opportunity_id]


def test_an_action_is_recommended_with_a_reason(analyst, opportunity_id):
    from agents.asymmetry import ACTIONS

    run = analyst.run(opportunity_id)

    assert run.action in ACTIONS
    assert run.assessment.get("priority") in ("HIGH", "MEDIUM", "LOW")
    assert run.assessment.get("next_action")
    assert run.assessment.get("reason_for_next_action")


def test_too_little_knowledge_means_research_not_a_verdict(
    asymmetry_store, opportunity_id
):
    analyst = AsymmetryAnalyst(asymmetry_store, policy=AnalysisPolicy(minimum_completeness=0.99))
    run = analyst.run(opportunity_id)

    assert run.action == "RESEARCH"


# -- the execution record ---------------------------------------------------
def test_every_run_leaves_an_execution_record(analyst, asymmetry_store, opportunity_id):
    run = analyst.run(opportunity_id)
    record = asymmetry_store.get(run.record.id)

    assert record.types == ["ExecutionRecord"]
    assert record.get("agent") == analyst.agent
    assert record.get("agent_version")
    assert record.get("profile_version") == analyst.specification.version
    assert record.get("started_at") <= record.get("completed_at")
    assert record.get("status") == "COMPLETE"
    assert record.related("about") == [opportunity_id]
    assert record.get("objects_read")
    assert run.assessment.id in record.get("objects_created")
    assert record.get("gaps_discovered")
    assert record.get("policy")["name"] == analyst.policy.name


def test_the_record_fingerprints_what_the_run_could_see(analyst, opportunity_id):
    run = analyst.run(opportunity_id)
    cluster = analyst.assemble(opportunity_id)

    digest = run.record.get("cluster_fingerprint")
    assert len(digest) == 64
    assert digest != cluster_fingerprint(cluster)  # the run itself added objects
    assert set(run.record.get("objects_read")) == set(run.read)


def test_no_hidden_reasoning_is_stored(analyst, opportunity_id):
    run = analyst.run(opportunity_id)

    assert "chain_of_thought" not in run.record.properties
    assert "prompt" not in run.record.properties


# -- new evidence -----------------------------------------------------------
def _land(store, analyst, late_evidence, gap_dimension="people.execution_probability"):
    gap = store.get(gap_id("urn:aiop:opportunity:clinical-triage", gap_dimension))
    return claims.assemble(
        store=store,
        gap=gap,
        findings=late_evidence,
        target=COMPANY,
        dimension=gap_dimension,
        prop="execution_probability",
        policy=analyst.policy,
        agent="urn:aiop:agent:diligence",
        context=analyst.context,
    )


def test_new_evidence_supersedes_the_claim_it_replaces(
    analyst, asymmetry_store, opportunity_id, late_evidence
):
    analyst.run(opportunity_id)
    original = asymmetry_store.get(claim_id(COMPANY, EXECUTION_VALUE))

    outcome = _land(asymmetry_store, analyst, late_evidence)

    assert outcome.claim.id != original.id
    assert outcome.superseded == original.id
    assert asymmetry_store.get(original.id).state is State.SUPERSEDED
    assert outcome.claim.related("supersedes") == [original.id]
    assert asymmetry_store.get(COMPANY).get("execution_probability") == 0.78


def test_changed_evidence_makes_the_calculations_stale(
    analyst, asymmetry_store, opportunity_id, late_evidence
):
    run = analyst.run(opportunity_id)
    _land(asymmetry_store, analyst, late_evidence)

    stale = {result.id for result in analyst.engine.stale()}

    assert run.results["expected_value"].id in stale
    assert run.results["asymmetry_score"].id in stale


def test_recomputation_keeps_the_old_result(
    analyst, asymmetry_store, opportunity_id, late_evidence
):
    first = analyst.run(opportunity_id)
    before = first.results["expected_value"]
    _land(asymmetry_store, analyst, late_evidence)

    second = analyst.reanalyse(opportunity_id)
    after = second.results["expected_value"]

    assert after.id != before.id
    assert after.get("value") > before.get("value")
    assert asymmetry_store.get(before.id).state is State.SUPERSEDED
    assert asymmetry_store.get(before.id).get("value") == before.get("value")
    assert after.related("supersedes") == [before.id]


def test_changed_inputs_make_the_assessment_stale(
    analyst, asymmetry_store, opportunity_id, late_evidence
):
    run = analyst.run(opportunity_id)

    assert not is_stale(asymmetry_store, run.assessment)

    _land(asymmetry_store, analyst, late_evidence)
    analyst.engine.recompute_stale()

    stale, reason = check(asymmetry_store, run.assessment)
    assert stale
    assert reason


def test_a_stale_assessment_is_replaced_not_edited(
    analyst, asymmetry_store, opportunity_id, late_evidence
):
    first = analyst.run(opportunity_id)
    _land(asymmetry_store, analyst, late_evidence)

    second = analyst.reanalyse(opportunity_id)

    assert second.assessment.id != first.assessment.id
    assert first.assessment.id in second.superseded
    assert asymmetry_store.get(first.assessment.id).state is State.SUPERSEDED
    assert second.assessment.related("supersedes") == [first.assessment.id]
    assert asymmetry_store.get(first.assessment.id).get(
        "base_case"
    ) == first.assessment.get("base_case")


def test_an_unchanged_world_is_not_reassessed(blind_analyst, opportunity_id):
    """Nothing new learned, nothing new concluded: the same assessment stands."""
    first = blind_analyst.run(opportunity_id)
    second = blind_analyst.run(opportunity_id)

    assert second.assessment.id == first.assessment.id
    assert not second.superseded
    assert blind_analyst.store.get(first.assessment.id).state is State.ACTIVE


def test_research_that_learns_something_does_produce_a_new_assessment(
    analyst, opportunity_id
):
    """The converse: a run that closes more gaps must not reuse the old verdict."""
    first = analyst.run(opportunity_id)
    second = analyst.run(opportunity_id)

    assert second.completeness.score > first.completeness.score
    assert second.assessment.id != first.assessment.id
    assert first.assessment.id in second.superseded


def test_the_fingerprint_only_moves_when_the_inputs_do(analyst, asymmetry_store, opportunity_id):
    run = analyst.run(opportunity_id)
    sources = run.assessment.get("sources")
    before = fingerprint(asymmetry_store, sources, run.completeness.score)

    assert before == run.assessment.get("inputFingerprint")
    assert before == fingerprint(asymmetry_store, sources, run.completeness.score)
    assert before != fingerprint(asymmetry_store, sources, run.completeness.score + 0.1)


# -- the profile ------------------------------------------------------------
def test_the_profile_declares_what_the_analyst_writes():
    assert {"Claim", "InformationGap", "Assessment", "ExecutionRecord"} <= set(
        ASYMMETRY_PROFILE.known_types
    )
    assert ASYMMETRY_FUNCTIONS.get("asymmetry_score")
    assert ASYMMETRY_FUNCTIONS.get("expected_value")


def test_everything_the_analyst_writes_is_in_the_context(analyst, opportunity_id):
    known, opaque = _vocabulary()

    run = analyst.run(opportunity_id)
    for identifier in run.created + (run.record.id,):
        document = analyst.store.get(identifier).to_jsonld()
        assert used_terms(document, opaque) <= known, identifier


def test_the_example_world_is_expressed_in_the_vocabulary():
    known, opaque = _vocabulary()

    documents = (
        asymmetry_documents("*.jsonld")
        + asymmetry_documents("research/*.jsonld")
        + asymmetry_documents("late/*.jsonld")
    )
    assert documents
    for document in documents:
        assert used_terms(document, opaque) <= known, document["@id"]


def test_a_provider_that_answers_nothing_is_valid(asymmetry_store, opportunity_id):
    analyst = AsymmetryAnalyst(asymmetry_store, research=NoResearchProvider())
    run = analyst.run(opportunity_id)

    assert run.record.get("research_provider") == "none"
    assert run.record.get("status") == "COMPLETE"


def test_the_verdict_helpers_read_a_dossier_without_writing(analyst, opportunity_id):
    run = analyst.run(opportunity_id)
    before = len(analyst.store)

    dossier = run.judgement
    assert dossier is not None
    from agents.asymmetry.assessment import Dossier

    plain = Dossier(
        opportunity=analyst.store.get(opportunity_id),
        completeness=run.completeness,
        policy=analyst.policy,
    )
    assert synergy(plain).status
    assert our_edge(plain, analyst.policy).status
    assert len(analyst.store) == before
