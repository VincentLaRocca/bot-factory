"""AIOP Object Store: storage, indexing, traversal and clusters.

Layered above the frozen AIOP Core, and domain-neutral like it: the store knows
about identifiers, edges, depth and lifecycle state, and nothing about what any
of them mean. Concrete views live in a profile.

```python
store = ObjectStore(objects)
cluster = store.cluster("urn:aiop:person:sarah", CHARACTER_VIEW)
cluster.to_json()          # deterministic, hand to anything
```
"""

from .cluster import CLUSTER_CONTEXT_URI, ObjectCluster
from .index import RelationIndex
from .repository import (
    CURRENT_STATES,
    DuplicateObject,
    ObjectNotFound,
    ObjectRepository,
    ObjectStore,
)
from .traversal import Step, Traversal, traverse
from .view import NEIGHBOURHOOD_VIEW, Direction, View

__all__ = [
    "CLUSTER_CONTEXT_URI",
    "CURRENT_STATES",
    "Direction",
    "DuplicateObject",
    "NEIGHBOURHOOD_VIEW",
    "ObjectCluster",
    "ObjectNotFound",
    "ObjectRepository",
    "ObjectStore",
    "RelationIndex",
    "Step",
    "Traversal",
    "View",
    "traverse",
]
