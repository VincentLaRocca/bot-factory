"""The observer application profile: the vocabulary a motherboard runs on.

An ``Observer`` is a chassis, a ``Capability`` is a plug-in, a ``Mission`` is
purpose and a ``Permission`` is control. None of those words belong in Core —
they are how *this* application organises agents — so the names, the required
properties and the permission vocabulary live here, and the observer package
above imports them.

The permission list is deliberately longer than v0.1 implements. Authority is
only meaningful when the vocabulary is wider than the current behaviour: a
permission nobody can yet exercise still says what would have to be granted.
"""

from enum import Enum
from pathlib import Path

from aiop import CONTEXT_URI, Profile, Vocabulary

from .demo import (
    DEMO_CONTEXT_URI,
    DEMO_VOCABULARY,
    REQUIRED_PROPERTIES,
    VERSION_PREDICATE,
)

#: Where this profile publishes its JSON-LD context, and its local copy.
OBSERVER_CONTEXT_URI = "https://aiop.dev/profiles/observer/context.jsonld"
OBSERVER_CONTEXT_FILE = Path(__file__).with_name("observer-context.jsonld")

#: Observer documents compose the envelope, the world and the observer terms.
OBSERVER_CONTEXT = [CONTEXT_URI, DEMO_CONTEXT_URI, OBSERVER_CONTEXT_URI]


class Permission(str, Enum):
    """What an observer may be authorised to do.

    A permission is not a capability: a capability is knowing *how*, a
    permission is being allowed to. An observer can hold a capability whose
    every action it is forbidden to perform, and that combination has to be
    expressible or authority means nothing.
    """

    READ = "READ"
    OBSERVE = "OBSERVE"
    RESEARCH = "RESEARCH"
    CREATE_OBJECT = "CREATE_OBJECT"
    RELATE_OBJECTS = "RELATE_OBJECTS"
    CALCULATE = "CALCULATE"
    VALIDATE = "VALIDATE"
    RECOMMEND = "RECOMMEND"
    SPAWN = "SPAWN"
    COMMUNICATE_INTERNAL = "COMMUNICATE_INTERNAL"
    COMMUNICATE_EXTERNAL = "COMMUNICATE_EXTERNAL"
    TRANSACT = "TRANSACT"

    def __str__(self) -> str:
        return self.value


#: How an observer disposes of an anomaly. Triage, not judgement: the point of
#: a disposition is to decide who looks next, not what it means.
DISPOSITIONS = ("IGNORE", "WATCH", "RESEARCH", "ESCALATE")

#: The world's predicates plus the observer's own: an observation is about a
#: technology a company develops, so both halves have to be sayable at once.
OBSERVER_VOCABULARY = Vocabulary(
    inverses={
        **DEMO_VOCABULARY.inverses,
        "about": "subjectOf",
        "observedBy": "observed",
        "sensedBy": "sensed",
        "detectedBy": "detected",
        "comparedWith": "comparedBy",
        "assignedTo": "assigned",
        "installedOn": "installed",
        "derivedFrom": "sourceOf",
        "produced": "producedBy",
        "supersedes": "supersededBy",
    },
    symmetric=frozenset(DEMO_VOCABULARY.symmetric),
)

#: What each observer type must carry to be worth storing. An observation that
#: does not say what it observed, or when, cannot be compared with anything;
#: an anomaly that does not carry its score cannot be argued with.
OBSERVER_REQUIRED_PROPERTIES = {
    "Observer": ["name", "version", "status"],
    "Capability": ["capability", "version", "requires"],
    "Mission": ["objective", "required_capabilities", "authority"],
    "Sensor": ["name", "independence_group"],
    "Observation": ["value", "observed_at"],
    "Anomaly": ["score", "disposition", "dimensions"],
    "ExecutionRecord": ["observer", "status", "started_at"],
}

OBSERVER_PROFILE = Profile(
    name="observer",
    required_properties={**REQUIRED_PROPERTIES, **OBSERVER_REQUIRED_PROPERTIES},
    known_types=set(REQUIRED_PROPERTIES) | set(OBSERVER_REQUIRED_PROPERTIES),
    vocabulary=OBSERVER_VOCABULARY,
)

__all__ = [
    "DISPOSITIONS",
    "OBSERVER_CONTEXT",
    "OBSERVER_CONTEXT_FILE",
    "OBSERVER_CONTEXT_URI",
    "OBSERVER_PROFILE",
    "OBSERVER_REQUIRED_PROPERTIES",
    "OBSERVER_VOCABULARY",
    "Permission",
    "VERSION_PREDICATE",
]
