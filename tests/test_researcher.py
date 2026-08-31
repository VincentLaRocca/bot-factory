"""What the Researcher is required to do, and required never to do.

The order follows the architecture: the chassis first (which must still know
nothing), then the capability's self-description, then authority, then the
provider boundary, then what investigation writes into the graph. The load
bearing tests are the ones about ignorance — contradiction survives, unknown
survives, and no source's word becomes a property of anything.
"""

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import aiop
from aiop import AIOPObject, State, validate_object
from capabilities.anomaly import AnomalyListener
from capabilities.research import (
    CARD,
    ChainedResearchProvider,
    Finding,
    Investigation,
    MockResearchProvider,
    Researcher,
    ResearchProvider,
    ResearchRequest,
    ResearchResponse,
    SilentResearchProvider,
    claim_id,
    evidence_id,
    findings as findings_module,
    questions_for,
)
from observer import (
    Authority,
    Mission,
    Observer,
    Permission,
    Reading,
    SensorCard,
    StaticSensor,
    to_observations,
)
from profiles import ASYMMETRY_PROFILE, OBSERVER_CONTEXT_FILE, VERSION_PREDICATE
from profiles.research import (
    EPISTEMIC_STATES,
    RESEARCH_CONTEXT_FILE,
    RESEARCH_PROFILE,
    TOPICS,
)
from store import ObjectStore

from conftest import load_context, opaque_terms, used_terms

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "research"
COMPANY = "urn:aiop:company:abc"
START = datetime(2026, 1, 6, 21, 0, tzinfo=timezone.utc)
QUIET = [4.05, 4.18, 4.11, 4.22, 4.16, 4.20]
TAPE = SensorCard(
    sensor="exchange-tape",
    name="Exchange consolidated tape",
    independence_group="abc-exchange",
)

#: Researching reaches outside the graph, so it is granted by name.
DESK_AUTHORITY = Authority.of(
    Permission.READ,
    Permission.OBSERVE,
    Permission.RESEARCH,
    Permission.CREATE_OBJECT,
    Permission.RELATE_OBJECTS,
)


# -- helpers ---------------------------------------------------------------
def prepared():
    return json.loads((EXAMPLES / "sources.json").read_text())


def observations(values, first=0, target=COMPANY):
    sensor = StaticSensor(
        card=TAPE,
        readings=[
            Reading(
                target=target,
                value=value,
                target_property="share_price",
                observed_at=START + timedelta(days=7 * (first + week)),
            )
            for week, value in enumerate(values)
        ],
    )
    return to_observations(sensor, observer="urn:aiop:observer:market-desk")


def mission_for(*capabilities, authority=None):
    return Mission.build(
        objective="Find out what caused the unusual print",
        required_capabilities=capabilities,
        authority=authority
        if authority is not None
        else [
            Permission.READ,
            Permission.OBSERVE,
            Permission.RESEARCH,
            Permission.CREATE_OBJECT,
            Permission.RELATE_OBJECTS,
        ],
    )


@pytest.fixture
def research_store():
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    for path in sorted(EXAMPLES.glob("*.jsonld")):
        store.put(AIOPObject.from_jsonld(json.loads(path.read_text())))
    return store


@pytest.fixture
def sources():
    """The prepared answers: an exchange, two filings and a newswire."""
    data = prepared()
    return MockResearchProvider(
        findings={data["target"]: [Finding(**item) for item in data["findings"]]},
        unreachable={data["target"]: data["unreachable"]},
        name="exchange+filings+wire",
    )


@pytest.fixture
def desk(research_store, sources):
    observer = Observer("market desk", store=research_store, authority=DESK_AUTHORITY)
    observer.install(AnomalyListener())
    observer.install(Researcher(sources))
    observer.assign(mission_for("anomaly_listener", "researcher"))
    observer.register()
    return observer


@pytest.fixture
def anomaly(desk):
    """The print nobody expected, produced by the other capability entirely."""
    for observation in observations(QUIET):
        desk.store.add(observation)
    noticed = desk.invoke("anomaly_listener", inputs=observations([42.0], len(QUIET)))
    return desk.store.get(noticed.findings["anomalies"][0])


@pytest.fixture
def investigated(desk, anomaly):
    return desk.invoke("researcher", inputs=[anomaly])


