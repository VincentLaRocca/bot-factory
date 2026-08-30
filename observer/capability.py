"""Capabilities: what an observer can be taught, without being rewritten.

A capability is a plug-in. It carries its own identity, version, input and
output types, the permissions it needs and the dependencies it assumes, and it
is handed everything it may touch through a context object. Nothing about a
capability is discovered by inspecting Python: an observer can be asked what
it can do, and what that would require, before anything is run.

The interface is deliberately tiny — a card and a ``run`` — because every
method the chassis demands is a method every future capability must implement.
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

from aiop import AIOPObject, State
from profiles.observer import OBSERVER_CONTEXT, Permission
from store import ObjectStore

from .authority import Authority, PermissionSpec, permissions

#: The motherboard revision capabilities declare compatibility against.
CHASSIS_VERSION = "0.1"


class CapabilityError(Exception):
    """Base class for the ways a capability can fail to be usable."""


class CapabilityNotInstalled(CapabilityError):
    def __init__(self, capability: str) -> None:
        super().__init__(f"no capability named '{capability}' is installed")
        self.capability = capability


class DuplicateCapability(CapabilityError):
    def __init__(self, capability: str) -> None:
        super().__init__(f"capability '{capability}' is already installed")
        self.capability = capability


class IncompatibleCapability(CapabilityError):
    def __init__(self, capability: str, wanted: Sequence[str], chassis: str) -> None:
        super().__init__(
            f"capability '{capability}' expects observer "
            f"{' or '.join(wanted)}, not {chassis}"
        )
        self.capability = capability


class UnmetDependency(CapabilityError):
    def __init__(self, capability: str, missing: Sequence[str]) -> None:
        super().__init__(
            f"capability '{capability}' depends on {', '.join(sorted(missing))}"
        )
        self.capability = capability
        self.missing: Tuple[str, ...] = tuple(missing)


@dataclass(frozen=True)
class CapabilityCard:
    """Everything the chassis knows about a capability it has never run.

    Self-description is what makes the motherboard generic: the observer does
    not import a capability's module to find out what it needs, it reads the
    card.
    """

    capability: str
    version: str
    description: str
    accepts: Tuple[str, ...] = ()
    produces: Tuple[str, ...] = ()
    requires: Tuple[Permission, ...] = ()
    dependencies: Tuple[str, ...] = ()
    compatible_with: Tuple[str, ...] = (CHASSIS_VERSION,)

    @classmethod
    def build(
        cls,
        capability: str,
        version: str,
        description: str,
        accepts: Iterable[str] = (),
        produces: Iterable[str] = (),
        requires: PermissionSpec = (),
        dependencies: Iterable[str] = (),
        compatible_with: Iterable[str] = (CHASSIS_VERSION,),
    ) -> "CapabilityCard":
        return cls(
            capability=capability,
            version=version,
            description=description,
            accepts=tuple(accepts),
            produces=tuple(produces),
            requires=tuple(sorted(permissions(requires), key=str)),
            dependencies=tuple(dependencies),
            compatible_with=tuple(compatible_with),
        )

    @property
    def id(self) -> str:
        return f"urn:aiop:capability:{self.capability}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "version": self.version,
            "description": self.description,
            "accepts": list(self.accepts),
            "produces": list(self.produces),
            "requires": [str(permission) for permission in self.requires],
            "dependencies": list(self.dependencies),
            "compatible_with": list(self.compatible_with),
        }

    def describe(self, context: Any = None) -> AIOPObject:
        """The card as an ordinary Information Object.

        A capability that cannot be stored cannot be discovered by anything
        except this process, and the point of AIOP is that it should be.
        """
        return AIOPObject(
            id=self.id,
            types=["Capability"],
            context=context if context is not None else list(OBSERVER_CONTEXT),
            state=State.ACTIVE,
            properties=self.to_dict(),
        )

    def missing_authority(self, authority: Authority) -> Tuple[Permission, ...]:
        return authority.missing(self.requires)

    def accepts_type(self, type_name: str) -> bool:
        return not self.accepts or type_name in self.accepts


@runtime_checkable
class Capability(Protocol):
    """A plug-in: a card describing it, and one way to run it."""

    card: CapabilityCard

    def run(self, context: "CapabilityContext") -> "CapabilityOutcome":
        ...


@dataclass(frozen=True)
class CapabilityContext:
    """Everything a capability is allowed to touch, handed to it explicitly.

    Capabilities do not reach for a store, a clock or a permission set of their
    own. If it is not in the context it is not available, which is what makes
    a refusal at the chassis boundary meaningful.
    """

    observer: str
    observer_version: str
    store: ObjectStore
    authority: Authority
    inputs: Tuple[AIOPObject, ...] = ()
    mission: Optional[AIOPObject] = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    now: Optional[datetime] = None
    context: Any = None

    @property
    def input(self) -> AIOPObject:
        """The single input, for capabilities that take exactly one."""
        if len(self.inputs) != 1:
            raise ValueError(f"expected exactly one input, got {len(self.inputs)}")
        return self.inputs[0]

    def require(self, *required: "Permission | str") -> None:
        """Re-check authority from inside the capability.

        The chassis has already checked the card, but a capability that only
        sometimes writes should say so at the moment it writes.
        """
        self.authority.require(self.observer, required)


@dataclass
class CapabilityOutcome:
    """What one invocation produced, in the chassis's vocabulary."""

    status: str = "COMPLETE"
    created: Sequence[AIOPObject] = ()
    read: Sequence[str] = ()
    findings: Mapping[str, Any] = field(default_factory=dict)
    note: str = ""

    @property
    def created_ids(self) -> List[str]:
        return [obj.id for obj in self.created]


