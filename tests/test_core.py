import json
from pathlib import Path

import pytest

from conftest import used_terms
from profiles import DEMO_CONTEXT, DEMO_CONTEXT_URI

from aiop import (
    CONTEXT_URI,
    AIOPObject,
    InvalidTransition,
    Provenance,
    ProvenanceChain,
    State,
    StateMachine,
    index,
    new_id,
    normalise_types,
    of_type,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def load_document(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / f"{name}.jsonld").read_text())


def test_new_id_is_unique_and_prefixed():
    first, second = new_id(), new_id()
    assert first != second
    assert first.startswith("urn:aiop:")


def test_object_defaults():
    obj = AIOPObject(types="Person")
    assert obj.state is State.DRAFT
    assert obj.id
    assert obj.properties == {}


def test_property_accessors():
    obj = AIOPObject(types="Person").set("name", "Ada")
    assert obj.get("name") == "Ada"
    assert obj.get("email") is None
    assert "name" in obj
    assert "email" not in obj


# -- types -----------------------------------------------------------


def test_normalise_types_accepts_string_list_or_nothing():
    assert normalise_types("Person") == ["Person"]
    assert normalise_types(["Person", "Agent"]) == ["Person", "Agent"]
    assert normalise_types(["Person", "Person"]) == ["Person"]
    assert normalise_types(None) == []


def test_object_carries_several_types():
    obj = AIOPObject(types=["Dog", "Animal"])
    assert obj.types == ["Dog", "Animal"]
    assert obj.type == "Dog"
    assert obj.has_type("Animal")
    assert not obj.has_type("Person")

    obj.add_type("Pet").add_type("Animal")
    assert obj.types == ["Dog", "Animal", "Pet"]


def test_untyped_object_has_empty_primary_type():
    assert AIOPObject().type == ""
    assert AIOPObject().types == []


def test_type_serialisation_is_scalar_for_one_type_and_array_for_many():
    assert AIOPObject(types=["Story"]).to_jsonld()["@type"] == "Story"
    assert AIOPObject(types=["Dog", "Animal"]).to_jsonld()["@type"] == ["Dog", "Animal"]


def test_type_deserialisation_accepts_scalar_and_array():
    assert AIOPObject.from_jsonld({"@id": "a", "@type": "Story"}).types == ["Story"]
    assert AIOPObject.from_jsonld({"@id": "a", "@type": ["Dog", "Animal"]}).types == [
        "Dog",
        "Animal",
    ]


def test_of_type_matches_any_declared_type(example_objects):
    animals = of_type(example_objects, "Animal")
    assert [o.id for o in animals] == ["urn:aiop:animal:biscuit"]
    assert {o.id for o in of_type(example_objects, "Agent")} == {
        "urn:aiop:person:ada",
        "urn:aiop:company:northwind",
    }


# -- state -----------------------------------------------------------


def test_state_transitions_follow_the_lifecycle():
    obj = AIOPObject(types="Person")
    obj.transition(State.PROPOSED).transition(State.ACTIVE)
    assert obj.state is State.ACTIVE

    with pytest.raises(InvalidTransition):
        obj.transition(State.DRAFT)


def test_retired_is_terminal():
    assert State.RETIRED.is_terminal
    assert not State.ACTIVE.is_terminal
    assert State.ACTIVE.allowed_transitions() == {State.SUPERSEDED, State.RETIRED}


def test_state_machine_records_history():
    machine = StateMachine()
    machine.transition(State.ACTIVE, reason="approved")
    machine.transition(State.SUPERSEDED, reason="replaced by v2")

    assert machine.state is State.SUPERSEDED
    assert [(c.source, c.target) for c in machine.history] == [
        (State.DRAFT, State.ACTIVE),
        (State.ACTIVE, State.SUPERSEDED),
    ]
    assert machine.history[-1].reason == "replaced by v2"


# -- provenance ------------------------------------------------------


def test_provenance_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        Provenance(agent="urn:aiop:agent:x", confidence=1.5)


def test_provenance_chain_orders_records_and_keeps_confidences_separate():
    chain = ProvenanceChain(
        [
            Provenance(agent="b", confidence=0.5, generated_at="2026-02-01T00:00:00Z"),
            Provenance(agent="a", confidence=0.4, generated_at="2026-01-01T00:00:00Z"),
        ]
    )
    assert [r.agent for r in chain] == ["a", "b"]
    assert chain.confidences() == [0.4, 0.5]
    assert chain.latest.agent == "b"
    assert chain.by_agent("a")[0].confidence == 0.4


def test_latest_provenance_on_object():
    obj = AIOPObject(types="Story")
    obj.attest(Provenance(agent="writer", generated_at="2026-02-11T18:40:00Z"))
    obj.attest(Provenance(agent="reviewer", generated_at="2026-02-12T08:05:00Z"))
    assert obj.latest_provenance.agent == "reviewer"


# -- serialisation ---------------------------------------------------


