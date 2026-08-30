"""The Observer motherboard: a chassis capabilities plug into.

    Agent = Observer + Capabilities + Mission + Authority + Resources

Nothing in this package knows a domain. It knows identity, slots, purpose,
permission, and how to write down what happened. Domain intelligence arrives
as a capability — see ``capabilities/`` for the first one — and leaves again
without the chassis noticing.
"""

from .authority import (
    Authority,
    INTERNAL_AUTHORITY,
    Permission,
    READ_ONLY_AUTHORITY,
    Unauthorised,
    permissions,
)
from .capability import (
    CHASSIS_VERSION,
    Capability,
    CapabilityCard,
    CapabilityContext,
    CapabilityError,
    CapabilityNotInstalled,
    CapabilityOutcome,
    CapabilityRegistry,
    DuplicateCapability,
    IncompatibleCapability,
    UnmetDependency,
)
from .core import COMPLETE, FAILED, Invocation, Observer, REFUSED, VERSION
from .mission import Mission, MissionNotExecutable, Readiness
from .observation import SelfObservation, history, observe, observed_at, record
from .sensor import Reading, Sensor, SensorCard, StaticSensor, to_observations

__all__ = [
    "Authority",
    "CHASSIS_VERSION",
    "COMPLETE",
    "Capability",
    "CapabilityCard",
    "CapabilityContext",
    "CapabilityError",
    "CapabilityNotInstalled",
    "CapabilityOutcome",
    "CapabilityRegistry",
    "DuplicateCapability",
    "FAILED",
    "INTERNAL_AUTHORITY",
    "IncompatibleCapability",
    "Invocation",
    "Mission",
    "MissionNotExecutable",
    "Observer",
    "Permission",
    "READ_ONLY_AUTHORITY",
    "REFUSED",
    "Reading",
    "Readiness",
    "SelfObservation",
    "Sensor",
    "SensorCard",
    "StaticSensor",
    "Unauthorised",
    "UnmetDependency",
    "VERSION",
    "history",
    "observe",
    "observed_at",
    "permissions",
    "record",
    "to_observations",
]
