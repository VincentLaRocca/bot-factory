"""Missions: purpose, written down where someone else can read it.

A mission says what is to be achieved, which capabilities that needs, what the
observer is permitted to do while doing it and when to stop or escalate. It is
an ordinary Information Object, so a mission can be stored, superseded,
audited and pointed at by the execution records of the runs it authorised.

A mission naming a capability the observer does not have is not quietly
degraded into a smaller mission. It is refused, by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aiop import AIOPObject, State
from profiles.observer import OBSERVER_CONTEXT, Permission

from .authority import Authority, PermissionSpec, permissions


@dataclass(frozen=True)
class Mission:
    """What an observer has been asked to do, and how far it may go."""

    objective: str
    required_capabilities: Tuple[str, ...] = ()
    authority: Authority = field(default_factory=Authority.none)
    id: Optional[str] = None
    priority: str = "NORMAL"
    success_conditions: Tuple[str, ...] = ()
    termination_conditions: Tuple[str, ...] = ()
    escalation_conditions: Tuple[str, ...] = ()
    permitted_resources: Tuple[str, ...] = ()
    output_expectations: Tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        objective: str,
        required_capabilities: Iterable[str] = (),
        authority: PermissionSpec = (),
        id: Optional[str] = None,
        priority: str = "NORMAL",
        success_conditions: Iterable[str] = (),
        termination_conditions: Iterable[str] = (),
        escalation_conditions: Iterable[str] = (),
        permitted_resources: Iterable[str] = (),
        output_expectations: Iterable[str] = (),
    ) -> "Mission":
        grant = (
            authority
            if isinstance(authority, Authority)
            else Authority(permissions(authority))
        )
        return cls(
            objective=objective,
            required_capabilities=tuple(required_capabilities),
            authority=grant,
            id=id,
            priority=priority,
            success_conditions=tuple(success_conditions),
            termination_conditions=tuple(termination_conditions),
            escalation_conditions=tuple(escalation_conditions),
            permitted_resources=tuple(permitted_resources),
            output_expectations=tuple(output_expectations),
        )

    @property
    def identifier(self) -> str:
        return self.id or f"urn:aiop:mission:{slug(self.objective)}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "priority": self.priority,
            "required_capabilities": list(self.required_capabilities),
            "authority": list(self.authority.names()),
            "permitted_resources": list(self.permitted_resources),
            "success_conditions": list(self.success_conditions),
            "termination_conditions": list(self.termination_conditions),
            "escalation_conditions": list(self.escalation_conditions),
            "output_expectations": list(self.output_expectations),
        }

    def to_object(self, context: Any = None) -> AIOPObject:
        """The mission as an Information Object, ready to store."""
        return AIOPObject(
            id=self.identifier,
            types=["Mission"],
            context=context if context is not None else list(OBSERVER_CONTEXT),
            state=State.ACTIVE,
            properties=self.to_dict(),
        )

    @classmethod
    def from_object(cls, obj: AIOPObject) -> "Mission":
        """Read a mission back out of the store, grant included."""
        return cls(
            id=obj.id,
            objective=obj.get("objective", ""),
            priority=obj.get("priority", "NORMAL"),
            required_capabilities=tuple(obj.get("required_capabilities", ())),
            authority=Authority(permissions(obj.get("authority", ()))),
            permitted_resources=tuple(obj.get("permitted_resources", ())),
            success_conditions=tuple(obj.get("success_conditions", ())),
            termination_conditions=tuple(obj.get("termination_conditions", ())),
            escalation_conditions=tuple(obj.get("escalation_conditions", ())),
            output_expectations=tuple(obj.get("output_expectations", ())),
        )


@dataclass(frozen=True)
class Readiness:
    """Whether a mission can run at all, and what is stopping it."""

    mission: str
    missing_capabilities: Tuple[str, ...] = ()
    missing_authority: Tuple[Permission, ...] = ()

    @property
    def executable(self) -> bool:
        return not self.missing_capabilities and not self.missing_authority

    @property
    def status(self) -> str:
        return "MISSION_EXECUTABLE" if self.executable else "MISSION_NOT_EXECUTABLE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission": self.mission,
            "status": self.status,
            "missing_capabilities": list(self.missing_capabilities),
            "missing_authority": [str(p) for p in self.missing_authority],
        }

    def explain(self) -> List[str]:
        reasons: List[str] = []
        if self.missing_capabilities:
            reasons.append(
                "missing_capabilities: " + ", ".join(self.missing_capabilities)
            )
        if self.missing_authority:
            reasons.append(
                "missing_authority: "
                + ", ".join(str(p) for p in self.missing_authority)
            )
        return reasons

    def __str__(self) -> str:
        return "\n".join([self.status, *(f"    {r}" for r in self.explain())])


class MissionNotExecutable(RuntimeError):
    """Raised when a mission asks for something the observer has not got.

    Carrying the readiness rather than a message: a caller deciding what to do
    about a missing capability needs its name, not prose.
    """

    def __init__(self, readiness: Readiness) -> None:
        super().__init__(str(readiness))
        self.readiness = readiness

    @property
    def missing_capabilities(self) -> Sequence[str]:
        return self.readiness.missing_capabilities

    @property
    def missing_authority(self) -> Sequence[Permission]:
        return self.readiness.missing_authority


def slug(text: str) -> str:
    """A stable, readable identifier fragment for a mission objective."""
    kept = [character.lower() if character.isalnum() else "-" for character in text]
    return "-".join(part for part in "".join(kept).split("-") if part)[:64] or "mission"


__all__ = [
    "Mission",
    "MissionNotExecutable",
    "Readiness",
    "slug",
]
