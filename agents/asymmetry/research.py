"""Where evidence comes from — behind an interface, so it can change.

v0.1 does no web research. It reads evidence already in the store, or takes it
from a controlled fixture, through one small protocol that a future Scout agent
can implement without the analyst noticing:

```python
class ResearchProvider(Protocol):
    def research(self, gap: AIOPObject) -> List[AIOPObject]: ...
```

Keeping the boundary here is the point: the analyst's reasoning must be
testable without a network, an API key or a particular model vendor.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence

from aiop import AIOPObject, Provenance, State
from store import ObjectStore


class ResearchProvider(Protocol):
    """Anything that can go and find evidence bearing on a gap."""

    #: Recorded on the execution record so a run can be attributed.
    name: str

    def research(self, gap: AIOPObject) -> List[AIOPObject]:
        """Evidence objects bearing on ``gap``; an empty list is a fine answer."""


def evidence(
    identifier: str,
    title: str,
    dimension: str,
    claimed_value: object = None,
    confidence: float = 0.8,
    stance: str = "supports",
    source_kind: str = "secondary",
    independent: bool = True,
    context: object = None,
    agent: str = "urn:aiop:agent:research",
    observed_at: Optional[str] = None,
) -> AIOPObject:
    """Build an Evidence object of the shape the analyst knows how to read."""
    properties: Dict[str, object] = {
        "title": title,
        "dimension": dimension,
        "stance": stance,
        "source_kind": source_kind,
        "independent": independent,
        "confidence": confidence,
    }
    if claimed_value is not None:
        properties["claimed_value"] = claimed_value
    if observed_at is not None:
        properties["observed_at"] = observed_at

    obj = AIOPObject(
        id=identifier,
        types=["Evidence"],
        state=State.ACTIVE,
        properties=properties,
    )
    if context is not None:
        obj.context = context
    obj.attest(Provenance(agent=agent, method="observed", confidence=confidence))
    return obj


class StoreResearchProvider:
    """Evidence the store already holds, matched to the gap's dimension.

    The graph usually knows more than any one object does: a piece of evidence
    filed against a company months ago may be exactly what an opportunity's
    execution probability was waiting for.
    """

    name = "store"

    def __init__(self, store: ObjectStore, types: Sequence[str] = ("Evidence",)) -> None:
        self.store = store
        self.types = tuple(types)

    def research(self, gap: AIOPObject) -> List[AIOPObject]:
        dimension = gap.get("dimension")
        return sorted(
            (
                obj
                for obj in self.store.objects(types=self.types, states=[State.ACTIVE])
                if obj.get("dimension") == dimension
            ),
            key=lambda obj: obj.id,
        )


class MockResearchProvider:
    """A fixture: evidence prepared in advance, keyed by dimension.

    This is what makes the whole workflow testable offline. It answers exactly
    the gaps it was given answers for, and — importantly — returns nothing at
    all for the others, so the analyst has to cope with unresolved gaps.
    """

    name = "mock"

    def __init__(self, findings: Mapping[str, Iterable[AIOPObject]]) -> None:
        self.findings: Dict[str, List[AIOPObject]] = {
            dimension: list(objects) for dimension, objects in findings.items()
        }
        self.asked: List[str] = []

    def research(self, gap: AIOPObject) -> List[AIOPObject]:
        dimension = gap.get("dimension")
        self.asked.append(dimension)
        return list(self.findings.get(dimension, ()))


class ChainedResearchProvider:
    """Ask several providers in order and pool what they return."""

    def __init__(self, *providers: ResearchProvider) -> None:
        self.providers = providers
        self.name = "+".join(provider.name for provider in providers)

    def research(self, gap: AIOPObject) -> List[AIOPObject]:
        found: Dict[str, AIOPObject] = {}
        for provider in self.providers:
            for obj in provider.research(gap):
                found.setdefault(obj.id, obj)
        return [found[key] for key in sorted(found)]


class NoResearchProvider:
    """Answers nothing. The honest default when no source is configured."""

    name = "none"

    def research(self, gap: AIOPObject) -> List[AIOPObject]:
        return []


__all__ = [
    "ChainedResearchProvider",
    "MockResearchProvider",
    "NoResearchProvider",
    "ResearchProvider",
    "StoreResearchProvider",
    "evidence",
]
