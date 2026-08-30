"""What is known, what is merely asserted, and what is missing.

Completeness is read off the graph, never off the analyst's memory: for each
dimension in the specification the analyst finds the object it belongs to, looks
for the property, and looks for anything standing behind it. A value with no
support is not the same as a fact, and neither is the same as silence — the
three are kept apart here so that everything downstream can keep them apart too.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence

from aiop import AIOPObject, State
from store import ObjectCluster, ObjectStore

from .specification import AnalysisSpecification, Dimension

#: Predicates by which one object stands behind another. ``qualifies`` is
#: deliberately absent: something that bears on a value without settling it is
#: not support for it.
SUPPORT_PREDICATES = ("supports",)
CONTRADICTION_PREDICATE = "contradicts"


class Status(str, Enum):
    """What the graph has to say about one dimension."""

    #: A value, and something behind it if the dimension demands one.
    KNOWN = "KNOWN"
    #: A value, but nothing supports it. It is an assertion, not a fact.
    UNSUPPORTED = "UNSUPPORTED"
    #: No value anywhere.
    UNKNOWN = "UNKNOWN"
    #: Not even an object of the right kind to hold the value.
    UNREACHABLE = "UNREACHABLE"

    @property
    def is_gap(self) -> bool:
        return self is not Status.KNOWN


@dataclass(frozen=True)
class Finding:
    """One dimension, as the graph currently has it."""

    dimension: Dimension
    status: Status
    target: Optional[str] = None
    value: object = None
    support: Sequence[str] = ()
    contradiction: Sequence[str] = ()

    @property
    def name(self) -> str:
        return self.dimension.name

    @property
    def known(self) -> bool:
        return self.status is Status.KNOWN

    @property
    def has_value(self) -> bool:
        return self.status in (Status.KNOWN, Status.UNSUPPORTED)

    @property
    def contested(self) -> bool:
        return bool(self.contradiction)


@dataclass(frozen=True)
class Completeness:
    """The whole picture: every dimension and how well the graph answers it."""

    findings: Sequence[Finding]
    specification: AnalysisSpecification

    def __iter__(self):
        return iter(self.findings)

    def __len__(self) -> int:
        return len(self.findings)

    def by_name(self, name: str) -> Finding:
        for finding in self.findings:
            if finding.name == name:
                return finding
        raise KeyError(name)

    def known(self) -> List[Finding]:
        return [f for f in self.findings if f.known]

    def gaps(self) -> List[Finding]:
        return [f for f in self.findings if f.status.is_gap]

    def values(self) -> Dict[str, object]:
        """Every dimension that has a value at all, supported or not."""
        return {f.name: f.value for f in self.findings if f.has_value}

    @property
    def score(self) -> float:
        """Known dimensions as a share of what matters, weighted by impact.

        An unsupported value counts for half: something is written down, but
        nothing yet says it is true.
        """
        total = sum(f.dimension.decision_impact for f in self.findings)
        if not total:
            return 0.0
        earned = sum(
            f.dimension.decision_impact
            * (1.0 if f.known else 0.5 if f.status is Status.UNSUPPORTED else 0.0)
            for f in self.findings
        )
        return round(earned / total, 4)

    def by_group(self) -> Dict[str, float]:
        """The same score, per group, so the shape of the ignorance is visible."""
        scores: Dict[str, float] = {}
        for group in self.specification.groups():
            findings = [f for f in self.findings if f.dimension.group == group]
            total = sum(f.dimension.decision_impact for f in findings)
            if not total:
                continue
            earned = sum(
                f.dimension.decision_impact
                * (1.0 if f.known else 0.5 if f.status is Status.UNSUPPORTED else 0.0)
                for f in findings
            )
            scores[group] = round(earned / total, 4)
        return scores

    def to_dict(self) -> Dict[str, object]:
        return {
            "specification": self.specification.version,
            "score": self.score,
            "groups": self.by_group(),
            "known": [f.name for f in self.known()],
            "unknown": [f.name for f in self.gaps()],
        }


def _has_value(obj: AIOPObject, key: str) -> bool:
    value = obj.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def target_for(
    dimension: Dimension, cluster: ObjectCluster, root: str
) -> Optional[AIOPObject]:
    """The object a dimension's value belongs on, nearest the root first."""
    candidates = cluster.of_type(dimension.target_type)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda obj: (
            0 if obj.id == root else 1,
            cluster.depth_of(obj.id) if cluster.depth_of(obj.id) is not None else 99,
            obj.id,
        ),
    )[0]


def support_for(
    store: ObjectStore, target: AIOPObject, dimension: Dimension
) -> List[str]:
    """Objects that point at this one and speak to this dimension."""
    found: List[str] = []
    for predicate in SUPPORT_PREDICATES:
        for relation in store.inbound(target.id, predicate):
            source = store.find(relation.subject)
            if source is None or source.state is not State.ACTIVE:
                continue
            if source.get("dimension") == dimension.name:
                found.append(source.id)
    return sorted(set(found))


def contradiction_for(
    store: ObjectStore, target: AIOPObject, dimension: Dimension
) -> List[str]:
    """Objects that point at this one and dispute this dimension."""
    found = [
        relation.subject
        for relation in store.inbound(target.id, CONTRADICTION_PREDICATE)
        if store.find(relation.subject) is not None
        and store.get(relation.subject).state is State.ACTIVE
        and store.get(relation.subject).get("dimension") == dimension.name
    ]
    return sorted(set(found))


def assess(
    store: ObjectStore,
    cluster: ObjectCluster,
    root: str,
    specification: AnalysisSpecification,
) -> Completeness:
    """Read every dimension of the specification off the cluster."""
    findings: List[Finding] = []
    for dimension in specification:
        target = target_for(dimension, cluster, root)
        if target is None:
            findings.append(Finding(dimension, Status.UNREACHABLE))
            continue

        support = support_for(store, target, dimension)
        contradiction = contradiction_for(store, target, dimension)
        if not _has_value(target, dimension.property):
            findings.append(
                Finding(
                    dimension,
                    Status.UNKNOWN,
                    target=target.id,
                    support=support,
                    contradiction=contradiction,
                )
            )
            continue

        supported = bool(support) or not dimension.evidence_required
        findings.append(
            Finding(
                dimension,
                Status.KNOWN if supported and not contradiction else Status.UNSUPPORTED,
                target=target.id,
                value=target.get(dimension.property),
                support=support,
                contradiction=contradiction,
            )
        )
    return Completeness(findings=tuple(findings), specification=specification)


__all__ = [
    "Completeness",
    "Finding",
    "Status",
    "assess",
    "contradiction_for",
    "support_for",
    "target_for",
]
