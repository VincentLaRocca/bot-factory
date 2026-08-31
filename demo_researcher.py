"""Two different minds on one motherboard: notice it, then go and find out why.

    python demo_researcher.py           # the run, narrated
    python demo_researcher.py --json    # the contested claim itself

ABC Corporation's share price prints 42.00 where it has always printed about
four. The listener says *that is different*. The researcher asks four fixed
questions of the sources it was given and files what they said — including the
part where the exchange and the newswire disagree, and the part nobody could
answer.

Nothing about the observer changed between the two capabilities.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Sequence

from aiop import AIOPObject
from capabilities.anomaly import AnomalyListener
from capabilities.research import (
    Finding,
    MockResearchProvider,
    Researcher,
    SilentResearchProvider,
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
from profiles import VERSION_PREDICATE
from store import ObjectStore

EXAMPLES = Path(__file__).parent / "examples" / "research"
COMPANY = "urn:aiop:company:abc"
OBSERVER_ID = "urn:aiop:observer:market-desk"
START = datetime(2026, 1, 6, 21, 0, tzinfo=timezone.utc)

TAPE = SensorCard(
    sensor="exchange-tape",
    name="Exchange consolidated tape",
    independence_group="abc-exchange",
    description="End-of-day prints for listed equities.",
)

#: Six weeks of a share doing nothing in particular, then the print.
QUIET = [4.05, 4.18, 4.11, 4.22, 4.16, 4.20]
SPIKE = 42.00

#: Researching reaches outside the graph, so it is not part of the internal
#: charter the other demonstrations run on: a desk that asks sources questions
#: has to be chartered to do it, by name.
DESK_AUTHORITY = Authority.of(
    Permission.READ,
    Permission.OBSERVE,
    Permission.RESEARCH,
    Permission.CREATE_OBJECT,
    Permission.RELATE_OBJECTS,
)


def world() -> ObjectStore:
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    for path in sorted(EXAMPLES.glob("*.jsonld")):
        store.put(AIOPObject.from_jsonld(json.loads(path.read_text())))
    return store


def sources() -> Dict[str, object]:
    return json.loads((EXAMPLES / "sources.json").read_text())


def provider() -> MockResearchProvider:
    """The sources, as prepared answers. No network, no key, no vendor."""
    prepared = sources()
    return MockResearchProvider(
        findings={
            prepared["target"]: [Finding(**item) for item in prepared["findings"]]
        },
        unreachable={prepared["target"]: prepared["unreachable"]},
        name="exchange+filings+wire",
    )


def prints(values: Sequence[float], first: int = 0) -> List[Reading]:
    return [
        Reading(
            target=COMPANY,
            value=value,
            target_property="share_price",
            observed_at=START + timedelta(days=7 * (first + week)),
        )
        for week, value in enumerate(values)
    ]


def observation(value: float, week: int) -> AIOPObject:
    sensor = StaticSensor(card=TAPE, readings=prints([value], week))
    return to_observations(sensor, observer=OBSERVER_ID)[0]


def mission() -> Mission:
    return Mission.build(
        objective="Notice unusual prints in ABC Corporation and find out what caused them",
        required_capabilities=["anomaly_listener", "researcher"],
        authority=[
            Permission.READ,
            Permission.OBSERVE,
            Permission.RESEARCH,
            Permission.CREATE_OBJECT,
            Permission.RELATE_OBJECTS,
        ],
        priority="HIGH",
        success_conditions=["every anomaly is investigated or explicitly left open"],
        escalation_conditions=["any claim about a cause is contested"],
        termination_conditions=["the mission is superseded"],
        output_expectations=["Anomaly", "Evidence", "Claim", "ExecutionRecord"],
    )


def show(investigation: Dict[str, object], store: ObjectStore) -> None:
    for topic, status in investigation["topics"].items():
        print(f"    {topic:<19} {status}")
    for identifier in investigation["claims"]:
        claim = store.get(identifier)
        print(f"\n  {claim.get('status')}: {claim.get('statement')}")
        for predicate in ("supporting", "contradicting", "qualifying"):
            for evidence_id in claim.get(predicate) or ():
                evidence = store.get(evidence_id)
                print(
                    f"    {predicate[:13]:<13} {evidence.get('source_name')} "
                    f"({evidence.get('source_type')}, "
                    f"group {evidence.get('independence_group')})"
                )


def main() -> None:
    store = world()
    desk = Observer("market desk", store=store, authority=DESK_AUTHORITY, id=OBSERVER_ID)
    desk.install(AnomalyListener())
    desk.install(Researcher(provider()))
    desk.register()
    assigned = desk.assign(mission())
    print(f"{desk.id} capabilities: {', '.join(desk.capabilities())} -> {assigned.status}")
    for card in desk.cards():
        print(
            f"  {card.capability:<17} accepts {', '.join(card.accepts):<12} "
            f"-> {', '.join(card.produces)}"
        )

    # 1. Notice ----------------------------------------------------------
    for reading in prints(QUIET):
        store.add(to_observations(StaticSensor(card=TAPE, readings=[reading]), OBSERVER_ID)[0])
    print(f"\nsix weeks of share_price: {QUIET}")
    print(f"week 7 prints {SPIKE:.2f}")

    noticed = desk.invoke("anomaly_listener", inputs=[observation(SPIKE, len(QUIET))])
    anomaly = store.get(noticed.findings["anomalies"][0])
    print(
        f"  anomaly {anomaly.get('score'):.2f} -> {anomaly.get('disposition')}"
        f" ({', '.join(anomaly.get('dimensions'))})"
    )

    # 2. Find out why ----------------------------------------------------
    investigated = desk.invoke("researcher", inputs=[anomaly])
    report = investigated.findings["investigations"][0]
    print(f"\nresearcher asked {len(report['questions'])} questions of "
          f"{investigated.findings['provider']}:")
    for question in report["questions"]:
        print(f"    {question['question']}")
    print()
    show(report, store)

    contested = store.get(investigated.findings["contested"][0])
    print(
        "\n  the exchange and the wire disagree, and both are still in the graph;"
        f"\n  the cause topic ends {report['topics']['cause']}, not averaged into a story"
    )
    print(f"  nobody could be asked about: {', '.join(report['topics'].keys() & {'alternative'})}"
          f" -> {report['topics']['alternative']}")

    # 3. Nothing was written onto the company ----------------------------
    company = store.get(COMPANY)
    print(f"\n{company.id} still says only: {sorted(company.properties)}")
    print("  no researcher writes a value onto a target object: that is a validator's job")

    # 4. Running it again does not manufacture opinions -------------------
    again = desk.invoke("researcher", inputs=[anomaly])
    print(f"\nsecond identical run created {len(again.created)} objects, "
          f"re-read {len(again.findings['evidence'])} pieces of evidence")

    # 5. A researcher with no sources ------------------------------------
    blind_store = world()
    blind = Observer("quiet desk", store=blind_store, authority=DESK_AUTHORITY)
    blind.install(AnomalyListener())
    blind.install(Researcher(SilentResearchProvider()))
    blind.assign(mission())
    for reading in prints(QUIET):
        blind_store.add(
            to_observations(StaticSensor(card=TAPE, readings=[reading]), blind.id)[0]
        )
    spotted = blind.invoke("anomaly_listener", inputs=[observation(SPIKE, len(QUIET))])
    nothing = blind.invoke(
        "researcher", inputs=[blind_store.get(spotted.findings["anomalies"][0])]
    )
    print("\nthe same capability with no sources at all:")
    for topic, status in nothing.findings["investigations"][0]["topics"].items():
        print(f"    {topic:<19} {status}")
    print(f"  {len(nothing.created)} objects created — silence is recorded, not filled")

    # 6. Capability without authority ------------------------------------
    reader = Observer(
        "compliance reader",
        store=store,
        authority=Authority.of(Permission.READ, Permission.OBSERVE),
    )
    reader.install(Researcher(provider()))
    reader.assign(mission(), strict=False)
    refusal = reader.invoke("researcher", inputs=[anomaly])
    print(f"\n{reader.id} holds the capability but not RESEARCH")
    print(f"  {refusal.status}: {refusal.refusal}")

    print(
        f"\n{len(store)} objects stored, {len(desk.records())} execution records, "
        "observer/ unchanged"
    )

    if "--json" in sys.argv:
        print(json.dumps(contested.to_jsonld(), indent=2))


if __name__ == "__main__":
    main()
