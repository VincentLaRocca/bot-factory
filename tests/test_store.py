"""The store: CRUD, two-way indexing, traversal, and version awareness."""

import pytest

from aiop import AIOPObject, Provenance, State
from profiles import ASYMMETRY_VIEW, CHARACTER_VIEW, VERSION_PREDICATE
from store import (
    Direction,
    DuplicateObject,
    ObjectNotFound,
    ObjectRepository,
    ObjectStore,
    View,
    traverse,
)

SARAH = "urn:aiop:person:sarah"
SCOUT = "urn:aiop:animal:scout"
STORY = "urn:aiop:story:the-long-field"
COMPANY = "urn:aiop:company:harbour-forge"
TECHNOLOGY = "urn:aiop:technology:induction-retrofit"
OPPORTUNITY = "urn:aiop:opportunity:harbour-q2-retrofit"
OPPORTUNITY_V1 = "urn:aiop:opportunity:harbour-q2-retrofit-v1"
FIELD_TRIAL = "urn:aiop:evidence:field-trial"
TEARDOWN = "urn:aiop:evidence:competitor-teardown"
CALCULATION = "urn:aiop:calculation:harbour-q2-expected-value"


# -- storage ----------------------------------------------------------


def test_store_is_a_repository():
    assert isinstance(ObjectStore(), ObjectRepository)


def test_add_get_update_delete_and_enumerate():
    store = ObjectStore()
    obj = AIOPObject(types="Widget", id="urn:aiop:widget:1", properties={"name": "one"})

    assert store.add(obj) is obj
    assert store.get("urn:aiop:widget:1") is obj
    assert store.ids() == ["urn:aiop:widget:1"]
    assert len(store) == 1
    assert "urn:aiop:widget:1" in store

    replacement = AIOPObject(types="Widget", id="urn:aiop:widget:1", properties={"name": "two"})
    store.update(replacement)
    assert store.get("urn:aiop:widget:1").get("name") == "two"

    assert store.delete("urn:aiop:widget:1") is replacement
    assert store.ids() == []


def test_unknown_and_duplicate_identifiers_are_refused():
    store = ObjectStore([AIOPObject(types="Widget", id="urn:aiop:widget:1")])

    with pytest.raises(ObjectNotFound):
        store.get("urn:aiop:widget:404")
    with pytest.raises(DuplicateObject):
        store.add(AIOPObject(types="Widget", id="urn:aiop:widget:1"))
    with pytest.raises(ObjectNotFound):
        store.delete("urn:aiop:widget:404")

    assert store.find("urn:aiop:widget:404") is None


def test_world_loads_and_enumerates(world_store):
    assert len(world_store) == 10
    assert SARAH in world_store.ids()
    assert not world_store.dangling()


def test_objects_can_be_narrowed_by_type_and_state(world_store):
    assert [o.id for o in world_store.objects(types=["Evidence"])] == [
        TEARDOWN,
        FIELD_TRIAL,
    ]
    assert [o.id for o in world_store.objects(states=[State.SUPERSEDED])] == [OPPORTUNITY_V1]


# -- provenance preservation ------------------------------------------


def test_retrieval_returns_the_stored_instance_with_its_provenance(world_store):
    stored = world_store.get(CALCULATION)
    again = world_store.get(CALCULATION)

    assert stored is again
    assert [p.confidence for p in stored.provenance] == [1.0, 0.9]
    assert [p.source for p in stored.provenance] == [OPPORTUNITY, FIELD_TRIAL]
    assert stored.latest_provenance.agent == "urn:aiop:agent:calculator"


def test_provenance_survives_a_store_roundtrip(world_store):
    original = world_store.get(SARAH)
    copy = ObjectStore().load([original.to_jsonld()]).get(SARAH)

    assert [p.to_dict() for p in copy.provenance] == [
        p.to_dict() for p in original.provenance
    ]
    assert copy.to_jsonld() == original.to_jsonld()


def test_attesting_through_the_store_is_visible_everywhere(world_store):
    world_store.get(SCOUT).attest(Provenance(agent="urn:aiop:agent:vet", confidence=0.99))
    assert len(world_store.get(SCOUT).provenance) == 2


# -- indexing ---------------------------------------------------------


def test_relations_are_indexed_in_both_directions(world_store):
    assert [r.object for r in world_store.outbound(SARAH)] == [SCOUT, COMPANY]
    assert [r.subject for r in world_store.inbound(SARAH)] == [STORY]
    assert world_store.referenced_by(SCOUT) == {SARAH}
    assert world_store.inbound(OPPORTUNITY, "supports") == [
        r for r in world_store.outbound(FIELD_TRIAL, "supports")
    ]


def test_the_index_follows_updates_and_deletes(world_store):
    sarah = world_store.get(SARAH)
    without_dog = AIOPObject.from_jsonld(
        {**sarah.to_jsonld(), "relations": [r.to_dict() for r in sarah.relations[1:]]}
    )
    world_store.update(without_dog)
    assert world_store.referenced_by(SCOUT) == set()

    world_store.delete(STORY)
    assert world_store.inbound(SARAH) == []


