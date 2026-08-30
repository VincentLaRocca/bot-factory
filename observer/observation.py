"""Observations: what was seen, of what, by whom, through what.

An observation is not a fact about the world; it is a fact about a looking.
Two of them can disagree and both be kept, which is only possible if each one
carries its own endpoints — the observer at one end, the observed at the other
— along with the sensor it came through and the independence group that sensor
belongs to.

That last field is the one that looks pointless in v0.1 and is not. Three
observers reading the same wire story are one observation wearing three hats,
and nothing downstream can discover that later if the metadata was never
written down.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Iterable, List, Optional, Sequence

from aiop import AIOPObject, Provenance, State
from aiop.provenance import parse_timestamp, utcnow
from profiles.observer import OBSERVER_CONTEXT
from store import ObjectStore


class SelfObservation(ValueError):
    """Raised when an observation's endpoints are the same thing.

    A component may certainly observe itself, but then the observer is the
    component and the observed is one of its states or sub-components. Letting
    the two ends collapse into one identifier destroys the only structure that
    makes the record interpretable.
    """

    def __init__(self, identifier: str) -> None:
        super().__init__(
            f"'{identifier}' cannot be both observer and observed; "
            "name the observed component or state distinctly"
        )
        self.identifier = identifier


def observe(
    target: str,
    value: Any,
    observer: str,
    target_property: Optional[str] = None,
    sensor: Optional[str] = None,
    independence_group: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    modality: str = "measurement",
    unit: Optional[str] = None,
    confidence: float = 1.0,
    note: Optional[str] = None,
    id: Optional[str] = None,
    context: Any = None,
) -> AIOPObject:
    """Build an Observation object. It is not stored until someone stores it."""
    if target == observer:
        raise SelfObservation(target)
    at = observed_at or utcnow()
    properties = {
        "value": value,
        "observed_at": at.isoformat(),
        "observer": observer,
        "target": target,
        "modality": modality,
        "confidence": confidence,
        "independence_group": independence_group or (sensor or observer),
    }
    if target_property is not None:
        properties["target_property"] = target_property
    if unit is not None:
        properties["unit"] = unit
    if sensor is not None:
        properties["sensor"] = sensor

    observation = AIOPObject(
        id=id or identifier(target, target_property, at, value),
        types=["Observation"],
        context=context if context is not None else list(OBSERVER_CONTEXT),
        state=State.ACTIVE,
        properties=properties,
    )
    observation.attest(
        Provenance(
            agent=observer,
            method=modality,
            source=sensor,
            confidence=confidence,
            generated_at=at,
            note=note,
        )
    )
    observation.relate("about", target)
    observation.relate("observedBy", observer)
    if sensor is not None:
        observation.relate("sensedBy", sensor)
    return observation


def identifier(
    target: str, target_property: Optional[str], at: datetime, value: Any
) -> str:
    """A readable, collision-resistant id for one looking.

    Time alone is not enough — two sensors can report the same instant — so the
    value and property are folded in. The digest is short because it exists to
    disambiguate, not to authenticate.
    """
    digest = hashlib.sha256(
        f"{target}|{target_property}|{at.isoformat()}|{value!r}".encode("utf-8")
    ).hexdigest()[:8]
    stamp = at.strftime("%Y%m%dT%H%M%S")
    part = f"-{target_property}" if target_property else ""
    return f"{target}#observation{part}-{stamp}-{digest}"


def record(store: ObjectStore, observation: AIOPObject) -> AIOPObject:
    """Persist an observation, or return the one already stored under its id."""
    existing = store.find(observation.id)
    if existing is not None:
        return existing
    return store.add(observation)


def observed_at(observation: AIOPObject) -> datetime:
    """When the looking happened, as a comparable value."""
    stamp = observation.get("observed_at")
    if isinstance(stamp, datetime):
        return stamp
    return parse_timestamp(stamp) if stamp else utcnow()


def history(
    store: ObjectStore,
    target: str,
    target_property: Optional[str] = None,
    before: Optional[datetime] = None,
    exclude: Iterable[str] = (),
    states: Sequence[State] = (State.ACTIVE,),
) -> List[AIOPObject]:
    """Every earlier observation of the same thing, oldest first.

    This is the memory the anomaly listener compares against, and it is the
    store's memory rather than the capability's: a listener with private state
    would give a different answer on a second machine.
    """
    skip = set(exclude)
    found: List[AIOPObject] = []
    for relation in store.inbound(target, "about"):
        observation = store.find(relation.subject)
        if observation is None or "Observation" not in observation.types:
            continue
        if observation.id in skip or observation.state not in states:
            continue
        if (
            target_property is not None
            and observation.get("target_property") != target_property
        ):
            continue
        if before is not None and observed_at(observation) >= before:
            continue
        found.append(observation)
    return sorted(found, key=lambda obs: (observed_at(obs), obs.id))


__all__ = [
    "SelfObservation",
    "history",
    "identifier",
    "observe",
    "observed_at",
    "record",
]
