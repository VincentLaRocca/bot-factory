"""Where findings come from — behind an interface, so it can change.

The researcher must not care whether an answer arrived from an exchange feed,
a filing, a newspaper, another observer or eventually a language model. It
hands a structured request across this boundary and receives structured
findings back, and everything vendor-shaped stays on the far side.

```python
class ResearchProvider(Protocol):
    name: str
    version: str

    def research(self, request: ResearchRequest) -> ResearchResponse: ...
```

v0.1 ships two implementations: a fixture that answers from prepared findings,
and one that answers nothing at all. The second is not a placeholder — a
provider that cannot establish a cause is a case the architecture has to
survive, so it is worth being able to construct on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

from profiles.research import STANCES, TOPICS


@dataclass(frozen=True)
class Question:
    """One thing investigation wants to know, and what kind of thing it is."""

    topic: str
    question: str

    def to_dict(self) -> Dict[str, str]:
        return {"topic": self.topic, "question": self.question}


@dataclass(frozen=True)
class ResearchRequest:
    """An anomaly, restated as questions a source could answer.

    The request carries the anomaly's *facts* — what was observed, what was
    expected, how far apart they are — and never its disposition. A source
    asked "why did this jump" should not also be told that somebody upstream
    thought the jump was exciting.
    """

    anomaly: str
    target: str
    questions: Tuple[Question, ...]
    target_property: Optional[str] = None
    observed_state: Any = None
    expected_state: Any = None
    magnitude: Optional[float] = None
    observed_at: Optional[str] = None
    asked_at: Optional[datetime] = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def topics(self) -> Tuple[str, ...]:
        return tuple(question.topic for question in self.questions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly": self.anomaly,
            "target": self.target,
            "target_property": self.target_property,
            "observed_state": self.observed_state,
            "expected_state": self.expected_state,
            "magnitude": self.magnitude,
            "questions": [question.to_dict() for question in self.questions],
        }


@dataclass(frozen=True)
class Finding:
    """One thing a source said, before it is anything in the graph.

    A finding is not yet Evidence: it is the provider's report, and the
    researcher decides how to write it down. ``proposition`` is what the
    source bears on and ``stance`` is how — including ``contradicts``, which
    a provider is expected to return rather than resolve.
    """

    topic: str
    source: str
    source_type: str
    content: str
    proposition: str
    stance: str = "supports"
    source_name: str = ""
    source_date: Optional[str] = None
    subject: Optional[str] = None
    claimed_property: Optional[str] = None
    claimed_value: Any = None
    confidence: float = 0.8
    #: Sources sharing a group are not independent confirmations of each
    #: other. Three papers running one wire story are one group.
    independence_group: Optional[str] = None
    source_kind: str = "secondary"
    reliability: Optional[str] = None

    def __post_init__(self) -> None:
        if self.stance not in STANCES:
            raise ValueError(f"unknown stance '{self.stance}'")
        if self.topic not in TOPICS:
            raise ValueError(f"unknown research topic '{self.topic}'")


@dataclass(frozen=True)
class ResearchResponse:
    """What one provider had to say, including what it could not reach."""

    provider: str
    version: str = "0.1"
    findings: Tuple[Finding, ...] = ()
    #: Topics the provider could not consult a source about at all. Different
    #: from having looked and found nothing, and kept different all the way
    #: through to the epistemic state.
    unreachable: Tuple[str, ...] = ()
    note: str = ""

    def for_topic(self, topic: str) -> List[Finding]:
        return [finding for finding in self.findings if finding.topic == topic]


@runtime_checkable
class ResearchProvider(Protocol):
    """Anything that can answer a research request."""

    #: Recorded on the execution record, so a run can be attributed.
    name: str
    version: str

    def research(self, request: ResearchRequest) -> ResearchResponse:
        """Findings bearing on the request; returning none is a real answer."""


class MockResearchProvider:
    """A fixture: findings prepared in advance, keyed by the target they concern.

    This is what makes investigation testable with no network, no key and no
    vendor. It answers only for targets it was given answers for, and only for
    the topics that were actually asked.
    """

    name = "mock"

    def __init__(
        self,
        findings: Mapping[str, Iterable[Finding]],
        version: str = "0.1",
        unreachable: Optional[Mapping[str, Iterable[str]]] = None,
        name: Optional[str] = None,
    ) -> None:
        self.findings: Dict[str, List[Finding]] = {
            target: list(items) for target, items in findings.items()
        }
        self.unreachable: Dict[str, Tuple[str, ...]] = {
            target: tuple(topics) for target, topics in (unreachable or {}).items()
        }
        self.version = version
        self.asked: List[ResearchRequest] = []
        if name is not None:
            self.name = name

    def research(self, request: ResearchRequest) -> ResearchResponse:
        self.asked.append(request)
        wanted = set(request.topics)
        found = [
            finding
            for finding in self.findings.get(request.target, ())
            if finding.topic in wanted
        ]
        return ResearchResponse(
            provider=self.name,
            version=self.version,
            findings=tuple(found),
            unreachable=tuple(
                topic
                for topic in self.unreachable.get(request.target, ())
                if topic in wanted
            ),
        )


class SilentResearchProvider:
    """Answers nothing, honestly.

    The default when no source is configured, and the way to construct the
    case that matters most: research ran, nothing was found, and the cause of
    the anomaly stays UNKNOWN rather than becoming a plausible story.
    """

    name = "none"
    version = "0.1"

    def research(self, request: ResearchRequest) -> ResearchResponse:
        return ResearchResponse(provider=self.name, version=self.version)


class ChainedResearchProvider:
    """Ask several providers in order and pool what they return.

    Findings are pooled, not merged: if the second provider disagrees with the
    first, both statements survive into the graph and the claim they bear on
    becomes contested.
    """

    def __init__(self, *providers: ResearchProvider) -> None:
        self.providers: Tuple[ResearchProvider, ...] = providers
        self.name = "+".join(provider.name for provider in providers) or "none"
        self.version = "+".join(provider.version for provider in providers) or "0.1"

    def research(self, request: ResearchRequest) -> ResearchResponse:
        findings: List[Finding] = []
        unreachable: List[str] = []
        for provider in self.providers:
            response = provider.research(request)
            findings.extend(response.findings)
            unreachable.extend(response.unreachable)
        answered = {finding.topic for finding in findings}
        return ResearchResponse(
            provider=self.name,
            version=self.version,
            findings=tuple(findings),
            unreachable=tuple(
                sorted({topic for topic in unreachable if topic not in answered})
            ),
        )


def questions_for(
    target: str,
    target_property: Optional[str],
    observed_state: Any,
    expected_state: Any,
    topics: Sequence[str] = TOPICS,
) -> Tuple[Question, ...]:
    """The v0.1 question template: four fixed questions, deterministically worded."""
    subject = f"{target_property} of {target}" if target_property else str(target)
    phrasing = {
        "event_verification": f"Did {subject} really move to {observed_state}?",
        "cause": f"What event or mechanism explains {subject} moving to {observed_state}?",
        "context": (
            f"What surrounding facts help interpret {subject} at {observed_state}"
            f"{'' if expected_state is None else f', against an expected {expected_state}'}?"
        ),
        "alternative": (
            f"Is there another plausible explanation for {subject} at {observed_state}?"
        ),
    }
    return tuple(
        Question(topic=topic, question=phrasing[topic])
        for topic in topics
        if topic in phrasing
    )


__all__ = [
    "ChainedResearchProvider",
    "Finding",
    "MockResearchProvider",
    "Question",
    "ResearchProvider",
    "ResearchRequest",
    "ResearchResponse",
    "SilentResearchProvider",
    "questions_for",
]