def test_in_place_relations_are_indexed_after_reindex(world_store):
    world_store.get(SCOUT).relate("portrays", world_store.get(STORY))
    assert world_store.referenced_by(STORY) == set()

    world_store.reindex(SCOUT)
    assert world_store.referenced_by(STORY) == {SCOUT}


# -- traversal --------------------------------------------------------


def test_traversal_runs_in_both_directions(world_store):
    outward = traverse(world_store, SARAH, View(depth=1, direction=Direction.OUT))
    inward = traverse(world_store, SARAH, View(depth=1, direction=Direction.IN))
    both = traverse(world_store, SARAH, View(depth=1, direction=Direction.BOTH))

    assert outward.ids == sorted([SARAH, SCOUT, COMPANY])
    assert inward.ids == sorted([SARAH, STORY])
    assert both.ids == sorted([SARAH, SCOUT, COMPANY, STORY])


def test_depth_limits_constrain_the_walk(world_store):
    view = View(depth=0)
    assert traverse(world_store, OPPORTUNITY, view).ids == [OPPORTUNITY]

    at_one = traverse(world_store, OPPORTUNITY, ASYMMETRY_VIEW.narrow(depth=1))
    assert set(at_one.ids) == {OPPORTUNITY, TECHNOLOGY, FIELD_TRIAL, CALCULATION}

    at_two = traverse(world_store, OPPORTUNITY, ASYMMETRY_VIEW.narrow(depth=2))
    assert COMPANY in at_two.ids and SARAH not in at_two.ids

    at_three = traverse(world_store, OPPORTUNITY, ASYMMETRY_VIEW)
    assert SARAH in at_three.ids
    assert at_three.depth_of(SARAH) == 3
    assert at_three.at_depth(1) == sorted([TECHNOLOGY, FIELD_TRIAL, CALCULATION])


def test_predicate_filters_keep_the_neighbourhoods_apart(world_store):
    narrative = traverse(world_store, SARAH, CHARACTER_VIEW)
    commercial = traverse(world_store, OPPORTUNITY, ASYMMETRY_VIEW)

    assert COMPANY not in narrative.ids
    assert STORY not in commercial.ids and SCOUT not in commercial.ids


def test_type_filters_admit_only_the_wanted_objects(world_store):
    view = View(depth=3, types={"Evidence", "Opportunity", "Technology"})
    walk = traverse(world_store, OPPORTUNITY, view)
    assert set(walk.ids) == {
        OPPORTUNITY,
        OPPORTUNITY_V1,
        TECHNOLOGY,
        FIELD_TRIAL,
        TEARDOWN,
    }
    assert COMPANY not in walk.ids and SARAH not in walk.ids


def test_traversal_records_the_edges_it_crossed(world_store):
    walk = traverse(world_store, SARAH, CHARACTER_VIEW)
    crossed = {(s.relation.predicate, s.direction) for s in walk.steps}
    assert ("owns", Direction.OUT) in crossed
    assert ("contains", Direction.IN) in crossed


def test_traversal_from_an_unknown_object_fails_loudly(world_store):
    with pytest.raises(ObjectNotFound):
        traverse(world_store, "urn:aiop:person:nobody", CHARACTER_VIEW)


def test_a_walk_only_touches_the_objects_it_admits(world_store):
    """Starting from Scout must not drag in the whole graph."""
    reads = []
    original_get = world_store.get
    world_store.get = lambda object_id: (reads.append(object_id), original_get(object_id))[1]
    try:
        walk = traverse(world_store, SCOUT, CHARACTER_VIEW.narrow(depth=1))
    finally:
        del world_store.get

    assert walk.ids == sorted([SCOUT, SARAH])
    assert COMPANY not in reads and OPPORTUNITY not in reads


# -- versions ---------------------------------------------------------


def test_current_excludes_superseded_objects(world_store):
    current = {obj.id for obj in world_store.current()}
    assert OPPORTUNITY in current
    assert OPPORTUNITY_V1 not in current


def test_history_and_latest_follow_the_version_predicate(world_store):
    assert [o.id for o in world_store.history_of(OPPORTUNITY)] == [
        OPPORTUNITY,
        OPPORTUNITY_V1,
    ]
    assert world_store.latest_of(OPPORTUNITY_V1).id == OPPORTUNITY
    assert world_store.latest_of(OPPORTUNITY).id == OPPORTUNITY
    assert world_store.version_predicate == VERSION_PREDICATE


def test_version_queries_need_a_configured_predicate(world_documents):
    store = ObjectStore().load(list(world_documents.values()))
    with pytest.raises(ValueError):
        store.history_of(OPPORTUNITY)


def test_views_can_exclude_superseded_objects(world_store):
    view = View(depth=2, predicates={"supersedes"}, states={State.ACTIVE})
    assert traverse(world_store, OPPORTUNITY, view).ids == [OPPORTUNITY]
    assert OPPORTUNITY_V1 in traverse(
        world_store, OPPORTUNITY, View(depth=2, predicates={"supersedes"})
    ).ids
