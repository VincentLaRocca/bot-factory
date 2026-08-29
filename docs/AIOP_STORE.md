# AIOP Object Store + Graph/Cluster Layer v0.1

Core gives us the atom. This layer keeps a collection of atoms, remembers how
they point at one another, and assembles the subset that answers a question.

Core is unchanged by it: `store/` imports `aiop` and nothing of `store` is
imported by Core.

## The invariant

> Objects remain independent. A cluster is a temporary view over objects, not a
> new container that owns or duplicates those objects.

`ObjectCluster` holds a list of identifiers, the view that selected them, the
edges crossed, and a reference to the store. `cluster.objects()` calls
`store.get()` for each identifier, so members are the store's own instances:

```python
cluster.objects()[0] is store.get(cluster.ids[0])   # True
```

A change made through the store is visible through every cluster that includes
the object, because there is only ever one object.

## Storage

`ObjectRepository` is the abstract interface — `add`, `get`, `update`, `delete`,
`ids`, `outbound`, `inbound` — so a database-backed implementation can replace
the in-memory `ObjectStore` without touching a caller. `ObjectStore` adds
convenience on top: `load()` (JSON-LD documents in), `put()` (upsert), `find()`
(`None` rather than raising), `objects(types=..., states=...)`, `dangling()` and
`cluster()`.

Missing identifiers raise `ObjectNotFound`; re-adding one raises
`DuplicateObject` (use `put()` if replacement is what you meant).

Retrieval never copies, re-parses or normalises: the object handed back is the
object that went in, provenance chain and all.

## Relation indexing

`RelationIndex` keeps two adjacency maps, subject→relations and
object→relations, maintained on every write. Inbound traversal therefore costs a
dictionary lookup rather than a scan of the graph — the reason a walk starting
at Scout never has to look at the commercial half of the world.

Relations mutated in place on an object the store already holds are invisible to
the index until `store.reindex(id)`; `update()`/`put()` reindex for you.

## Traversal and views

A `View` is a value object describing a question:

| field                 | meaning                                        |
| --------------------- | ---------------------------------------------- |
| `depth`               | how many hops from the root (0 = the root only) |
| `direction`           | `out`, `in` or `both`                           |
| `predicates`          | allowlist; `None` means every predicate         |
| `exclude_predicates`  | denylist, applied after the allowlist           |
| `types`               | only admit objects declaring one of these       |
| `states`              | only admit objects in one of these states       |

`traverse(store, root, view)` walks breadth-first, admitting the root
unconditionally and expanding only objects the view admits. It returns a
`Traversal`: reached identifiers, their depths, and the `Step`s crossed (each a
relation, the depth at which it was crossed and the direction it was followed
in). Ordering is deterministic — identifiers sorted, edges in canonical order —
so the same world and the same view always yield the same document.

Views are domain vocabulary, so the concrete ones live in the profile:
`profiles/views.py` defines `CHARACTER_VIEW` (narrative neighbourhood),
`ASYMMETRY_VIEW` (the case for an opportunity) and `LINEAGE_VIEW` (what a
calculation consumed). `View.narrow()` and `View.at_depth()` derive tighter
variants without mutating the original.

## Version and state awareness

`store.current()` returns objects in a current state (`draft`, `proposed`,
`active`), leaving `superseded` and `retired` out. A view can do the
same for a walk with `states={State.ACTIVE}`.

Chains of versions are followed through a predicate the application supplies —
`ObjectStore(version_predicate="supersedes")` in the demo profile — because the
word for "replaces" is vocabulary, not protocol. `history_of()` walks from an
object back through what it replaced; `latest_of()` walks forward to the newest.
Without a configured predicate both raise `ValueError` rather than guessing.

## Cluster serialisation

`cluster.to_jsonld()` produces a plain document with no vendor or model state:

```json
{
  "@context": ["https://aiop.dev/context.jsonld", "https://aiop.dev/store/context.jsonld"],
  "@type": "Cluster",
  "members": ["urn:...", "urn:..."],
  "@graph": [ ...full JSON-LD of each member, contexts and provenance intact... ],
  "root": "urn:...",
  "view": {"name": "asymmetry", "depth": 3, "direction": "both", "predicates": [...]},
  "depths": {"urn:...": 0, "urn:...": 1},
  "edges": [{"subject": "...", "predicate": "...", "object": "...", "depth": 1, "direction": "out"}]
}
```

Members are sorted by `@id`, `@graph` follows `members`, edges are in canonical
order and view predicates are sorted, so two assemblies of the same cluster are
byte-identical. `ObjectCluster.from_jsonld(document)` rebuilds the cluster —
into a fresh `ObjectStore` by default, or into one you pass — and re-serialises
to the identical document.
