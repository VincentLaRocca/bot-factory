"""The Observer: a motherboard, and deliberately nothing else.

    Agent = Observer + Capabilities + Mission + Authority + Resources

This class is the first term. It knows how to hold an identity, carry a
version, keep a store, accept plug-ins, take a mission, check authority,
invoke a capability and write down what happened. It does not know how to
detect an anomaly, judge an opportunity, browse the web or understand
medicine, and no future capability should teach it.

The proof that the architecture works is negative: adding the anomaly listener
required no change to this file, and there is no ``AnomalyListenerObserver``.

```python
observer = Observer("watchtower", store=store, authority=INTERNAL_AUTHORITY)
observer.install(AnomalyListener())
observer.assign(mission)
observer.invoke("anomaly_listener", inputs=[observation])
```
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from aiop import AIOPObject, Provenance, State
from aiop.provenance import utcnow
from profiles.observer import OBSERVER_CONTEXT, Permission
from store import ObjectStore

from .authority import Authority, PermissionSpec, Unauthorised, permissions
from .capability import (
    CHASSIS_VERSION,
    Capability,
    CapabilityCard,
    CapabilityContext,
    CapabilityOutcome,
    CapabilityRegistry,
)
from .mission import Mission, MissionNotExecutable, Readiness, slug

VERSION = "0.1"

#: Statuses an invocation can end in. ``REFUSED`` is not a failure: it is the
#: system working.
COMPLETE = "COMPLETE"
REFUSED = "REFUSED"
FAILED = "FAILED"


@dataclass
class Invocation:
    """One attempt to use a capability, whether or not it was allowed."""

    observer: str
    capability: str
    status: str
    record: Optional[AIOPObject] = None
    outcome: Optional[CapabilityOutcome] = None
    refusal: str = ""
    missing_capabilities: Tuple[str, ...] = ()
    missing_authority: Tuple[Permission, ...] = ()
    created: Sequence[AIOPObject] = ()
    read: Sequence[str] = ()

    @property
    def refused(self) -> bool:
        return self.status == REFUSED

    @property
    def complete(self) -> bool:
        return self.status == COMPLETE

    @property
    def findings(self) -> Mapping[str, Any]:
        return self.outcome.findings if self.outcome is not None else {}

    def raise_for_status(self) -> "Invocation":
        """Turn a refusal into an exception, for callers that want one."""
        if self.status != REFUSED:
            return self
        if self.missing_capabilities:
            raise MissionNotExecutable(
                Readiness(
                    mission=self.observer,
                    missing_capabilities=self.missing_capabilities,
                )
            )
        raise Unauthorised(self.capability, self.missing_authority)


class Observer:
    """The chassis: identity, slots, a mission, a grant and an audit trail."""

    def __init__(
        self,
        name: str,
        store: ObjectStore,
        authority: Optional[Authority] = None,
        id: Optional[str] = None,
        version: str = VERSION,
        status: str = "ACTIVE",
        context: Any = None,
        chassis: str = CHASSIS_VERSION,
    ) -> None:
        self.name = name
        self.store = store
        self.id = id or f"urn:aiop:observer:{slug(name)}"
        self.version = version
        self.status = status
        self.context = context if context is not None else list(OBSERVER_CONTEXT)
        self.authority = authority if authority is not None else Authority.none()
        self.registry = CapabilityRegistry(chassis=chassis)
        self.mission: Optional[Mission] = None
        self._registered = False

    # -- identity ----------------------------------------------------------
    def describe(self) -> AIOPObject:
        """The observer as an Information Object: who is running, and what of."""
        observer = AIOPObject(
            id=self.id,
            types=["Observer"],
            context=self.context,
            state=State.ACTIVE,
            properties={
                "name": self.name,
                "version": self.version,
                "status": self.status,
                "chassis": self.registry.chassis,
                "authority": list(self.authority.names()),
                "capabilities": self.registry.names(),
            },
        )
        for card in self.registry.cards():
            observer.relate("installed", card.id)
        return observer

    def register(self) -> AIOPObject:
        """Publish the observer and its installed capabilities to the store."""
        self._registered = True
        for card in self.registry.cards():
            self._publish(card)
        existing = self.store.find(self.id)
        described = self.describe()
        if existing is None:
            return self.store.add(described)
        existing.properties.update(described.properties)
        existing.relations = described.relations
        return self.store.reindex(existing.id)

    # -- slots -------------------------------------------------------------
    def install(self, capability: Capability) -> CapabilityCard:
        """Plug a capability in. No subclassing, no chassis change."""
        self.registry.install(capability)
        card = capability.card
        if self._registered:
            self._publish(card)
            self.register()
        return card

    def uninstall(self, capability: str) -> Capability:
        return self.registry.uninstall(capability)

    def capabilities(self) -> List[str]:
        return self.registry.names()

    def cards(self) -> List[CapabilityCard]:
        return self.registry.cards()

    def can(self, capability: str) -> bool:
        return self.registry.has(capability)

    def describe_capability(self, capability: str) -> CapabilityCard:
        return self.registry.get(capability).card

    def _publish(self, card: CapabilityCard) -> AIOPObject:
        published = card.describe(self.context)
        existing = self.store.find(published.id)
        if existing is not None:
            return existing
        published.relate("installedOn", self.id)
        return self.store.add(published)

    # -- purpose -----------------------------------------------------------
    def readiness(self, mission: Mission) -> Readiness:
        """Can this observer run this mission, and if not, exactly why not."""
        required: List[Permission] = []
        for name in mission.required_capabilities:
            capability = self.registry.find(name)
            if capability is not None:
                required.extend(capability.card.requires)
        return Readiness(
            mission=mission.identifier,
            missing_capabilities=self.registry.missing(mission.required_capabilities),
            missing_authority=self.grant(mission).missing(required),
        )

    def grant(self, mission: Optional[Mission] = None) -> Authority:
        """The effective authority: the observer's charter *and* the mission's.

        Intersection, not union. A mission cannot hand out a permission the
        observer was never chartered for, and a chartered observer does not
        get to use a permission the current mission withheld.
        """
        target = mission if mission is not None else self.mission
        if target is None:
            return self.authority
        return self.authority.narrow(target.authority)

    def assign(self, mission: Mission, strict: bool = True) -> Readiness:
        """Take a mission on, refusing it outright if it cannot be run."""
        readiness = self.readiness(mission)
        if strict and not readiness.executable:
            raise MissionNotExecutable(readiness)
        self.mission = mission
        obj = mission.to_object(self.context)
        if self.store.find(obj.id) is None:
            obj.relate("assignedTo", self.id)
            self.store.add(obj)
        return readiness

    def release(self) -> Optional[Mission]:
        mission, self.mission = self.mission, None
        return mission

    # -- work --------------------------------------------------------------
    def invoke(
        self,
        capability: str,
        inputs: Iterable[AIOPObject] = (),
        parameters: Optional[Mapping[str, Any]] = None,
        require: PermissionSpec = (),
    ) -> Invocation:
        """Run an installed capability, if the observer is allowed to.

        Refusals come back as invocations rather than exceptions: a refusal is
        an outcome worth recording, and the record is written either way.
        """
        started = utcnow()
        supplied = tuple(inputs)
        read = [obj.id for obj in supplied]

        plugged = self.registry.find(capability)
        if plugged is None:
            return self._refuse(
                capability=capability,
                started=started,
                read=read,
                refusal=f"capability '{capability}' is not installed",
                missing_capabilities=(capability,),
            )

        card = plugged.card
        authority = self.grant()
        absent = authority.missing(tuple(card.requires) + tuple(permissions(require)))
        if absent:
            return self._refuse(
                capability=capability,
                started=started,
                read=read,
                refusal=(
                    "missing_authority: "
                    + ", ".join(str(permission) for permission in absent)
                ),
                missing_authority=absent,
                card=card,
            )

        unacceptable = [
            obj.id
            for obj in supplied
            if not any(card.accepts_type(type_name) for type_name in obj.types)
        ]
        if unacceptable:
            return self._refuse(
                capability=capability,
                started=started,
                read=read,
                refusal=(
                    f"capability '{capability}' accepts "
                    f"{', '.join(card.accepts)}; got {', '.join(unacceptable)}"
                ),
                card=card,
            )

        context = CapabilityContext(
            observer=self.id,
            observer_version=self.version,
            store=self.store,
            authority=authority,
            inputs=supplied,
            mission=self.store.find(self.mission.identifier) if self.mission else None,
            parameters=dict(parameters or {}),
            now=started,
            context=self.context,
        )

        try:
            outcome = plugged.run(context)
        except Unauthorised as refusal:
            return self._refuse(
                capability=capability,
                started=started,
                read=read,
                refusal=str(refusal),
                missing_authority=refusal.missing,
                card=card,
            )
        except Exception as error:
            self._record(
                capability=capability,
                card=card,
                status=FAILED,
                started=started,
                read=read,
                created=(),
                refusal=f"{type(error).__name__}: {error}",
            )
            raise

        record = self._record(
            capability=capability,
            card=card,
            status=outcome.status,
            started=started,
            read=sorted(dict.fromkeys([*read, *outcome.read])),
            created=outcome.created_ids,
            findings=outcome.findings,
            note=outcome.note,
        )
        return Invocation(
            observer=self.id,
            capability=capability,
            status=outcome.status,
            record=record,
            outcome=outcome,
            created=tuple(outcome.created),
            read=tuple(record.get("inputs_read", ())),
        )

    # -- the audit trail ---------------------------------------------------
    def _refuse(
        self,
        capability: str,
        started: datetime,
        read: Sequence[str],
        refusal: str,
        missing_capabilities: Tuple[str, ...] = (),
        missing_authority: Tuple[Permission, ...] = (),
        card: Optional[CapabilityCard] = None,
    ) -> Invocation:
        record = self._record(
            capability=capability,
            card=card,
            status=REFUSED,
            started=started,
            read=read,
            created=(),
            refusal=refusal,
            missing_capabilities=missing_capabilities,
            missing_authority=missing_authority,
        )
        return Invocation(
            observer=self.id,
            capability=capability,
            status=REFUSED,
            record=record,
            refusal=refusal,
            missing_capabilities=missing_capabilities,
            missing_authority=missing_authority,
            read=tuple(read),
        )

    def _record(
        self,
        capability: str,
        card: Optional[CapabilityCard],
        status: str,
        started: datetime,
        read: Sequence[str],
        created: Sequence[str],
        refusal: str = "",
        findings: Optional[Mapping[str, Any]] = None,
        note: str = "",
        missing_capabilities: Sequence[str] = (),
        missing_authority: Sequence[Permission] = (),
    ) -> AIOPObject:
        """What ran, under whose authority, over what, producing what.

        Conclusions and lineage, never the reasoning's inner monologue: this
        is for reconstructing a decision, not replaying a mind.
        """
        completed = utcnow()
        properties: Dict[str, Any] = {
            "observer": self.id,
            "observer_version": self.version,
            "chassis": self.registry.chassis,
            "invoked": capability,
            "capability_version": card.version if card else None,
            "mission": self.mission.identifier if self.mission else None,
            "authority": list(self.grant().names()),
            "requires": [str(p) for p in (card.requires if card else ())],
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "inputs_read": list(read),
            "objects_created": list(created),
            "status": status,
        }
        if refusal:
            properties["refusal"] = refusal
        if missing_capabilities:
            properties["missing_capabilities"] = list(missing_capabilities)
        if missing_authority:
            properties["missing_authority"] = [str(p) for p in missing_authority]
        if findings:
            properties["findings"] = dict(findings)

        record = AIOPObject(
            id=self._record_id(capability, completed),
            types=["ExecutionRecord"],
            context=self.context,
            state=State.ACTIVE,
            properties=properties,
        )
        record.attest(
            Provenance(
                agent=self.id,
                method="invoked",
                source=capability,
                note=note or refusal or None,
            )
        )
        record.relate("about", self.id)
        if self.mission is not None:
            record.relate("derivedFrom", self.mission.identifier)
        for identifier in read:
            record.relate("derivedFrom", identifier)
        for identifier in created:
            record.relate("produced", identifier)
        return self.store.add(record)

    def _record_id(self, capability: str, at: datetime) -> str:
        base = f"{self.id}#run-{capability}-{at.strftime('%Y%m%dT%H%M%S%f')}"
        candidate, suffix = base, 1
        while self.store.contains(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def records(self) -> List[AIOPObject]:
        """This observer's execution records, oldest first."""
        found = [
            obj
            for obj in self.store.objects(types=["ExecutionRecord"])
            if obj.get("observer") == self.id
        ]
        return sorted(found, key=lambda obj: (obj.get("started_at", ""), obj.id))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Observer(id={self.id!r}, version={self.version!r}, "
            f"capabilities={self.registry.names()!r})"
        )


__all__ = [
    "COMPLETE",
    "FAILED",
    "Invocation",
    "Observer",
    "REFUSED",
    "VERSION",
]