# -- the chassis still knows nothing ---------------------------------------
def test_the_observer_knows_nothing_about_research():
    """The acceptance criterion: ``observer/core.py`` never heard of this.

    Prose may mention research as an example; the code may not know the
    capability exists. Docstrings are stripped before looking.
    """
    source = Path(aiop.__file__).parents[1] / "observer"
    for path in sorted(source.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant):
                        node.body[0].value.value = ""
        code = ast.unparse(tree)
        for forbidden in ("Research", "Evidence", "Claim", "capabilities."):
            assert forbidden not in code, f"{path.name} mentions {forbidden}"

    assert not [name for name in dir(Observer) if "research" in name.lower()]


def test_the_chassis_was_not_edited_to_take_the_second_capability():
    """``observer/`` is what it was at the Observer v0.1 baseline."""
    import subprocess

    root = Path(aiop.__file__).parents[1]
    changed = subprocess.run(
        ["git", "diff", "--name-only", "bf6e75838c3c2addc1d73ff7de7e5e0c2f7dd818", "--", "observer"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if changed.returncode != 0:  # a shallow clone or no git at all
        pytest.skip("git history unavailable")
    assert changed.stdout.strip() == ""


def test_a_researcher_is_installed_not_inherited(research_store, sources):
    observer = Observer("market desk", store=research_store, authority=DESK_AUTHORITY)
    assert observer.capabilities() == []

    observer.install(Researcher(sources))

    assert observer.capabilities() == ["researcher"]
    assert type(observer) is Observer


# -- self-description ------------------------------------------------------
def test_the_capability_describes_itself_before_it_runs(desk):
    card = desk.describe_capability("researcher")

    assert card.capability == "researcher"
    assert card.accepts == ("Anomaly",)
    assert card.produces == ("Evidence", "Claim")
    assert Permission.RESEARCH in card.requires
    assert card.description


def test_the_card_is_published_as_an_object(desk):
    published = desk.store.get(CARD.id)

    assert "Capability" in published.types
    assert published.get("capability") == "researcher"
    assert desk.id in published.related("installedOn")


def test_a_researcher_accepts_an_anomaly(desk, anomaly):
    assert desk.invoke("researcher", inputs=[anomaly]).complete


def test_a_researcher_refuses_what_it_cannot_read(desk):
    observation = observations([4.5], 99)[0]

    refused = desk.invoke("researcher", inputs=[observation])

    assert refused.refused
    assert "accepts Anomaly" in refused.refusal


def test_a_capability_that_is_not_installed_is_a_refusal_not_a_crash(desk, anomaly):
    desk.uninstall("researcher")

    refused = desk.invoke("researcher", inputs=[anomaly])

    assert refused.missing_capabilities == ("researcher",)
    assert refused.record.get("status") == "REFUSED"


# -- authority -------------------------------------------------------------
def test_research_without_the_authority_to_research_is_refused(research_store, sources, anomaly):
    reader = Observer(
        "compliance reader",
        store=research_store,
        authority=Authority.of(Permission.READ, Permission.OBSERVE),
    )
    reader.install(Researcher(sources))

    refused = reader.invoke("researcher", inputs=[anomaly])

    assert refused.refused
    assert Permission.RESEARCH in refused.missing_authority
    assert sources.asked == []


def test_a_mission_can_narrow_research_away(research_store, sources, anomaly):
    observer = Observer("market desk", store=research_store, authority=DESK_AUTHORITY)
    observer.install(Researcher(sources))
    observer.assign(
        mission_for("researcher", authority=[Permission.READ, Permission.OBSERVE]),
        strict=False,
    )

    refused = observer.invoke("researcher", inputs=[anomaly])

    assert refused.refused
    assert Permission.RESEARCH in refused.missing_authority


def test_a_mission_cannot_manufacture_research_authority(research_store, sources, anomaly):
    observer = Observer(
        "watcher", store=research_store, authority=Authority.of(Permission.READ)
    )
    observer.install(Researcher(sources))
    observer.assign(mission_for("researcher"), strict=False)

    assert Permission.RESEARCH not in observer.grant().granted


# -- the provider boundary -------------------------------------------------
def test_the_providers_satisfy_the_protocol(sources):
    assert isinstance(sources, ResearchProvider)
    assert isinstance(SilentResearchProvider(), ResearchProvider)
    assert isinstance(ChainedResearchProvider(sources), ResearchProvider)


def test_the_request_carries_facts_and_not_the_verdict(desk, anomaly, sources):
    desk.invoke("researcher", inputs=[anomaly])
    request = sources.asked[0]

    assert request.anomaly == anomaly.id
    assert request.target == COMPANY
    assert request.target_property == "share_price"
    assert request.observed_state == 42.0
    assert [question.topic for question in request.questions] == list(TOPICS)
    serialised = json.dumps(request.to_dict())
    assert "disposition" not in serialised and "score" not in serialised


def test_the_questions_are_deterministic():
    first = questions_for(COMPANY, "share_price", 42.0, 4.15)
    second = questions_for(COMPANY, "share_price", 42.0, 4.15)

    assert first == second
    assert len(first) == len(TOPICS)


def test_the_same_provider_twice_gives_the_same_answer(sources):
    request = ResearchRequest(
        anomaly="urn:aiop:anomaly:x",
        target=COMPANY,
        questions=questions_for(COMPANY, "share_price", 42.0, 4.15),
    )

    first = sources.research(request)
    second = sources.research(request)

    assert first == second


def test_a_provider_may_answer_nothing():
    response = SilentResearchProvider().research(
        ResearchRequest(anomaly="urn:aiop:anomaly:x", target=COMPANY, questions=())
    )

    assert response.findings == ()


def test_chained_providers_pool_their_findings_rather_than_resolving_them(sources):
    data = prepared()
    dissenting = MockResearchProvider(
        findings={
            COMPANY: [
                Finding(
                    topic="cause",
                    source="urn:aiop:source:second-wire",
                    source_type="news",
                    content="Analysts insist the move reflects a genuine re-rating.",
                    proposition=data["findings"][1]["proposition"],
                    stance="contradicts",
                )
            ]
        },
        name="second-wire",
    )
    chained = ChainedResearchProvider(sources, dissenting)

    response = chained.research(
        ResearchRequest(
            anomaly="urn:aiop:anomaly:x",
            target=COMPANY,
            questions=questions_for(COMPANY, "share_price", 42.0, 4.15),
        )
    )

    stances = [f.stance for f in response.findings if f.topic == "cause"]
    assert stances.count("contradicts") == 2
    assert "supports" in stances


def test_no_provider_here_reaches_the_network():
    source = Path(aiop.__file__).parents[1] / "capabilities" / "research"
    text = " ".join(path.read_text() for path in sorted(source.glob("*.py")))

    for forbidden in ("import requests", "urllib", "openai", "anthropic", "http://api"):
        assert forbidden not in text


# -- evidence --------------------------------------------------------------
def test_every_finding_becomes_evidence_naming_its_source(investigated, desk):
    ids = investigated.findings["evidence"]
    assert len(ids) == len(prepared()["findings"])

    for identifier in ids:
        evidence = desk.store.get(identifier)
        assert "Evidence" in evidence.types
        assert evidence.get("source")
        assert evidence.get("source_type")
        assert evidence.get("content")
        assert validate_object(evidence, RESEARCH_PROFILE).is_valid


def test_evidence_records_who_asked_and_when(investigated, desk):
    evidence = desk.store.get(investigated.findings["evidence"][0])
    provenance = evidence.provenance[-1]

    assert provenance.agent == CARD.id
    assert provenance.source == evidence.get("source")
    assert evidence.get("retrieved_at")


def test_evidence_is_tied_back_to_the_anomaly_that_prompted_it(investigated, desk, anomaly):
    for identifier in investigated.findings["evidence"]:
        evidence = desk.store.get(identifier)
        assert anomaly.id in evidence.related("investigatedFrom")
        assert COMPANY in evidence.related("about")


def test_independence_metadata_survives_into_the_graph(investigated, desk):
    groups = {
        desk.store.get(identifier).get("independence_group")
        for identifier in investigated.findings["evidence"]
    }

    assert {"abc-exchange", "abc-issuer", "wire-syndicate"} <= groups


def test_the_researcher_does_not_score_independence(investigated, desk):
    claim = desk.store.get(investigated.findings["contested"][0])

    assert sorted(claim.get("independence_groups")) == ["abc-exchange", "abc-issuer"]
    assert "consensus" not in claim.properties
    assert "independence_score" not in claim.properties


# -- claims ----------------------------------------------------------------
def test_claims_are_proposed_with_the_evidence_pointing_at_them(investigated, desk):
    claims = investigated.findings["claims"]
    assert claims

    for identifier in claims:
        claim = desk.store.get(identifier)
        assert "Claim" in claim.types
        assert claim.get("statement")
        assert COMPANY in claim.related("about")
        bearing = {
            relation.predicate
            for relation in desk.store.inbound(identifier)
            if relation.predicate in ("supports", "contradicts", "qualifies")
        }
        assert bearing


def test_a_claim_the_evidence_agrees_on_is_supported(investigated, desk):
    supported = [
        desk.store.get(identifier)
        for identifier in investigated.findings["claims"]
        if desk.store.get(identifier).get("status") == "SUPPORTED"
    ]

    assert supported
    for claim in supported:
        assert claim.get("supporting")
        assert not claim.get("contradicting")


def test_contradiction_survives_rather_than_being_resolved(investigated, desk):
    contested = investigated.findings["contested"]
    assert len(contested) == 1

    claim = desk.store.get(contested[0])
    assert claim.get("status") == "CONTESTED"
    assert len(claim.get("supporting")) == 2
    assert len(claim.get("contradicting")) == 1
    dissent = desk.store.get(claim.get("contradicting")[0])
    assert dissent.state is State.ACTIVE
    assert "breakthrough" in dissent.get("content")


def test_qualifying_evidence_is_neither_support_nor_contradiction(investigated, desk):
    qualifying = [
        claim
        for claim in (desk.store.get(i) for i in investigated.findings["claims"])
        if claim.get("qualifying")
    ]

    assert qualifying
    for claim in qualifying:
        assert set(claim.get("qualifying")).isdisjoint(claim.get("supporting"))


def test_a_researcher_claim_is_a_claim_the_analyst_can_read(investigated, desk):
    """Reuse, not a second claim system: the analyst's profile validates these."""
    for identifier in investigated.findings["claims"]:
        claim = desk.store.get(identifier)
        assert validate_object(claim, ASYMMETRY_PROFILE).is_valid


def test_nothing_the_researcher_finds_becomes_a_property_of_the_target(investigated, desk):
    company = desk.store.get(COMPANY)

    assert sorted(company.properties) == ["name"]
    assert not company.related("supersedes")
    statuses = {
        desk.store.get(i).get("status") for i in investigated.findings["claims"]
    }
    assert "ACCEPTED" not in statuses


# -- what could not be established -----------------------------------------
def test_a_topic_with_no_findings_stays_unknown(research_store, anomaly, sources):
    desk = Observer("quiet desk", store=research_store, authority=DESK_AUTHORITY)
    desk.install(Researcher(SilentResearchProvider()))

    result = desk.invoke("researcher", inputs=[anomaly])
    topics = result.findings["investigations"][0]["topics"]

    assert set(topics.values()) == {"UNKNOWN"}
    assert result.findings["claims"] == []
    assert result.created == ()


def test_a_topic_nobody_could_be_asked_is_unreachable_not_unknown(investigated):
    topics = investigated.findings["investigations"][0]["topics"]

    assert topics["alternative"] == "UNREACHABLE"
    assert set(topics.values()) <= set(EPISTEMIC_STATES)


def test_a_contested_topic_is_not_reported_as_known(investigated):
    topics = investigated.findings["investigations"][0]["topics"]

    assert topics["cause"] == "UNSUPPORTED"
    assert topics["event_verification"] == "KNOWN"
    assert investigated.findings["unresolved"] == ["alternative"]


# -- repetition and lineage ------------------------------------------------
def test_running_the_same_investigation_twice_creates_nothing_new(desk, anomaly):
    first = desk.invoke("researcher", inputs=[anomaly])
    before = len(desk.store)

    second = desk.invoke("researcher", inputs=[anomaly])

    assert second.created == ()
    assert len(desk.store) == before + 1  # the second execution record
    assert second.findings["evidence"] == first.findings["evidence"]
    assert second.findings["claims"] == first.findings["claims"]


def test_evidence_and_claim_identity_is_a_digest_of_what_they_say():
    finding = Finding(
        topic="cause",
        source="urn:aiop:source:one",
        source_type="filing",
        content="something happened",
        proposition="something happened for a reason",
    )

    assert evidence_id("urn:aiop:anomaly:x", finding) == evidence_id(
        "urn:aiop:anomaly:x", finding
    )
    assert claim_id(COMPANY, "p") != claim_id(COMPANY, "q")


def test_later_contradiction_unsettles_a_claim_that_looked_supported(desk, anomaly, research_store):
    first = desk.invoke("researcher", inputs=[anomaly])
    verified = [
        i
        for i in first.findings["claims"]
        if research_store.get(i).get("status") == "SUPPORTED"
    ][0]
    statement = research_store.get(verified).get("statement")

    doubter = Observer("night desk", store=research_store, authority=DESK_AUTHORITY)
    doubter.install(
        Researcher(
            MockResearchProvider(
                findings={
                    COMPANY: [
                        Finding(
                            topic="event_verification",
                            source="urn:aiop:source:clearing-house",
                            source_type="clearing_data",
                            content="The 42.00 print was cancelled as erroneous.",
                            proposition=statement,
                            stance="contradicts",
                        )
                    ]
                },
                name="clearing-house",
            )
        )
    )
    doubter.invoke("researcher", inputs=[anomaly])

    assert research_store.get(verified).get("status") == "CONTESTED"


def test_the_execution_record_says_what_was_read_and_written(investigated, desk, anomaly):
    record = investigated.record

    assert record.get("invoked") == "researcher"
    assert record.get("capability_version") == CARD.version
    assert anomaly.id in record.get("inputs_read")
    assert set(record.get("objects_created")) == set(
        investigated.findings["evidence"] + investigated.findings["claims"]
    )
    assert Permission.RESEARCH.value in record.get("authority")
    for identifier in record.get("objects_created"):
        assert identifier in record.related("produced")


def test_the_whole_chain_is_walkable_from_the_target(investigated, desk, anomaly):
    """Observation -> Anomaly -> Evidence -> Claim, in the store, after the fact."""
    claim = desk.store.get(investigated.findings["contested"][0])
    evidence = desk.store.get(claim.get("supporting")[0])
    investigated_from = evidence.related("investigatedFrom")

    assert anomaly.id in investigated_from
    assert anomaly.related("derivedFrom")
    observation = desk.store.get(anomaly.related("derivedFrom")[0])
    assert observation.get("target") == COMPANY
    assert claim.id in [relation.object for relation in desk.store.outbound(evidence.id)]


# -- serialisation ---------------------------------------------------------
def test_evidence_and_claims_round_trip(investigated, desk):
    for identifier in investigated.findings["evidence"] + investigated.findings["claims"]:
        stored = desk.store.get(identifier)
        restored = AIOPObject.from_jsonld(json.loads(json.dumps(stored.to_jsonld())))

        assert restored.id == stored.id
        assert restored.types == stored.types
        assert restored.properties == stored.properties
        assert list(restored) == list(stored)


def test_everything_research_writes_is_in_the_context(investigated, desk):
    contexts = [
        load_context(RESEARCH_CONTEXT_FILE),
        load_context(OBSERVER_CONTEXT_FILE),
        load_context(Path(aiop.__file__).with_name("context.jsonld")),
        load_context(Path(aiop.__file__).parents[1] / "profiles" / "context.jsonld"),
    ]
    known = set().union(*contexts)
    opaque = set().union(*(opaque_terms(context) for context in contexts))

    written = investigated.findings["evidence"] + investigated.findings["claims"]
    for identifier in [*written, investigated.record.id]:
        document = desk.store.get(identifier).to_jsonld()
        assert used_terms(document, opaque) <= known, identifier

    for path in sorted(EXAMPLES.glob("*.jsonld")):
        document = json.loads(path.read_text())
        assert used_terms(document, opaque) <= known, document["@id"]


def test_the_epistemic_words_are_the_ones_the_analyst_already_uses():
    from agents.asymmetry.completeness import Status

    assert set(EPISTEMIC_STATES) == {status.value for status in Status}


def test_an_investigation_reports_itself_as_plain_data(investigated):
    report = investigated.findings["investigations"][0]

    assert json.loads(json.dumps(report)) == report
    assert set(report["topics"]) == set(TOPICS)


def test_a_response_can_be_built_without_a_store():
    """The provider boundary is data, not graph access."""
    response = ResearchResponse(provider="test", findings=())

    assert response.for_topic("cause") == []
    assert isinstance(Investigation, type)
    assert findings_module.judge([], []) == "UNSUPPORTED"
