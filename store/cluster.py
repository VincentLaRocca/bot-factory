"""Clusters: a temporary view over stored objects.

A cluster owns nothing. It holds identifiers, the view that selected them and
the edges that were crossed; the objects themselves stay in the store, and are
resolved on every access. Two consequences worth stating plainly: an object in
three clusters is one object, and editing it through the store is immediately
visible in all three.

Serialisation is deterministic — members sorted by ``@id``, edges and depths in
a fixed order, no timestamps and no vendor state — so the same cluster handed
to any model or to plain Python is byte-identical.
"""

from __future__ import annotations

import json
from typing import Dict, Iterator, List, Optional, Sequence

from aiop import CONTEXT_URI, AIOPObject, Relation

from .traversal import Step, Traversal, traverse
from .view import Direction, View

#: The context defining the cluster envelope itself (see store/context.jsonld).
CLUSTER_CONTEXT_URI = "https://aiop.dev/store/context.jsonld"


def _step_order(step: Step):
    """The canonical order of crossed edges: nearest first, then lexical."""
    return (
        step.depth,
        step.relation.subject,
        step.relation.predicate,
        step.relation.object,
        step.direction.value,
    )


class ObjectCluster:
    """A named, ordered set of object identifiers resolved against a store."""

    def __init__(
        self,
        store,
        ids: Sequence[str],
        root: Optional[str] = None,
        view: Optional[View] = None,
        steps: Sequence[Step] = (),
        depths: Optional[Dict[str, int]] = None,
    ) -> None:
        self.store = store
        self.root = root
        self.view = view
        self._ids: List[str] = sorted(dict.fromkeys(ids))
        self._steps: List[Step] = sorted(steps, key=_step_order)
        self._depths: Dict[str, int] = dict(depths or {})

    # -- assembly -------------------------------------------------------
    @classmethod
    def assemble(cls, store, root: str, view: View) -> "ObjectCluster":
        """Gather the neighbourhood of ``root`` that ``view`` describes."""
        walk = traverse(store, root, view)
        return cls(
            store=store,
            ids=walk.ids,
            root=root,
            view=view,
            steps=walk.steps,
            depths=walk.depths,
        )

    @classmethod
    def of(cls, store, ids: Sequence[str], name: str = "selection") -> "ObjectCluster":
        """A cluster over an explicit set of identifiers."""
        return cls(store=store, ids=ids, view=View(name=name, depth=0))

    # -- membership -----------------------------------------------------
    @property
    def ids(self) -> List[str]:
        return list(self._ids)

    def __len__(self) -> int:
        return len(self._ids)

    def __contains__(self, object_id: str) -> bool:
        return object_id in self._ids

    def __iter__(self) -> Iterator[AIOPObject]:
        return iter(self.objects())

    def objects(self) -> List[AIOPObject]:
        """The stored instances themselves — not copies of them."""
        return [self.store.get(object_id) for object_id in self._ids]

    def of_type(self, name: str) -> List[AIOPObject]:
        return [obj for obj in self.objects() if obj.has_type(name)]

    def depth_of(self, object_id: str) -> Optional[int]:
        return self._depths.get(object_id)

    def at_depth(self, depth: int) -> List[str]:
        return sorted(i for i, d in self._depths.items() if d == depth)

    @property
    def steps(self) -> List[Step]:
        return list(self._steps)

    @property
    def relations(self) -> List[Relation]:
        return [step.relation for step in self._steps]

    @property
    def traversal(self) -> Traversal:
        return Traversal(root=self.root or "", depths=dict(self._depths), steps=tuple(self._steps))

    def expand(self, view: View) -> "ObjectCluster":
        """A wider cluster around the same root; this one is unchanged."""
        if self.root is None:
            raise ValueError("a rootless cluster cannot be expanded")
        return ObjectCluster.assemble(self.store, self.root, view)

    # -- serialisation --------------------------------------------------
    def to_jsonld(self) -> dict:
        """A deterministic JSON-LD document describing the cluster."""
        members = self.objects()
        document = {
            "@context": [CONTEXT_URI, CLUSTER_CONTEXT_URI],
            "@type": "Cluster",
            "members": list(self._ids),
            "@graph": [obj.to_jsonld() for obj in members],
        }
        if self.root is not None:
            document["root"] = self.root
        if self.view is not None:
            document["view"] = self.view.to_dict()
        if self._depths:
            document["depths"] = {i: self._depths[i] for i in sorted(self._depths)}
        if self._steps:
            document["edges"] = [
                {
                    **step.relation.to_dict(),
                    "depth": step.depth,
                    "direction": step.direction.value,
                }
                for step in self._steps
            ]
        return document

    def to_json(self, indent: Optional[int] = 2) -> str:
        """The same document as text, with keys in a stable order."""
        return json.dumps(self.to_jsonld(), indent=indent, sort_keys=True)

    @classmethod
    def from_jsonld(cls, document: dict, store=None) -> "ObjectCluster":
        """Rebuild a cluster, hydrating its members into ``store``.

        Without a store one is created, so a serialised cluster is a complete,
        self-contained hand-off.
        """
        if store is None:
            from .repository import ObjectStore

            store = ObjectStore()
        for member in document.get("@graph", []):
            store.put(AIOPObject.from_jsonld(member))

        steps = [
            Step(
                relation=Relation.from_dict(edge),
                depth=edge["depth"],
                direction=Direction(edge["direction"]),
            )
            for edge in document.get("edges", [])
        ]
        return cls(
            store=store,
            ids=document.get("members", []),
            root=document.get("root"),
            view=View.from_dict(document["view"]) if "view" in document else None,
            steps=steps,
            depths=document.get("depths", {}),
        )
