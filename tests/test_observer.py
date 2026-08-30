"""What the Observer motherboard and its first plug-in are required to do.

The tests are organised as the architecture is: the chassis on its own, then
slots, then purpose, then authority, then the anomaly listener, then what all
of it leaves behind in the store. The most important ones are the negatives —
an observer that cannot do the job says so, and one that is not allowed to do
the job is refused even though it could.
"""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import aiop
from aiop import AIOPObject, State
from capabilities.anomaly import (
    AnomalyListener,
    AnomalyPolicy,
    Comparison,
    DEFAULT_DETECTORS,
    DetectorRegistry,
    Signal,
    anomaly as anomaly_module,
    detectors as detector_module,
)
from observer import (
    Authority,
    CapabilityCard,
    CapabilityContext,
    CapabilityNotInstalled,
    CapabilityOutcome,
    DuplicateCapability,
    INTERNAL_AUTHORITY,
    IncompatibleCapability,
    Mission,
    MissionNotExecutable,
    Observer,
    Permission,
    Reading,
    SelfObservation,
    SensorCard,
    StaticSensor,
    Unauthorised,
    UnmetDependency,
    observation as observation_module,
    to_observations,
)
from aiop import validate_object
from profiles import OBSERVER_CONTEXT_FILE, OBSERVER_PROFILE
from store import ObjectStore

from conftest import load_context, observer_documents, opaque_terms, used_terms

START = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
STEADY = [0.61, 0.62, 0.60, 0.63, 0.62, 0.61, 0.62, 0.60]
NOISY = [0.31, 0.88, 0.45, 0.79, 0.36, 0.91, 0.42, 0.79]
LAB = SensorCard(
    sensor="lab-report-feed",
    name="Laboratory report feed",
    independence_group="lattice-works-lab",
)
WIRE = SensorCard(
    sensor="wire-service",
    name="Wire service",
    independence_group="reuters-story-4471",
)


# -- helpers ---------------------------------------------------------------
def reading(target, value, week=0, target_property="cycle_efficiency"):
    return Reading(
        target=target,
        value=value,
        target_property=target_property,
        observed_at=START + timedelta(days=7 * week),
    )


def observations(target, values, target_property="cycle_efficiency", card=LAB, first=0):
    sensor = StaticSensor(
        card=card,
        readings=[
            reading(target, value, first + week, target_property)
            for week, value in enumerate(values)
        ],
    )
    return to_observations(sensor, observer="urn:aiop:observer:watchtower")


def remember(store, target, values, target_property="cycle_efficiency", card=LAB):
    return [
        store.add(obs)
        for obs in observations(target, values, target_property, card)
    ]


def mission_for(*capabilities, authority=None):
    return Mission.build(
        objective="Notice when the cell stops behaving as it always has",
        required_capabilities=capabilities,
        authority=authority
        if authority is not None
        else [
            Permission.READ,
            Permission.OBSERVE,
            Permission.CREATE_OBJECT,
            Permission.RELATE_OBJECTS,
        ],
    )


@pytest.fixture
def watchtower(observer_store):
    observer = Observer("watchtower", store=observer_store, authority=INTERNAL_AUTHORITY)
    observer.register()
    return observer


@pytest.fixture
def listening(watchtower):
    watchtower.install(AnomalyListener())
    watchtower.assign(mission_for("anomaly_listener"))
    return watchtower


class Trivial:
    """A capability that exists only to be plugged in and counted."""

    def __init__(self, name="trivial", requires=(), dependencies=(), compatible=("0.1",)):
        self.card = CapabilityCard.build(
            capability=name,
            version="0.1",
            description="does nothing, carefully",
            accepts=("Observation",),
            produces=(),
            requires=requires,
            dependencies=dependencies,
            compatible_with=compatible,
        )
        self.runs = 0

    def run(self, context: CapabilityContext) -> CapabilityOutcome:
        self.runs += 1
        return CapabilityOutcome(findings={"inputs": len(context.inputs)})


# -- the chassis on its own -------------------------------------------------
def test_an_observer_exists_before_it_can_do_anything(observer_store):
    observer = Observer("watchtower", store=observer_store)

    assert observer.id == "urn:aiop:observer:watchtower"
    assert observer.version
    assert observer.status == "ACTIVE"
    assert observer.capabilities() == []
    assert observer.authority.granted == frozenset()


