"""Clusters: assembly around a question, non-ownership, and serialisation."""

import json

import pytest

from aiop import AIOPObject
from profiles import ASYMMETRY_VIEW, CHARACTER_VIEW, LINEAGE_VIEW
from store import CLUSTER_CONTEXT_URI, Direction, ObjectCluster, ObjectStore, View

SARAH = "urn:aiop:person:sarah"
SCOUT = "urn:aiop:animal:scout"
STORY = "urn:aiop:story:the-long-field"
COMPANY = "urn:aiop:company:harbour-forge"
TECHNOLOGY = "urn:aiop:technology:induction-retrofit"
OPPORTUNITY = "urn:aiop:opportunity:harbour-q2-retrofit"
FIELD_TRIAL = "urn:aiop:evidence:field-trial"
TEARDOWN = "urn:aiop:evidence:competitor-teardown"
CALCULATION = "urn:aiop:calculation:harbour-q2-expected-value"


# -- the required demonstrations --------------------------------------


def test_character_view_from_sarah_returns_the_story_cluster(world_store):
    cluster = world_store.cluster(SARAH, CHARACTER_VIEW)

    assert set(cluster.ids) == {SARAH, STORY, SCOUT}
    assert cluster.depth_of(STORY) == 1 and cluster.depth_of(SCOUT) == 1
    assert [o.id for o in cluster.of_type("Character")] == [SARAH]
    assert COMPANY not in cluster and OPPORTUNITY not in cluster


def test_asymmetry_view_from_the_opportunity_returns_the_case_for_it(world_store):
    cluster = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW)

    assert set(cluster.ids) == {
        OPPORTUNITY,
        TECHNOLOGY,
        COMPANY,
        SARAH,
        FIELD_TRIAL,
        TEARDOWN,
        CALCULATION,
    }
    assert {o.id for o in cluster.of_type("Evidence")} == {FIELD_TRIAL, TEARDOWN}
    assert [o.id for o in cluster.of_type("Calculation")] == [CALCULATION]
    assert STORY not in cluster and SCOUT not in cluster


def test_a_cluster_around_scout_stays_small(world_store):
    cluster = world_store.cluster(SCOUT, CHARACTER_VIEW.narrow(depth=1))

    assert set(cluster.ids) == {SCOUT, SARAH}
    assert len(cluster) < len(world_store)


def test_depth_limits_constrain_the_cluster(world_store):
    assert world_store.cluster(SARAH, CHARACTER_VIEW.narrow(depth=0)).ids == [SARAH]

    wide = world_store.cluster(SCOUT, CHARACTER_VIEW.narrow(depth=2))
    assert set(wide.ids) == {SCOUT, SARAH, STORY}
    assert wide.depth_of(STORY) == 2


def test_clusters_reach_in_both_directions(world_store):
    cluster = world_store.cluster(SARAH, CHARACTER_VIEW)
    directions = {step.direction for step in cluster.steps}
    assert directions == {Direction.OUT, Direction.IN}


def test_lineage_view_finds_what_a_calculation_consumed(world_store):
    cluster = world_store.cluster(CALCULATION, LINEAGE_VIEW)

    assert set(cluster.ids) == {CALCULATION, OPPORTUNITY, FIELD_TRIAL}
    bindings = {
        step.relation.attributes["variable"]: step.relation.object for step in cluster.steps
    }
    assert bindings == {"opportunity_value": OPPORTUNITY, "conversion_rate": FIELD_TRIAL}


# -- objects keep their identity and provenance -----------------------


def test_a_cluster_borrows_objects_rather_than_owning_them(world_store):
    cluster = world_store.cluster(SARAH, CHARACTER_VIEW)

    for obj in cluster:
        assert obj is world_store.get(obj.id)

    world_store.get(SCOUT).set("name", "Scout II")
    assert cluster.store.get(SCOUT).get("name") == "Scout II"
    assert [o.get("name") for o in cluster.of_type("Dog")] == ["Scout II"]


