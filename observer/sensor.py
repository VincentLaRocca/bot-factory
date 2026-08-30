"""Sensors: where information enters, as distinct from what is done with it.

A sensor reaches a Space — a feed, an inbox, a price tape — and returns
readings. A capability reasons about what the readings mean. Keeping the two
apart is what lets an anomaly listener written against a price feed run
unchanged against a publication feed.

Nothing here goes near a network. v0.1 ships one sensor that reads a list it
was handed, which is enough to prove the shape without pretending to a live
system that has not been built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, runtime_checkable

from aiop import AIOPObject, State
from profiles.observer import OBSERVER_CONTEXT

from . import observation as observation_module


@dataclass(frozen=True)
class Reading:
    """One thing a sensor saw, before any observer has interpreted it."""

    target: str
    value: Any
    target_property: Optional[str] = None
    observed_at: Optional[datetime] = None
    unit: Optional[str] = None
    confidence: float = 1.0
    note: Optional[str] = None


@dataclass(frozen=True)
class SensorCard:
    """A sensor's self-description, in the same spirit as a capability card."""

    sensor: str
    name: str
    modality: str = "measurement"
    #: Readings sharing a group are not independent evidence of each other.
    independence_group: Optional[str] = None
    description: str = ""

    @property
    def id(self) -> str:
        return f"urn:aiop:sensor:{self.sensor}"

    @property
    def group(self) -> str:
        return self.independence_group or self.sensor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "sensor": self.sensor,
            "modality": self.modality,
            "independence_group": self.group,
            "description": self.description,
        }

    def describe(self, context: Any = None) -> AIOPObject:
        return AIOPObject(
            id=self.id,
            types=["Sensor"],
            context=context if context is not None else list(OBSERVER_CONTEXT),
            state=State.ACTIVE,
            properties=self.to_dict(),
        )


@runtime_checkable
class Sensor(Protocol):
    """Anything that can be asked what it currently sees."""

    card: SensorCard

    def sense(self) -> Sequence[Reading]:
        ...


@dataclass
class StaticSensor:
    """A sensor over a fixed list of readings: deterministic, offline, honest."""

    card: SensorCard
    readings: Sequence[Reading] = field(default_factory=tuple)

    def sense(self) -> Sequence[Reading]:
        return tuple(self.readings)


def to_observations(
    sensor: Sensor,
    observer: str,
    readings: Optional[Iterable[Reading]] = None,
    context: Any = None,
) -> List[AIOPObject]:
    """Turn what a sensor saw into observations attributed to an observer."""
    card = sensor.card
    return [
        observation_module.observe(
            target=reading.target,
            value=reading.value,
            observer=observer,
            target_property=reading.target_property,
            sensor=card.id,
            independence_group=card.group,
            observed_at=reading.observed_at,
            modality=card.modality,
            unit=reading.unit,
            confidence=reading.confidence,
            note=reading.note,
            context=context,
        )
        for reading in (sensor.sense() if readings is None else readings)
    ]


__all__ = [
    "Reading",
    "Sensor",
    "SensorCard",
    "StaticSensor",
    "to_observations",
]