def test_the_observer_knows_nothing_about_anomalies():
    """The negative test the whole architecture exists to pass.

    Prose may mention the listener as an example; the code may not know it
    exists. Docstrings are stripped before looking.
    """
    source = Path(aiop.__file__).parents[1] / "observer"
    for path in sorted(source.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant):
                        node.body[0].value.value = ""
        assert "anomal" not in ast.unparse(tree).lower(), path.name
        assert "capabilities." not in ast.unparse(tree), path.name

    assert not [name for name in dir(Observer) if "anomaly" in name.lower()]


def test_the_observer_publishes_itself_as_an_object(watchtower):
    stored = watchtower.store.get(watchtower.id)

    assert "Observer" in stored.types
    assert stored.get("name") == "watchtower"
    assert stored.get("version") == watchtower.version
    assert stored.get("status") == "ACTIVE"


# -- slots ------------------------------------------------------------------
def test_a_capability_is_installed_not_inherited(watchtower):
    card = watchtower.install(AnomalyListener())

    assert card.capability == "anomaly_listener"
    assert watchtower.can("anomaly_listener")
    assert type(watchtower) is Observer


def test_installing_twice_is_an_error(watchtower):
    watchtower.install(AnomalyListener())

    with pytest.raises(DuplicateCapability):
        watchtower.install(AnomalyListener())


def test_a_capability_describes_itself(watchtower):
    watchtower.install(AnomalyListener())
    card = watchtower.describe_capability("anomaly_listener")

    assert card.accepts == ("Observation",)
    assert card.produces == ("Anomaly",)
    assert Permission.CREATE_OBJECT in card.requires
    assert card.description


def test_capabilities_are_discoverable_by_what_they_take_and_make(listening):
    assert listening.registry.accepting("Observation")
    assert [card.capability for card in listening.registry.producing("Anomaly")] == [
        "anomaly_listener"
    ]
    assert listening.registry.producing("Opportunity") == []


def test_the_installed_capability_is_stored_as_an_object(listening):
    card = listening.store.get("urn:aiop:capability:anomaly_listener")

    assert "Capability" in card.types
    assert card.get("requires") == ["CREATE_OBJECT", "OBSERVE", "READ", "RELATE_OBJECTS"]
    assert card.get("produces") == ["Anomaly"]


def test_an_incompatible_capability_is_refused(watchtower):
    with pytest.raises(IncompatibleCapability):
        watchtower.install(Trivial(compatible=("0.9",)))


def test_a_capability_depending_on_a_missing_one_is_refused(watchtower):
    with pytest.raises(UnmetDependency):
        watchtower.install(Trivial(dependencies=("scientific_research",)))

    watchtower.install(Trivial(name="scientific_research"))
    assert watchtower.install(Trivial(dependencies=("scientific_research",)))


def test_uninstalling_leaves_the_chassis_intact(listening):
    listening.uninstall("anomaly_listener")

    assert not listening.can("anomaly_listener")
    with pytest.raises(CapabilityNotInstalled):
        listening.describe_capability("anomaly_listener")


# -- purpose ----------------------------------------------------------------
def test_a_mission_is_an_object(listening):
    mission = listening.mission
    stored = listening.store.get(mission.identifier)

    assert "Mission" in stored.types
    assert stored.get("objective") == mission.objective
    assert stored.get("required_capabilities") == ["anomaly_listener"]
    assert "CREATE_OBJECT" in stored.get("authority")
    assert Mission.from_object(stored).authority == mission.authority


def test_a_mission_needing_an_absent_capability_is_refused(watchtower):
    watchtower.install(AnomalyListener())

    with pytest.raises(MissionNotExecutable) as refused:
        watchtower.assign(mission_for("anomaly_listener", "scientific_research"))

    readiness = refused.value.readiness
    assert readiness.status == "MISSION_NOT_EXECUTABLE"
    assert readiness.missing_capabilities == ("scientific_research",)
    assert "missing_capabilities: scientific_research" in str(refused.value)
    assert watchtower.mission is None