def test_one_object_serves_several_clusters(world_store):
    narrative = world_store.cluster(SARAH, CHARACTER_VIEW)
    commercial = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW)

    assert narrative.store.get(SARAH) is commercial.store.get(SARAH)
    assert len(world_store) == 10  # assembling clusters stored nothing new


def test_cluster_members_keep_their_provenance(world_store):
    cluster = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW)

    for obj in cluster:
        assert obj.provenance, f"{obj.id} lost its provenance"
    calculation = cluster.store.get(CALCULATION)
    assert [p.confidence for p in calculation.provenance] == [1.0, 0.9]


def test_expanding_a_cluster_leaves_the_original_alone(world_store):
    narrow = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW.narrow(depth=1))
    wide = narrow.expand(ASYMMETRY_VIEW)

    assert len(narrow) == 4
    assert len(wide) == 7
    assert narrow.view.depth == 1


# -- serialisation ----------------------------------------------------


def test_cluster_serialisation_is_deterministic(world_store):
    cluster = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW)

    assert cluster.to_json() == world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW).to_json()
    document = cluster.to_jsonld()
    assert document["members"] == sorted(document["members"])
    assert [member["@id"] for member in document["@graph"]] == document["members"]
    assert document["@context"][-1] == CLUSTER_CONTEXT_URI
    assert json.loads(cluster.to_json()) == document


def test_a_cluster_survives_a_roundtrip_without_a_store(world_store):
    original = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW)
    document = original.to_jsonld()

    rebuilt = ObjectCluster.from_jsonld(json.loads(json.dumps(document)))

    assert rebuilt.to_jsonld() == document
    assert rebuilt.ids == original.ids
    assert rebuilt.root == original.root
    assert rebuilt.view == original.view
    assert rebuilt.steps == original.steps
    assert isinstance(rebuilt.store, ObjectStore)
    assert len(rebuilt.store) == len(original)


def test_roundtripped_objects_are_unchanged(world_store):
    original = world_store.cluster(OPPORTUNITY, ASYMMETRY_VIEW)
    rebuilt = ObjectCluster.from_jsonld(original.to_jsonld())

    for before, after in zip(original.objects(), rebuilt.objects()):
        assert after.to_jsonld() == before.to_jsonld()
        assert [p.to_dict() for p in after.provenance] == [
            p.to_dict() for p in before.provenance
        ]
        assert after.state is before.state
        assert after.types == before.types


def test_a_cluster_can_be_rehydrated_into_an_existing_store(world_store):
    document = world_store.cluster(CALCULATION, LINEAGE_VIEW).to_jsonld()

    target = ObjectStore()
    rebuilt = ObjectCluster.from_jsonld(document, store=target)

    assert rebuilt.store is target
    assert target.ids() == sorted(rebuilt.ids)
    assert target.outbound(CALCULATION, "derivedFrom")


def test_an_explicit_selection_is_also_a_cluster(world_store):
    cluster = ObjectCluster.of(world_store, [SCOUT, SARAH], name="hand-picked")

    assert cluster.ids == sorted([SARAH, SCOUT])
    assert cluster.root is None
    assert cluster.to_jsonld()["view"]["name"] == "hand-picked"
    with pytest.raises(ValueError):
        cluster.expand(CHARACTER_VIEW)


def test_view_specifications_roundtrip():
    assert View.from_dict(ASYMMETRY_VIEW.to_dict()) == ASYMMETRY_VIEW
    assert View.from_dict(CHARACTER_VIEW.to_dict()) == CHARACTER_VIEW
    assert View(depth=1).to_dict() == {"name": "view", "depth": 1, "direction": "both"}
    with pytest.raises(ValueError):
        View(depth=-1)


def test_a_serialised_cluster_carries_no_vendor_state(world_store):
    document = world_store.cluster(SARAH, CHARACTER_VIEW).to_jsonld()

    assert set(document) == {"@context", "@type", "members", "@graph", "root", "view", "depths", "edges"}
    assert all(isinstance(member, dict) for member in document["@graph"])
    assert AIOPObject.from_jsonld(document["@graph"][0]).id in document["members"]