class CapabilityRegistry:
    """The observer's slots: what is plugged in, and what that can do."""

    def __init__(self, chassis: str = CHASSIS_VERSION) -> None:
        self.chassis = chassis
        self._installed: Dict[str, Capability] = {}

    def install(self, capability: Capability) -> Capability:
        card = capability.card
        if card.capability in self._installed:
            raise DuplicateCapability(card.capability)
        if card.compatible_with and self.chassis not in card.compatible_with:
            raise IncompatibleCapability(
                card.capability, card.compatible_with, self.chassis
            )
        unmet = [
            dependency
            for dependency in card.dependencies
            if dependency not in self._installed
        ]
        if unmet:
            raise UnmetDependency(card.capability, unmet)
        self._installed[card.capability] = capability
        return capability

    def uninstall(self, capability: str) -> Capability:
        if capability not in self._installed:
            raise CapabilityNotInstalled(capability)
        return self._installed.pop(capability)

    def get(self, capability: str) -> Capability:
        try:
            return self._installed[capability]
        except KeyError:
            raise CapabilityNotInstalled(capability) from None

    def find(self, capability: str) -> Optional[Capability]:
        return self._installed.get(capability)

    def has(self, capability: str) -> bool:
        return capability in self._installed

    def names(self) -> List[str]:
        return sorted(self._installed)

    def cards(self) -> List[CapabilityCard]:
        return [self._installed[name].card for name in self.names()]

    def missing(self, required: Iterable[str]) -> Tuple[str, ...]:
        return tuple(sorted(set(required) - set(self._installed)))

    def accepting(self, type_name: str) -> List[CapabilityCard]:
        return [card for card in self.cards() if card.accepts_type(type_name)]

    def producing(self, type_name: str) -> List[CapabilityCard]:
        return [card for card in self.cards() if type_name in card.produces]

    def __contains__(self, capability: str) -> bool:
        return self.has(capability)

    def __len__(self) -> int:
        return len(self._installed)

    def __iter__(self):
        return iter(self.cards())


__all__ = [
    "CHASSIS_VERSION",
    "Capability",
    "CapabilityCard",
    "CapabilityContext",
    "CapabilityError",
    "CapabilityNotInstalled",
    "CapabilityOutcome",
    "CapabilityRegistry",
    "DuplicateCapability",
    "IncompatibleCapability",
    "UnmetDependency",
]