def test_missing_functionality_is_not_faked(watchtower):
    watchtower.install(AnomalyListener())
    readiness = watchtower.readiness(mission_for("scientific_research"))

    assert not readiness.executable
    assert readiness.to_dict()["missing_capabilities"] == ["scientific_research"]


def test_a_mission_that_withholds_authority_is_not_executable(watchtower):
    watchtower.install(AnomalyListener())
    readiness = watchtower.readiness(
        mission_for("anomaly_listener", authority=[Permission.READ])
    )

    assert not readiness.executable
    assert Permission.CREATE_OBJECT in readiness.missing_authority


# -- authority --------------------------------------------------------------
def test_capability_does_not_imply_authority(observer_store, technology_id):
    watcher = Observer(
        "read-only watcher",
        store=observer_store,
        authority=Authority.of(Permission.READ, Permission.OBSERVE),
    )
    watcher.install(AnomalyListener())
    watcher.assign(mission_for("anomaly_listener"), strict=False)
    remember(observer_store, technology_id, STEADY)

    result = watcher.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )

    assert result.refused
    assert Permission.CREATE_OBJECT in result.missing_authority
    assert not observer_store.objects(types=["Anomaly"])
    with pytest.raises(Unauthorised):
        result.raise_for_status()


def test_a_mission_cannot_grant_what_the_observer_never_had(observer_store):
    watcher = Observer(
        "watcher", store=observer_store, authority=Authority.of(Permission.READ)
    )
    generous = mission_for("anomaly_listener", authority=[Permission.TRANSACT])

    assert watcher.grant(generous).granted == frozenset()
    assert not watcher.grant(generous).allows(Permission.TRANSACT)


def test_the_effective_grant_is_the_intersection(listening):
    assert listening.grant().allows(Permission.CREATE_OBJECT)
    assert not listening.grant().allows(Permission.RECOMMEND)
    assert listening.authority.allows(Permission.RECOMMEND)


def test_an_uninstalled_capability_cannot_be_invoked(watchtower, technology_id):
    result = watchtower.invoke(
        "scientific_research", inputs=observations(technology_id, [0.83])
    )

    assert result.refused
    assert result.missing_capabilities == ("scientific_research",)
    with pytest.raises(MissionNotExecutable):
        result.raise_for_status()


def test_a_capability_only_takes_what_it_declared(listening, technology_id):
    result = listening.invoke(
        "anomaly_listener", inputs=[listening.store.get(technology_id)]
    )

    assert result.refused
    assert "accepts Observation" in result.refusal


# -- observations -----------------------------------------------------------
def test_an_observation_keeps_both_of_its_endpoints(technology_id):
    observation = observations(technology_id, [0.62])[0]

    assert observation.get("target") == technology_id
    assert observation.get("observer") == "urn:aiop:observer:watchtower"
    assert {r.predicate for r in observation.relations} == {
        "about",
        "observedBy",
        "sensedBy",
    }


def test_an_observation_cannot_observe_itself():
    with pytest.raises(SelfObservation):
        observation_module.observe(
            target="urn:aiop:observer:watchtower",
            value=1,
            observer="urn:aiop:observer:watchtower",
        )


def test_observation_provenance_names_the_sensor(technology_id):
    observation = observations(technology_id, [0.62])[0]
    record = observation.provenance[0]

    assert record.agent == "urn:aiop:observer:watchtower"
    assert record.source == "urn:aiop:sensor:lab-report-feed"
    assert record.method == "measurement"


def test_independence_is_recorded_not_computed(technology_id):
    lab = observations(technology_id, [0.62], card=LAB)[0]
    first, second = observations(technology_id, [0.62, 0.62], card=WIRE)

    assert lab.get("independence_group") == "lattice-works-lab"
    assert first.get("independence_group") == second.get("independence_group")
    assert first.get("independence_group") != lab.get("independence_group")


def test_history_is_the_stores_memory(observer_store, technology_id):
    remember(observer_store, technology_id, STEADY)
    remember(observer_store, technology_id, ["charge-cycling"], "demonstrated_capability")

    history = observation_module.history(
        observer_store, technology_id, "cycle_efficiency"
    )

    assert [obs.get("value") for obs in history] == STEADY
    assert len(observation_module.history(observer_store, technology_id)) == len(STEADY) + 1


