"""Run the Asymmetry Analyst over a deliberately incomplete opportunity.

    python demo_asymmetry.py           # the run, narrated
    python demo_asymmetry.py --json    # the assessment object itself

The world it reads is missing most of what matters: no execution probability,
no adoption probability, no success probability, and a synergy case that is
half asserted and half absent. Watching what the analyst does with that is the
point — it says what it does not know, ranks it, asks for it, and calculates
only what it can honestly calculate.
"""

import json
import sys
from pathlib import Path

from agents.asymmetry import (
    AsymmetryAnalyst,
    ChainedResearchProvider,
    MockResearchProvider,
    StoreResearchProvider,
    claims,
    is_stale,
)
from aiop import AIOPObject
from profiles import VERSION_PREDICATE
from store import ObjectStore

EXAMPLES = Path(__file__).parent / "examples" / "asymmetry"
OPPORTUNITY = "urn:aiop:opportunity:clinical-triage"
COMPANY = "urn:aiop:company:vantage-clinical"
EXECUTION_GAP = f"{OPPORTUNITY}#gap-people-execution_probability"


def documents(pattern: str):
    return [json.loads(path.read_text()) for path in sorted(EXAMPLES.glob(pattern))]


def load_world() -> ObjectStore:
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    store.load(documents("*.jsonld"))
    return store


def available_research() -> MockResearchProvider:
    """Evidence that exists in the world but is not yet in our graph."""
    findings = {}
    for document in documents("research/*.jsonld"):
        obj = AIOPObject.from_jsonld(document)
        findings.setdefault(obj.get("dimension"), []).append(obj)
    return MockResearchProvider(findings)


def main() -> None:
    store = load_world()
    analyst = AsymmetryAnalyst(
        store,
        research=ChainedResearchProvider(
            StoreResearchProvider(store), available_research()
        ),
    )

    before = analyst.inspect(analyst.assemble(OPPORTUNITY), OPPORTUNITY)
    print(f"{len(store)} objects stored; the opportunity is {before.score:.0%} understood")
    for name, score in before.by_group().items():
        print(f"  {name:12} {score:>6.0%}")

    run = analyst.run(OPPORTUNITY)

    print(f"\n{len(run.gaps)} gaps, ranked by what resolving them is worth:")
    for gap in run.gaps[:6]:
        print(
            f"  {gap.get('research_priority'):>5.2f}  {gap.get('dimension'):38}"
            f"  {gap.get('importance')}"
        )

    print(f"\nresearch closed {len(run.resolved)} of them:")
    for outcome in run.resolved:
        print(
            f"  {outcome.gap.get('dimension'):38} = {outcome.value}"
            f"  [{len(outcome.evidence)} source(s)]"
        )
    still_open = [gap.get("dimension") for gap in run.open_gaps]
    print(f"  still unknown: {', '.join(still_open[:6])}")

    print(f"\nthe picture is now {run.completeness.score:.0%} complete")
    for function, result in sorted(run.results.items()):
        print(f"  {function:18} = {result.get('value'):>14,.2f}  [{result.id}]")
    for calculation, reason in run.unavailable:
        print(f"  unavailable: {calculation} — {reason}")

    print(f"\nsynergy: {run.synergy.status} — {run.synergy.rationale}")
    print(f"our edge: {run.edge.status} — {run.edge.rationale}")
    print(f"\n{run.assessment.id}")
    for field in ("bull_case", "base_case", "bear_case"):
        print(f"  {field:10} {run.assessment.get(field)}")
    print(
        f"  action     {run.action} ({run.assessment.get('priority')}), "
        f"confidence {run.assessment.get('confidence')}"
    )
    print(f"  next       {run.assessment.get('next_action')}")
    print(f"\nexecution record {run.record.id}")
    print(
        f"  read {len(run.read)} objects, wrote {len(run.created)}, "
        f"ran {len(run.record.get('calculations_executed'))} calculation(s)"
    )

    # -- new evidence arrives ------------------------------------------
    late = [AIOPObject.from_jsonld(doc) for doc in documents("late/*.jsonld")]
    outcome = claims.assemble(
        store=store,
        gap=store.get(EXECUTION_GAP),
        findings=late,
        target=COMPANY,
        dimension="people.execution_probability",
        prop="execution_probability",
        policy=analyst.policy,
        agent="urn:aiop:agent:diligence",
        context=analyst.context,
    )
    print(
        f"\n{late[0].id} lands: execution_probability 0.62 -> "
        f"{store.get(COMPANY).get('execution_probability')}"
    )
    print(f"  claim {outcome.claim.id} supersedes {outcome.superseded}")
    for dependent in analyst.engine.invalidated_by(COMPANY):
        print(f"  stale: {dependent.id} — {analyst.engine.check(dependent).reason}")
    print(f"  assessment stale: {is_stale(store, run.assessment)}")

    again = analyst.reanalyse(OPPORTUNITY)
    for function, result in sorted(again.results.items()):
        print(f"  recomputed {function:18} = {result.get('value'):>14,.2f}")
    for identifier in again.superseded:
        print(f"  {identifier} -> {store.get(identifier).state.value}")
    print(f"  new assessment {again.assessment.id}: {again.action}")

    if "--json" in sys.argv:
        print(again.assessment.to_json())


if __name__ == "__main__":
    main()
