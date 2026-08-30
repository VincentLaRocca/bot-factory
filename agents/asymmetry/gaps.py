"""Information gaps: the unknowns, written down and ranked.

A gap is an ordinary Information Object, not a note in the agent's head. It
says which dimension is missing, what would settle it, and how much settling it
is worth — so a different analyst, or a person, can pick up the research queue
tomorrow without ever seeing this run.

The ranking is a documented heuristic, not an oracle:

    research_priority = decision_impact x uncertainty x dependency_weight x resolvability

* **decision_impact** comes from the specification: how much the decision turns
  on this dimension at all.
* **uncertainty** is 1.0 when nothing is known, 0.5 when a value exists but
  nothing supports it, and 0.75 when the value is disputed.
* **dependency_weight** is ``1 + 0.5 x`` the number of calculations that read
  this exact property — a number the graph already knows, because bindings are
  declared rather than implied.
* **resolvability** is the specification's guess at how gettable the answer is:
  ranking research by value alone queues up the unanswerable.

It is deliberately simple arithmetic over declared numbers. Two runs over the
same graph rank the gaps identically, and anybody can check the sum.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from aiop import AIOPObject, Provenance, State
from reasoning import CalculationSchema
from store import ObjectStore

from .completeness import Completeness, Finding, Status
from .policy import AnalysisPolicy

#: How uncertain each status is, for the ranking.
UNCERTAINTY = {
    Status.UNKNOWN: 1.0,
    Status.UNREACHABLE: 1.0,
    Status.UNSUPPORTED: 0.5,
    Status.KNOWN: 0.0,
}

#: Where the priority score stops being worth a word.
IMPORTANCE_BANDS = ((0.5, "HIGH"), (0.25, "MEDIUM"), (0.0, "LOW"))


def importance_of(priority: float) -> str:
    for threshold, label in IMPORTANCE_BANDS:
        if priority >= threshold:
            return label
    return "LOW"


def dependants_of_property(
    store: ObjectStore, target: str, prop: str, schema: CalculationSchema
) -> List[str]:
    """The calculations whose declared inputs read ``target.prop``."""
    dependants = []
    for calculation in store.objects(types=["Calculation"]):
        for binding in calculation.get(schema.inputs_property) or []:
            if (
                binding.get(schema.source_key) == target
                and binding.get(schema.source_property_key) == prop
            ):
                dependants.append(calculation.id)
                break
    return sorted(dependants)


@dataclass(frozen=True)
class Ranking:
    """The four factors and the number they multiply to."""

    decision_impact: float
    uncertainty: float
    dependency_weight: float
    resolvability: float
    dependants: Sequence[str] = ()

    @property
    def priority(self) -> float:
        return round(
            self.decision_impact
            * self.uncertainty
            * self.dependency_weight
            * self.resolvability,
            4,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "decision_impact": self.decision_impact,
            "uncertainty": self.uncertainty,
            "dependency_weight": self.dependency_weight,
            "resolvability": self.resolvability,
            "research_priority": self.priority,
        }


def rank(
    finding: Finding, store: ObjectStore, schema: CalculationSchema
) -> Ranking:
    """Score one gap by the documented heuristic."""
    dimension = finding.dimension
    dependants = (
        dependants_of_property(store, finding.target, dimension.property, schema)
        if finding.target is not None
        else []
    )
    uncertainty = 0.75 if finding.contested else UNCERTAINTY[finding.status]
    return Ranking(
        decision_impact=dimension.decision_impact,
        uncertainty=uncertainty,
        dependency_weight=1.0 + 0.5 * len(dependants),
        resolvability=dimension.resolvability,
        dependants=tuple(dependants),
    )


def gap_id(root: str, dimension_name: str) -> str:
    return f"{root}#gap-{dimension_name.replace('.', '-')}"


def _reason(finding: Finding, ranking: Ranking) -> str:
    dimension = finding.dimension
    if finding.status is Status.UNREACHABLE:
        return (
            f"No {dimension.target_type} is connected to the opportunity, so "
            f"{dimension.property} has nowhere to live."
        )
    if finding.status is Status.UNSUPPORTED:
        return (
            f"{dimension.property} is asserted but nothing supports it, and "
            f"{len(ranking.dependants)} calculation(s) read it."
        )
    if finding.contested:
        return f"{dimension.property} is disputed by the evidence on file."
    return f"{dimension.description} Nothing in the graph answers this."


def build(
    finding: Finding,
    ranking: Ranking,
    root: str,
    agent: str,
    context: object,
) -> AIOPObject:
    """The gap as an object: what is missing, why it matters, what would fix it."""
    dimension = finding.dimension
    gap = AIOPObject(
        id=gap_id(root, dimension.name),
        types=["InformationGap"],
        context=context,
        state=State.ACTIVE,
        properties={
            "dimension": dimension.name,
            "target_property": dimension.property,
            "status": finding.status.value,
            "importance": importance_of(ranking.priority),
            "reason": _reason(finding, ranking),
            "required_evidence": list(dimension.required_evidence)
            or [dimension.description],
            **ranking.to_dict(),
        },
    )
    if finding.target is not None:
        gap.set("target", finding.target)
    gap.attest(
        Provenance(
            agent=agent,
            method="derived",
            source=root,
            note=f"{dimension.name} is {finding.status.value.lower()}",
        )
    )
    gap.relate("about", root, dimension=dimension.name)
    if finding.target is not None and finding.target != root:
        gap.relate("about", finding.target, dimension=dimension.name)
    return gap


def discover(
    store: ObjectStore,
    root: str,
    completeness: Completeness,
    policy: AnalysisPolicy,
    schema: CalculationSchema,
    agent: str,
    context: object,
) -> List[AIOPObject]:
    """Every gap worth recording, highest research priority first.

    A gap already in the store is reused rather than duplicated; one whose
    dimension has since been answered is retired, not deleted, so the record
    that it was once open survives.
    """
    gaps: List[AIOPObject] = []
    for finding in completeness:
        identifier = gap_id(root, finding.dimension.name)
        existing = store.find(identifier)

        if not finding.status.is_gap:
            if existing is not None and existing.state is State.ACTIVE:
                existing.transition(State.RETIRED)
            continue
        if finding.dimension.decision_impact < policy.gap_importance_threshold:
            continue

        ranking = rank(finding, store, schema)
        if existing is not None:
            gaps.append(_refresh(existing, finding, ranking))
            continue
        gaps.append(store.add(build(finding, ranking, root, agent, context)))
    return sort(gaps)


def _refresh(gap: AIOPObject, finding: Finding, ranking: Ranking) -> AIOPObject:
    """Bring a standing gap up to date without replacing it."""
    gap.set("status", finding.status.value)
    gap.set("importance", importance_of(ranking.priority))
    if finding.target is not None:
        gap.set("target", finding.target)
    for key, value in ranking.to_dict().items():
        gap.set(key, value)
    return gap


def sort(gaps: Sequence[AIOPObject]) -> List[AIOPObject]:
    """Highest research priority first, then by identifier."""
    return sorted(
        gaps, key=lambda gap: (-float(gap.get("research_priority", 0.0)), gap.id)
    )


def queue(gaps: Sequence[AIOPObject], limit: Optional[int] = None) -> List[AIOPObject]:
    """The gaps to actually research this run."""
    ordered = sort(gaps)
    return ordered if limit is None else ordered[:limit]


__all__ = [
    "IMPORTANCE_BANDS",
    "Ranking",
    "UNCERTAINTY",
    "build",
    "dependants_of_property",
    "discover",
    "gap_id",
    "importance_of",
    "queue",
    "rank",
    "sort",
]
