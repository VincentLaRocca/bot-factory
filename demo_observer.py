"""Plug a capability into an empty Observer and watch it notice something.

    python demo_observer.py           # the run, narrated
    python demo_observer.py --json    # the anomaly object itself

The observer starts knowing nothing: it can hold a mission, check a permission
and write a record, and that is all. The intelligence arrives as a plug-in, the
memory comes out of the store, and the same reading against a different past
gets a different answer.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Sequence

from aiop import AIOPObject
from capabilities.anomaly import AnomalyListener
from observer import (
    Authority,
    INTERNAL_AUTHORITY,
    Mission,
    MissionNotExecutable,
    Observer,
    Permission,
    Reading,
    SensorCard,
    StaticSensor,
    to_observations,
)
from profiles import VERSION_PREDICATE
from store import ObjectStore

EXAMPLES = Path(__file__).parent / "examples" / "observer"
TECHNOLOGY = "urn:aiop:technology:lattice-cell"
OBSERVER_ID = "urn:aiop:observer:watchtower"
START = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)

LAB = SensorCard(
    sensor="lab-report-feed",
    name="Laboratory report feed",
    independence_group="lattice-works-lab",
    description="Weekly cell test reports from the manufacturer's own lab.",
)

#: A cell that has done the same thing every week for eight weeks.
STEADY = [0.61, 0.62, 0.60, 0.63, 0.62, 0.61, 0.62, 0.60]
#: The same cell, in a world where the test rig was never reliable.
NOISY = [0.31, 0.88, 0.45, 0.79, 0.36, 0.91, 0.42, 0.79]
#: What it has ever been shown to do.
DEMONSTRATED = ["charge-cycling", "charge-cycling", "thermal-tolerance", "charge-cycling"]


def world() -> ObjectStore:
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    for path in sorted(EXAMPLES.glob("*.jsonld")):
        store.put(AIOPObject.from_jsonld(json.loads(path.read_text())))
    return store


def weekly(
    values: Sequence[object], target_property: str, first: int = 0
) -> List[Reading]:
    return [
        Reading(
            target=TECHNOLOGY,
            value=value,
            target_property=target_property,
            observed_at=START + timedelta(days=7 * (first + week)),
        )
        for week, value in enumerate(values)
    ]


def remember(store: ObjectStore, readings: Sequence[Reading]) -> List[AIOPObject]:
    """Persist the past. This is the listener's memory, and it is public."""
    sensor = StaticSensor(card=LAB, readings=readings)
    observations = to_observations(sensor, observer=OBSERVER_ID)
    return [store.add(observation) for observation in observations]


def reading(value: object, target_property: str, week: int) -> AIOPObject:
    sensor = StaticSensor(card=LAB, readings=weekly([value], target_property, week))
    return to_observations(sensor, observer=OBSERVER_ID)[0]


def show(invocation) -> None:
    detection = invocation.findings["detections"][0]
    print(f"  score {detection['score']:.2f} -> {detection['disposition']}")
    for reason in detection["reasons"]:
        print(f"    {reason}")
    print(f"    compared with {len(detection['compared_with'])} stored observation(s)")