def test_history_ignores_retired_observations(observer_store, technology_id):
    stored = remember(observer_store, technology_id, STEADY)
    stored[0].transition(State.RETIRED)

    history = observation_module.history(observer_store, technology_id, "cycle_efficiency")
    assert len(history) == len(STEADY) - 1


# -- detection --------------------------------------------------------------
def test_a_numerical_deviation_is_detected(listening, technology_id):
    remember(listening.store, technology_id, STEADY)

    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )
    detection = result.findings["detections"][0]

    assert result.complete
    assert detection["disposition"] == "ESCALATE"
    assert "deviation_from_expected" in detection["dimensions"]
    assert detection["score"] > 0.85


def test_an_ordinary_week_is_not_an_anomaly(listening, technology_id):
    remember(listening.store, technology_id, STEADY)

    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.615], first=9)
    )

    assert result.findings["disposition"] == "IGNORE"
    assert result.findings["anomalies"] == []
    assert not listening.store.objects(types=["Anomaly"])


def test_categorical_novelty_is_detected(listening, technology_id):
    remember(
        listening.store,
        technology_id,
        ["charge-cycling", "charge-cycling", "thermal-tolerance"],
        "demonstrated_capability",
    )

    result = listening.invoke(
        "anomaly_listener",
        inputs=observations(
            technology_id,
            ["self-healing electrolyte"],
            "demonstrated_capability",
            first=9,
        ),
    )
    detection = result.findings["detections"][0]

    assert detection["dimensions"] == ["categorical_novelty"]
    assert detection["disposition"] == "ESCALATE"
    assert "never observed before" in detection["reasons"][0]


def test_the_same_reading_against_a_different_past(observer_store, technology_id):
    def score_against(history):
        store = ObjectStore()
        for document in observer_documents():
            store.put(AIOPObject.from_jsonld(document))
        observer = Observer("watchtower", store=store, authority=INTERNAL_AUTHORITY)
        observer.install(AnomalyListener())
        observer.assign(mission_for("anomaly_listener"))
        remember(store, technology_id, history)
        result = observer.invoke(
            "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
        )
        return result.findings["score"]

    assert score_against(STEADY) > 0.85
    assert score_against(NOISY) == 0.0


def test_the_first_observation_of_anything_is_noted_quietly(listening, technology_id):
    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.62])
    )
    detection = result.findings["detections"][0]

    assert detection["dimensions"] == ["first_observation"]
    assert detection["disposition"] == "WATCH"


def test_scoring_is_reproducible(observer_store, technology_id):
    remember(observer_store, technology_id, STEADY)
    listener = AnomalyListener()
    history = observation_module.history(observer_store, technology_id, "cycle_efficiency")
    comparison = Comparison(
        target=technology_id,
        value=0.83,
        target_property="cycle_efficiency",
        values=tuple(anomaly_module.comparison_values(history)),
    )

    first = listener.detectors.run(comparison)
    second = listener.detectors.run(comparison)

    assert [signal.to_dict() for signal in first] == [
        signal.to_dict() for signal in second
    ]
    assert [signal.score for signal in first] == sorted(
        (signal.score for signal in first), reverse=True
    )
    assert anomaly_module.fingerprint(
        history[0], history
    ) == anomaly_module.fingerprint(history[0], history)


def test_the_score_is_the_strongest_dimension():
    signals = [
        Signal("categorical_novelty", 0.9, "novel"),
        Signal("magnitude_of_change", 0.4, "moved"),
    ]

    assert anomaly_module.score_of(signals) == 0.9
    assert anomaly_module.score_of([]) == 0.0


def test_detectors_are_extensible():
    def always(comparison):
        return Signal("bespoke", 1.0, "because the deployment says so")

    registry = DEFAULT_DETECTORS.extend(DetectorRegistry.of(always))
    signals = registry.run(Comparison(target="x", value=1.0))

    assert "bespoke" in [signal.dimension for signal in signals]
    assert len(registry) == len(DEFAULT_DETECTORS) + 1


