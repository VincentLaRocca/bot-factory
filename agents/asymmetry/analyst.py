"""The Asymmetry Analyst: a process, not a place where knowledge lives.

The analyst holds nothing. It reads an opportunity out of the store, assembles
a bounded cluster around it, works out what is missing, asks a research
provider for the missing pieces, records what comes back as claims and
evidence, runs the calculations whose inputs now exist, forms a judgement, and
writes all of it back as ordinary objects. When the run ends the objects remain
and the analyst does not; another model — or a person, next year — can read the
result without ever seeing this conversation.

```python
run = AsymmetryAnalyst(store, research=MockResearchProvider(findings)).run(opportunity)
run.assessment.get("recommended_action")   # 'RESEARCH'
run.record.get("gaps_discovered")          # 7
```
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from aiop import AIOPObject, Provenance, State
from aiop.provenance import utcnow
from profiles import (
    ASYMMETRY_CALCULATION_SCHEMA,
    ASYMMETRY_CONTEXT,
    ASYMMETRY_FUNCTIONS,
)
from reasoning import (
    CalculationSchema,
    FunctionRegistry,
    MalformedCalculation,
    ReasoningEngine,
    UnresolvedBinding,
    UnknownFunction,
)
from store import ObjectCluster, ObjectStore, View

from . import assessment as judgement_module
from . import claims, completeness as completeness_module, gaps as gaps_module
from .assessment import (
    DeterministicAnalyst,
    Dossier,
    Judgement,
    ReasoningProvider,
    Verdict,
)
from .completeness import Completeness
from .policy import DEFAULT_POLICY, AnalysisPolicy
from .research import NoResearchProvider, ResearchProvider
from .specification import ASYMMETRY_SPECIFICATION, AnalysisSpecification
from .views import ANALYSIS_VIEW, DOSSIER_VIEW

AGENT = "urn:aiop:agent:asymmetry-analyst"
VERSION = "0.1"


@dataclass
class AnalysisRun:
    """What one run produced, and what it read to produce it."""

    opportunity: str
    record: AIOPObject
    assessment: AIOPObject
    completeness: Completeness
    judgement: Judgement
    synergy: Verdict
    edge: Verdict
    gaps: Sequence[AIOPObject] = ()
    outcomes: Sequence[claims.ClaimOutcome] = ()
    results: Dict[str, AIOPObject] = field(default_factory=dict)
    unavailable: Sequence[Tuple[str, str]] = ()
    created: Sequence[str] = ()
    read: Sequence[str] = ()
    superseded: Sequence[str] = ()

    @property
    def action(self) -> str:
        return self.assessment.get("recommended_action")

    @property
    def open_gaps(self) -> List[AIOPObject]:
        return [gap for gap in self.gaps if gap.state is State.ACTIVE]

    @property
    def resolved(self) -> List[claims.ClaimOutcome]:
        return [outcome for outcome in self.outcomes if outcome.applied]


class AsymmetryAnalyst:
    """Reads opportunities, writes conclusions, owns nothing in between."""

    def __init__(
        self,
        store: ObjectStore,
        policy: AnalysisPolicy = DEFAULT_POLICY,
        research: Optional[ResearchProvider] = None,
        reasoner: Optional[ReasoningProvider] = None,
        specification: AnalysisSpecification = ASYMMETRY_SPECIFICATION,
        functions: FunctionRegistry = ASYMMETRY_FUNCTIONS,
        schema: CalculationSchema = ASYMMETRY_CALCULATION_SCHEMA,
        view: View = ANALYSIS_VIEW,
        context: object = None,
        agent: str = AGENT,
    ) -> None:
        self.store = store
        self.policy = policy
        self.research = research if research is not None else NoResearchProvider()
        self.reasoner = reasoner if reasoner is not None else DeterministicAnalyst()
        self.specification = specification
        self.schema = schema
        self.view = view
        self.context = context if context is not None else list(ASYMMETRY_CONTEXT)
        self.agent = agent
        self.engine = ReasoningEngine(
            store, registry=functions, schema=schema, agent=agent
        )

    # -- the run -----------------------------------------------------------
    def run(self, opportunity_id: str) -> AnalysisRun:
        """Analyse one opportunity, end to end, and leave the objects behind."""
        started = utcnow()
        opportunity = self.store.get(opportunity_id)
        created: List[str] = []

        cluster = self.assemble(opportunity_id)
        completeness = self.inspect(cluster, opportunity_id)
        gaps = gaps_module.discover(
            self.store,
            opportunity_id,
            completeness,
            self.policy,
            self.schema,
            self.agent,
            self.context,
        )
        created.extend(gap.id for gap in gaps)

        outcomes = self.investigate(gaps)
        for outcome in outcomes:
            created.extend(obj.id for obj in outcome.created)

        # The graph has changed under us, so look again before judging.
        cluster = self.assemble(opportunity_id)
        completeness = self.inspect(cluster, opportunity_id)
        results, unavailable = self.calculate(cluster)
        created.extend(result.id for result in results.values())

        dossier = Dossier(
            opportunity=opportunity,
            completeness=completeness,
            policy=self.policy,
            gaps=gaps_module.sort([g for g in gaps if g.state is State.ACTIVE]),
            # Every standing claim in the neighbourhood, not merely the ones
            # this run happened to make: two runs over the same graph must
            # rest on the same evidence and reach the same conclusion.
            claims=sorted(
                (
                    claim
                    for claim in cluster.of_type("Claim")
                    if claim.state is State.ACTIVE
                ),
                key=lambda claim: claim.id,
            ),
            results=results,
            unavailable=tuple(unavailable),
            cluster=tuple(cluster.ids),
        )

        assessment, judgement, superseded = self.judge(dossier)
        created.append(assessment.id)
        created.extend(
            relation.object
            for relation in assessment.relations
            if relation.predicate == "derivedFrom"
            and relation.object.startswith(f"{opportunity_id}#")
        )

        record = self.record(
            opportunity_id=opportunity_id,
            started=started,
            cluster=cluster,
            completeness=completeness,
            gaps=gaps,
            results=results,
            created=created,
            status="COMPLETE",
        )
        return AnalysisRun(
            opportunity=opportunity_id,
            record=record,
            assessment=assessment,
            completeness=completeness,
            judgement=judgement,
            synergy=judgement_module.synergy(dossier),
            edge=judgement_module.our_edge(dossier, self.policy),
            gaps=gaps,
            outcomes=outcomes,
            results=results,
            unavailable=tuple(unavailable),
            created=tuple(dict.fromkeys(created)),
            read=tuple(cluster.ids),
            superseded=tuple(superseded),
        )

    def reanalyse(self, opportunity_id: str) -> AnalysisRun:
        """Recompute what new evidence has made stale, then judge again."""
        self.engine.recompute_stale()
        return self.run(opportunity_id)

    # -- the steps ---------------------------------------------------------
    def assemble(self, opportunity_id: str, view: Optional[View] = None) -> ObjectCluster:
        """The bounded neighbourhood the analysis is allowed to see."""
        return self.store.cluster(opportunity_id, view or self.view)

    def inspect(self, cluster: ObjectCluster, root: str) -> Completeness:
        """What the graph currently answers, and what it does not."""
        return completeness_module.assess(
            self.store, cluster, root, self.specification
        )

    def investigate(self, gaps: Sequence[AIOPObject]) -> List[claims.ClaimOutcome]:
        """Ask the research provider about the gaps worth asking about."""
        outcomes: List[claims.ClaimOutcome] = []
        for gap in gaps_module.queue(gaps, self.policy.maximum_research):
            target = gap.get("target")
            if target is None or not self.store.contains(target):
                continue
            findings = self.research.research(gap)
            outcome = claims.assemble(
                store=self.store,
                gap=gap,
                findings=findings,
                target=target,
                dimension=gap.get("dimension"),
                prop=gap.get("target_property"),
                policy=self.policy,
                agent=self.agent,
                context=self.context,
            )
            outcomes.append(outcome)
            if outcome.applied:
                gap.transition(State.RETIRED)
                gap.set("status", "RESOLVED")
        return outcomes

    def calculate(
        self, cluster: ObjectCluster
    ) -> Tuple[Dict[str, AIOPObject], List[Tuple[str, str]]]:
        """Run every calculation in the cluster whose inputs now exist.

        A calculation with an unknown input produces nothing at all. Inventing
        a plausible number here would poison every figure downstream of it, so
        the missing input is reported instead.
        """
        results: Dict[str, AIOPObject] = {}
        unavailable: List[Tuple[str, str]] = []
        for calculation in sorted(cluster.of_type("Calculation"), key=lambda o: o.id):
            if calculation.state is not State.ACTIVE:
                continue
            try:
                result = self.engine.evaluate(calculation.id)
            except (UnresolvedBinding, MalformedCalculation, UnknownFunction) as error:
                unavailable.append((calculation.id, str(error)))
                continue
            results[result.get(self.schema.function_property)] = result
        return results, unavailable

    def judge(self, dossier: Dossier) -> Tuple[AIOPObject, Judgement, List[str]]:
        """Form the judgement and store it, superseding any it replaces."""
        judgement = self.reasoner.assess(dossier)
        assessment, companions = judgement_module.build(
            store=self.store,
            dossier=dossier,
            judgement=judgement,
            synergy_verdict=judgement_module.synergy(dossier),
            edge_verdict=judgement_module.our_edge(dossier, self.policy),
            agent=self.agent,
            context=self.context,
            reasoner=self.reasoner.name,
        )

        existing = self.store.find(assessment.id)
        if existing is not None:
            return existing, judgement, []

        superseded: List[str] = []
        for standing in judgement_module.current_assessments(
            self.store, dossier.opportunity.id
        ):
            assessment.relate("supersedes", standing.id)
            standing.transition(State.SUPERSEDED)
            self.store.reindex(standing.id)
            superseded.append(standing.id)

        for companion in companions:
            if not self.store.contains(companion.id):
                self.store.add(companion)
        self.store.add(assessment)
        return assessment, judgement, superseded

    def record(
        self,
        opportunity_id: str,
        started: datetime,
        cluster: ObjectCluster,
        completeness: Completeness,
        gaps: Sequence[AIOPObject],
        results: Dict[str, AIOPObject],
        created: Sequence[str],
        status: str,
    ) -> AIOPObject:
        """The audit trail: who ran what, over what, and what came out.

        Conclusions, inputs and outputs — not the reasoning's inner monologue.
        An execution record is for reconstructing a decision, not for replaying
        a mind.
        """
        completed = utcnow()
        written = sorted(dict.fromkeys(created))
        record = AIOPObject(
            id=f"{opportunity_id}#run-{completed.strftime('%Y%m%dT%H%M%S%f')}",
            types=["ExecutionRecord"],
            context=self.context,
            state=State.ACTIVE,
            properties={
                "agent": self.agent,
                "agent_version": VERSION,
                "profile_version": self.specification.version,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "policy": self.policy.to_dict(),
                "research_provider": self.research.name,
                "reasoner": self.reasoner.name,
                "cluster_fingerprint": cluster_fingerprint(cluster),
                "completeness_report": completeness.to_dict(),
                "objects_read": sorted(cluster.ids),
                "objects_created": written,
                "calculations_executed": sorted(
                    result.get(self.schema.calculation_property)
                    for result in results.values()
                ),
                "gaps_discovered": [gap.id for gap in gaps],
                "status": status,
            },
        )
        record.attest(
            Provenance(
                agent=self.agent,
                method="executed",
                source=opportunity_id,
                note=f"{len(created)} object(s) written, {len(gaps)} gap(s) open",
            )
        )
        record.relate("about", opportunity_id)
        for identifier in written:
            record.relate("produced", identifier)
        return self.store.add(record)


def cluster_fingerprint(cluster: ObjectCluster) -> str:
    """A digest of exactly what the analysis was allowed to see.

    Members and the states they were in: enough to tell later whether a run
    saw the same world a subsequent one did.
    """
    payload = [[obj.id, obj.state.value] for obj in cluster.objects()]
    canonical = json.dumps(sorted(payload), separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "AGENT",
    "AnalysisRun",
    "AsymmetryAnalyst",
    "DOSSIER_VIEW",
    "VERSION",
    "cluster_fingerprint",
]
