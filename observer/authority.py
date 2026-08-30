"""Authority: what an observer is allowed to do, as opposed to able to do.

The whole module exists to make one sentence enforceable:

    Capability does not imply authority.

An observer holds capabilities because someone installed them. It holds
authority because a mission granted it and its own charter allows it. Where
those two disagree, the narrower one wins — which is why the effective grant is
an intersection and never a union.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Sequence, Tuple

from profiles.observer import Permission

PermissionSpec = Iterable["Permission | str"]


def permissions(spec: PermissionSpec) -> FrozenSet[Permission]:
    """Coerce names or members into a set of permissions.

    An unknown name is an error rather than an ignored string: silently
    dropping a permission nobody recognises is how a typo becomes a grant.
    """
    return frozenset(
        item if isinstance(item, Permission) else Permission(item) for item in spec
    )


class Unauthorised(PermissionError):
    """Raised when something is attempted without the authority for it."""

    def __init__(self, action: str, missing: Sequence[Permission]) -> None:
        names = ", ".join(sorted(str(permission) for permission in missing))
        super().__init__(f"'{action}' requires {names}")
        self.action = action
        self.missing: Tuple[Permission, ...] = tuple(missing)


@dataclass(frozen=True)
class Authority:
    """A grant of permissions, and the arithmetic for combining grants."""

    granted: FrozenSet[Permission] = frozenset()

    @classmethod
    def of(cls, *spec: "Permission | str") -> "Authority":
        return cls(permissions(spec))

    @classmethod
    def none(cls) -> "Authority":
        return cls(frozenset())

    def allows(self, permission: "Permission | str") -> bool:
        wanted = permission if isinstance(permission, Permission) else Permission(permission)
        return wanted in self.granted

    def missing(self, required: PermissionSpec) -> Tuple[Permission, ...]:
        """Which of ``required`` this grant does not cover, in a stable order."""
        return tuple(sorted(permissions(required) - self.granted, key=str))

    def require(self, action: str, required: PermissionSpec) -> None:
        absent = self.missing(required)
        if absent:
            raise Unauthorised(action, absent)

    def narrow(self, other: "Authority") -> "Authority":
        """The permissions both grants agree on.

        Composition of authority is intersection, so no combination of an
        observer's charter and a mission's grant can produce a permission
        neither of them held. Privilege cannot be escalated by delegation.
        """
        return Authority(self.granted & other.granted)

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(str(permission) for permission in self.granted))

    def __contains__(self, permission: "Permission | str") -> bool:
        return self.allows(permission)

    def __bool__(self) -> bool:
        return bool(self.granted)

    def __len__(self) -> int:
        return len(self.granted)


#: A charter wide enough to run the demonstrations: everything an observer can
#: do to the graph, and nothing that reaches outside it.
INTERNAL_AUTHORITY = Authority.of(
    Permission.READ,
    Permission.OBSERVE,
    Permission.CREATE_OBJECT,
    Permission.RELATE_OBJECTS,
    Permission.CALCULATE,
    Permission.RECOMMEND,
    Permission.COMMUNICATE_INTERNAL,
)

READ_ONLY_AUTHORITY = Authority.of(Permission.READ, Permission.OBSERVE)

__all__ = [
    "Authority",
    "INTERNAL_AUTHORITY",
    "READ_ONLY_AUTHORITY",
    "Permission",
    "Unauthorised",
    "permissions",
]