def test_a_declared_threshold_is_an_expectation_from_outside(listening, technology_id):
    remember(listening.store, technology_id, [40.0, 41.0, 39.5, 40.5])

    result = listening.invoke(
        "anomaly_listener",
        inputs=observations(technology_id, [46.0], first=9),
        parameters={"expected_range": {"cycle_efficiency": (38.0, 42.0)}},
    )
    detection = result.findings["detections"][0]

    assert "threshold_crossing" in detection["dimensions"]


def test_a_thousand_identical_readings_do_not_become_an_anomaly(listening, technology_id):
    remember(listening.store, technology_id, [0.62] * 12)

    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.62], first=20)
    )

    assert result.findings["disposition"] == "IGNORE"


def test_the_policy_decides_the_disposition():
    policy = AnomalyPolicy(watch=0.1, research=0.2, escalate=0.3)

    assert policy.disposition(0.05) == "IGNORE"
    assert policy.disposition(0.15) == "WATCH"
    assert policy.disposition(0.25) == "RESEARCH"
    assert policy.disposition(0.95) == "ESCALATE"


# -- what it leaves behind --------------------------------------------------
def test_an_anomaly_is_an_object_with_lineage(listening, technology_id):
    remember(listening.store, technology_id, STEADY)
    observation = observations(technology_id, [0.83], first=9)[0]

    result = listening.invoke("anomaly_listener", inputs=[observation])
    anomaly = listening.store.get(result.findings["anomalies"][0])
    predicates = {(r.predicate, r.object) for r in anomaly.relations}

    assert "Anomaly" in anomaly.types
    assert ("derivedFrom", observation.id) in predicates
    assert ("about", technology_id) in predicates
    assert ("detectedBy", "urn:aiop:capability:anomaly_listener") in predicates
    assert len(anomaly.get("comparison_context")) == len(STEADY)
    assert anomaly.get("detected_by") == "urn:aiop:capability:anomaly_listener"
    assert anomaly.get("detector_version") == "0.1"
    assert anomaly.get("expected_state") == pytest.approx(0.6137, abs=1e-3)
    assert anomaly.get("observed_state") == 0.83


def test_an_anomaly_is_not_an_opportunity(listening, technology_id):
    remember(listening.store, technology_id, STEADY)

    listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )

    assert not listening.store.objects(types=["Opportunity"])
    assert not listening.store.objects(types=["Assessment"])
    anomaly = listening.store.objects(types=["Anomaly"])[0]
    assert anomaly.get("disposition") in {"IGNORE", "WATCH", "RESEARCH", "ESCALATE"}
    assert anomaly.get("recommended_action") is None


def test_the_observation_is_persisted_before_anything_derives_from_it(
    listening, technology_id
):
    remember(listening.store, technology_id, STEADY)
    observation = observations(technology_id, [0.83], first=9)[0]

    listening.invoke("anomaly_listener", inputs=[observation])

    assert listening.store.contains(observation.id)
    assert listening.store.get(observation.id).state is State.ACTIVE


def test_the_same_run_twice_writes_one_anomaly(listening, technology_id):
    remember(listening.store, technology_id, STEADY)
    observation = observations(technology_id, [0.83], first=9)[0]

    first = listening.invoke("anomaly_listener", inputs=[observation])
    second = listening.invoke("anomaly_listener", inputs=[observation])

    assert first.findings["anomalies"] == second.findings["anomalies"]
    assert len(listening.store.objects(types=["Anomaly"])) == 1


def test_an_execution_record_describes_the_run(listening, technology_id):
    remember(listening.store, technology_id, STEADY)
    observation = observations(technology_id, [0.83], first=9)[0]

    result = listening.invoke("anomaly_listener", inputs=[observation])
    record = result.record

    assert record.get("observer") == listening.id
    assert record.get("observer_version") == listening.version
    assert record.get("invoked") == "anomaly_listener"
    assert record.get("capability_version") == "0.1"
    assert record.get("mission") == listening.mission.identifier
    assert set(record.get("authority")) == {
        "CREATE_OBJECT",
        "OBSERVE",
        "READ",
        "RELATE_OBJECTS",
    }
    assert observation.id in record.get("inputs_read")
    assert result.findings["anomalies"][0] in record.get("objects_created")
    assert record.get("started_at") <= record.get("completed_at")
    assert record.get("status") == "COMPLETE"