def test_jsonld_roundtrip_preserves_everything():
    document = load_document("person")
    obj = AIOPObject.from_jsonld(document)

    assert obj.id == "urn:aiop:person:ada"
    assert obj.types == ["Person", "Agent"]
    assert obj.state is State.ACTIVE
    assert obj.get("name") == "Ada Okafor"
    assert len(obj.relations) == 3
    assert len(obj.provenance) == 1

    assert AIOPObject.from_jsonld(obj.to_jsonld()).to_jsonld() == obj.to_jsonld()


def test_every_example_roundtrips(example_documents):
    for name, document in example_documents.items():
        obj = AIOPObject.from_jsonld(document)
        assert AIOPObject.from_jsonld(obj.to_jsonld()).to_jsonld() == obj.to_jsonld(), name


def test_to_jsonld_flattens_properties():
    document = AIOPObject(
        types="Dog", id="urn:aiop:animal:x", properties={"name": "Biscuit"}
    ).to_jsonld()
    assert document["@id"] == "urn:aiop:animal:x"
    assert document["@type"] == "Dog"
    assert document["name"] == "Biscuit"
    assert document["state"] == "draft"
    assert "relations" not in document


def test_every_example_loads(example_objects):
    assert len(example_objects) == 8
    by_id = index(example_objects)
    assert "urn:aiop:person:ada" in by_id
    assert by_id["urn:aiop:calculation:northwind-q1-commission"].get("result") == 18000


# -- contexts ---------------------------------------------------------


def test_default_context_is_the_core_context_alone():
    assert AIOPObject(types="Thing").to_jsonld()["@context"] == CONTEXT_URI


def test_examples_compose_the_core_and_profile_contexts(example_documents):
    for name, document in example_documents.items():
        assert document["@context"] == [CONTEXT_URI, DEMO_CONTEXT_URI], name


def test_composed_context_survives_a_roundtrip(example_documents):
    obj = AIOPObject.from_jsonld(example_documents["person"])
    assert obj.context == DEMO_CONTEXT
    assert obj.to_jsonld()["@context"] == DEMO_CONTEXT


def test_every_example_term_resolves_in_the_composed_context(
    example_documents,
    world_documents,
    reasoning_documents,
    core_context,
    profile_context,
):
    """Nothing an example says is left undefined once both contexts are merged."""
    composed = {**core_context, **profile_context}
    for name, document in {
        **example_documents,
        **world_documents,
        **reasoning_documents,
    }.items():
        for term in used_terms(document):
            assert term in composed, f"{name}: '{term}' is defined by neither context"


def test_domain_terms_come_from_the_profile_context_only(core_context, profile_context):
    for term in ("Person", "Dog", "Character", "Story", "Company", "Opportunity", "Calculation"):
        assert term in profile_context
        assert term not in core_context

    envelope = {"state", "relations", "provenance", "confidence", "generatedAt"}
    assert envelope <= set(core_context)
    assert envelope.isdisjoint(profile_context)


# -- Core purity ------------------------------------------------------

DOMAIN_TERMS = (
    "Person",
    "Dog",
    "Animal",
    "Character",
    "Story",
    "Company",
    "Policy",
    "Opportunity",
    "Calculation",
    "owns",
    "employs",
    "portrays",
    "schema.org",
)

#: Words that would betray Core combining evidence rather than recording it.
COMBINATION_TERMS = (
    "joint",
    "product",
    "aggregate",
    "combine",
    "posterior",
    "prior",
    "bayes",
    "likelihood",
    "probability",
)


def core_sources():
    import aiop

    return sorted(Path(aiop.__file__).parent.glob("*.py"))


def test_core_modules_name_no_domain_vocabulary():
    for path in core_sources():
        source = path.read_text()
        for term in DOMAIN_TERMS:
            assert term not in source, f"{path.name} mentions '{term}'"


def test_core_context_defines_no_domain_vocabulary(core_context):
    for term in DOMAIN_TERMS:
        assert term not in core_context, f"the Core context defines '{term}'"
    assert all(not term[0].isupper() for term in core_context if not term.startswith("@")), (
        "the Core context declares a type name"
    )


def test_core_never_combines_confidences():
    """Confidence is recorded per attestation and never folded together."""
    assert not hasattr(ProvenanceChain, "confidence")

    for path in core_sources():
        source = path.read_text().lower()
        for term in COMBINATION_TERMS:
            assert term not in source, f"{path.name} mentions '{term}'"

    import aiop.provenance

    assert "*=" not in Path(aiop.provenance.__file__).read_text()


def test_confidences_are_returned_untouched():
    chain = ProvenanceChain(
        [
            Provenance(agent="a", confidence=0.5, generated_at="2026-01-01T00:00:00Z"),
            Provenance(agent="b", confidence=0.5, generated_at="2026-01-02T00:00:00Z"),
            Provenance(agent="c", confidence=0.5, generated_at="2026-01-03T00:00:00Z"),
        ]
    )
    assert chain.confidences() == [0.5, 0.5, 0.5]
    assert [r.confidence for r in chain] == [0.5, 0.5, 0.5]