def main() -> None:
    store = world()
    print(f"{len(store)} objects loaded from examples/observer\n")

    # 1. An observer with no intelligence in it at all -------------------
    watchtower = Observer("watchtower", store=store, authority=INTERNAL_AUTHORITY)
    watchtower.register()
    print(f"{watchtower.id} exists, capabilities: {watchtower.capabilities() or 'none'}")

    mission = Mission.build(
        objective="Notice when the lattice cell stops behaving as it always has",
        required_capabilities=["anomaly_listener"],
        authority=[
            Permission.READ,
            Permission.OBSERVE,
            Permission.CREATE_OBJECT,
            Permission.RELATE_OBJECTS,
        ],
        priority="HIGH",
        success_conditions=["every observation is triaged against its own history"],
        escalation_conditions=["any anomaly scoring at or above 0.85"],
        termination_conditions=["the mission is superseded"],
        output_expectations=["Anomaly", "ExecutionRecord"],
    )

    try:
        watchtower.assign(mission)
    except MissionNotExecutable as refused:
        print(f"\nassigning the mission: {refused.readiness.status}")
        for reason in refused.readiness.explain():
            print(f"    {reason}")

    # 2. The capability is installed, not inherited ----------------------
    card = watchtower.install(AnomalyListener())
    watchtower.register()
    print(f"\ninstalled {card.capability} v{card.version}")
    print(f"    accepts   {', '.join(card.accepts)} -> produces {', '.join(card.produces)}")
    print(f"    requires  {', '.join(str(p) for p in card.requires)}")
    readiness = watchtower.assign(mission)
    print(f"    mission   {readiness.status}")

    # 3. Memory: eight weeks of a cell doing the same thing --------------
    history = remember(store, weekly(STEADY, "cycle_efficiency"))
    print(f"\n{len(history)} weeks of cycle_efficiency remembered: {STEADY}")

    # 4. Something meaningfully different --------------------------------
    unusual = reading(0.83, "cycle_efficiency", week=len(STEADY))
    print("\nweek 9 reports 0.83")
    result = watchtower.invoke("anomaly_listener", inputs=[unusual])
    show(result)
    anomaly = store.get(result.findings["anomalies"][0])
    print(f"  {anomaly.id}")
    print(f"    derivedFrom  {unusual.id}")
    print(f"    detected_by  {anomaly.get('detected_by')}")
    print(f"    fingerprint  {anomaly.get('input_fingerprint')[:16]}…")
    print(f"  execution record {result.record.id}")
    print(
        f"    read {len(result.record.get('inputs_read'))}, "
        f"wrote {len(result.record.get('objects_created'))}, "
        f"authority {', '.join(result.record.get('authority'))}"
    )

    # 5. A boring week is not an anomaly ---------------------------------
    print("\nweek 10 reports 0.62")
    show(watchtower.invoke("anomaly_listener", inputs=[reading(0.62, "cycle_efficiency", 9)]))

    # 6. Categorical novelty: a thing it has never done before -----------
    remember(store, weekly(DEMONSTRATED, "demonstrated_capability"))
    print(f"\ndemonstrated capabilities so far: {sorted(set(DEMONSTRATED))}")
    novel = reading("self-healing electrolyte", "demonstrated_capability", week=4)
    print("a report claims: self-healing electrolyte")
    show(watchtower.invoke("anomaly_listener", inputs=[novel]))

    # 7. The same reading, a different past ------------------------------
    volatile = world()
    elsewhere = Observer(
        "watchtower", store=volatile, authority=INTERNAL_AUTHORITY, id=OBSERVER_ID
    )
    elsewhere.install(AnomalyListener())
    elsewhere.assign(mission)
    remember(volatile, weekly(NOISY, "cycle_efficiency"))
    print(f"\nin a world where the rig was always noisy {NOISY}")
    print("week 9 reports 0.83 again")
    show(elsewhere.invoke("anomaly_listener", inputs=[reading(0.83, "cycle_efficiency", 8)]))

    # 8. Capability without authority is not permission ------------------
    watcher = Observer(
        "read-only watcher",
        store=store,
        authority=Authority.of(Permission.READ, Permission.OBSERVE),
    )
    watcher.install(AnomalyListener())
    watcher.assign(mission, strict=False)
    refusal = watcher.invoke("anomaly_listener", inputs=[reading(0.91, "cycle_efficiency", 11)])
    print(f"\n{watcher.id} holds the capability but not the authority")
    print(f"  {refusal.status}: {refusal.refusal}")
    print(f"  recorded as {refusal.record.id}")

    # 9. A mission nobody can run ----------------------------------------
    bare = Observer("bare chassis", store=store, authority=INTERNAL_AUTHORITY)
    research = Mission.build(
        objective="Find out why the cell changed",
        required_capabilities=["anomaly_listener", "scientific_research"],
        authority=[Permission.READ, Permission.RESEARCH],
    )
    try:
        bare.assign(research)
    except MissionNotExecutable as refused:
        print(f"\n{bare.id}: {refused.readiness.status}")
        for reason in refused.readiness.explain():
            print(f"    {reason}")

    print(f"\n{len(store)} objects stored, {len(watchtower.records())} execution records")

    if "--json" in sys.argv:
        print(anomaly.to_json())


if __name__ == "__main__":
    main()