def test_a_refusal_is_recorded_too(observer_store, technology_id):
    watcher = Observer(
        "watcher", store=observer_store, authority=Authority.of(Permission.READ)
    )
    watcher.install(AnomalyListener())

    result = watcher.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83])
    )

    assert result.record.get("status") == "REFUSED"
    assert result.record.get("missing_authority")
    assert result.record.get("objects_created") == []
    assert watcher.records() == [result.record]


def test_a_capability_that_raises_is_recorded_then_raised(watchtower, technology_id):
    class Broken(Trivial):
        def run(self, context):
            raise RuntimeError("the sensor fell over")

    watchtower.install(Broken(name="broken"))

    with pytest.raises(RuntimeError):
        watchtower.invoke("broken", inputs=observations(technology_id, [1.0]))

    record = watchtower.records()[-1]
    assert record.get("status") == "FAILED"
    assert "the sensor fell over" in record.get("refusal")


def test_no_hidden_reasoning_is_stored(listening, technology_id):
    remember(listening.store, technology_id, STEADY)

    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )
    anomaly = listening.store.get(result.findings["anomalies"][0])

    assert set(anomaly.properties) & {"score", "reasons", "signals"}
    assert "chain_of_thought" not in anomaly.properties
    assert all(
        isinstance(reason, str) and len(reason) < 200
        for reason in anomaly.get("reasons")
    )


# -- serialisation and the profile -----------------------------------------
def test_everything_survives_a_round_trip(listening, technology_id):
    remember(listening.store, technology_id, STEADY)
    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )

    for identifier in [*result.record.get("objects_created"), result.record.id]:
        original = listening.store.get(identifier)
        restored = AIOPObject.from_jsonld(original.to_jsonld())
        assert restored.id == original.id
        assert restored.types == original.types
        assert restored.state == original.state
        assert restored.relations == original.relations
        assert restored.properties == original.properties


def test_the_profile_declares_what_the_observer_writes():
    assert {"Observer", "Capability", "Mission", "Observation", "Anomaly"} <= set(
        OBSERVER_PROFILE.known_types
    )
    assert OBSERVER_PROFILE.vocabulary.inverse_of("about") == "subjectOf"
    assert OBSERVER_PROFILE.vocabulary.inverse_of("observedBy") == "observed"


def test_everything_written_satisfies_the_profile(listening, technology_id):
    remember(listening.store, technology_id, STEADY)
    listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )

    for obj in listening.store.objects():
        assert validate_object(obj, OBSERVER_PROFILE).errors == [], obj.id


def test_everything_the_observer_writes_is_in_the_context(listening, technology_id):
    contexts = [
        load_context(OBSERVER_CONTEXT_FILE),
        load_context(Path(aiop.__file__).with_name("context.jsonld")),
        load_context(Path(aiop.__file__).parents[1] / "profiles" / "context.jsonld"),
    ]
    known = set().union(*contexts)
    opaque = set().union(*(opaque_terms(context) for context in contexts))

    remember(listening.store, technology_id, STEADY)
    result = listening.invoke(
        "anomaly_listener", inputs=observations(technology_id, [0.83], first=9)
    )

    written = [*result.record.get("objects_created"), result.record.id, listening.id]
    for identifier in written:
        document = listening.store.get(identifier).to_jsonld()
        assert used_terms(document, opaque) <= known, identifier

    for document in observer_documents():
        assert used_terms(document, opaque) <= known, document["@id"]


def test_nothing_here_calls_a_model_or_a_network():
    source = Path(aiop.__file__).parents[1]
    files = sorted(
        [*(source / "observer").glob("*.py"), *(source / "capabilities").rglob("*.py")]
    )
    text = " ".join(path.read_text() for path in files)

    for forbidden in ("import requests", "urllib", "openai", "anthropic", "http://api"):
        assert forbidden not in text


def test_the_detector_arithmetic_is_hand_checkable():
    assert detector_module.mean([1.0, 2.0, 3.0]) == 2.0
    assert detector_module.deviation([2.0, 2.0]) == 0.0
    assert detector_module.deviation([1.0, 3.0]) == 1.0

    signal = detector_module.deviation_from_expected(
        Comparison(target="x", value=5.0, values=(1.0, 3.0))
    )
    assert signal.magnitude == 3.0
    assert signal.score == 0.75
