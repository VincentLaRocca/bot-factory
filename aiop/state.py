"""Lifecycle state for AIOP objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Set

from .provenance import utcnow


class State(str, Enum):
    """The lifecycle stages an object may occupy."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"

    def allowed_transitions(self) -> Set["State"]:
        return set(TRANSITIONS[self])

    def can_transition_to(self, target: "State") -> bool:
        return target in TRANSITIONS[self]

    def transition_to(self, target: "State") -> "State":
        if not self.can_transition_to(target):
            raise InvalidTransition(self, target)
        return target

    @property
    def is_terminal(self) -> bool:
        return not TRANSITIONS[self]


TRANSITIONS: Dict[State, Set[State]] = {
    State.DRAFT: {State.PROPOSED, State.ACTIVE, State.RETIRED},
    State.PROPOSED: {State.ACTIVE, State.DRAFT, State.RETIRED},
    State.ACTIVE: {State.SUPERSEDED, State.RETIRED},
    State.SUPERSEDED: {State.RETIRED},
    State.RETIRED: set(),
}


class InvalidTransition(ValueError):
    """Raised when a lifecycle transition is not permitted."""

    def __init__(self, source: State, target: State) -> None:
        super().__init__(f"cannot transition from '{source.value}' to '{target.value}'")
        self.source = source
        self.target = target


@dataclass(frozen=True)
class StateChange:
    source: State
    target: State
    at: datetime = field(default_factory=utcnow)
    reason: str = ""


class StateMachine:
    """Tracks a state plus the audit trail of how it got there."""

    def __init__(self, state: State = State.DRAFT) -> None:
        self._state = state
        self._history: List[StateChange] = []

    @property
    def state(self) -> State:
        return self._state

    @property
    def history(self) -> List[StateChange]:
        return list(self._history)

    def transition(self, target: State, reason: str = "") -> State:
        source = self._state
        self._state = source.transition_to(target)
        self._history.append(StateChange(source=source, target=target, reason=reason))
        return self._state
