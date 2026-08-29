import pytest

from aiop import (
    CORE_PROFILE,
    AIOPObject,
    Profile,
    Provenance,
    Relation,
    ValidationError,
    Vocabulary,
    validate_document,
    validate_graph,
    validate_object,
)
from profiles import DEMO_PROFILE

# -- the universal layer ---------------------------------------------


def test_core_validates_the_envelope_only():
    """A domain type Core has never heard of is perfectly valid."""
    result = validate_document(
        {
            "@context": "https://aiop.dev/context.jsonld",
            "@id": "urn:aiop:widget:1",
            "@type": ["Widget", "Thing"],
            "state": "active",
        }
    )
    assert result.is_valid
    assert not result.warnings


def test_core_does_not_require_domain_properties():
    """A Person with no name breaks a profile rule, never a Core rule."""
    document = {"@context": "x", "@id": "urn:aiop:person:a", "@type": "Person"}
    assert validate_document(document).is_valid
    assert not validate_document(document, CORE_PROFILE).errors


def test_missing_identity_is_an_error():
    result = validate_document({"@context": "x", "@type": "Person", "name": "Ada"})
    assert not result
    assert [i.path for i in result.errors] == ["@id"]


def test_missing_type_is_an_error():
    result = validate_document({"@context": "x", "@id": "urn:aiop:person:a"})
    assert [i.path for i in result.errors] == ["@type"]


def test_non_string_types_are_rejected():
    result = validate_document(
        {"@context": "x", "@id": "urn:aiop:person:a", "@type": ["Person", 7]}
    )
    assert any(i.path == "@type" for i in result.errors)


def test_missing_context_is_only_a_warning():
    result = validate_document({"@id": "urn:aiop:person:a", "@type": "Person"})
    assert result.is_valid
    assert [i.path for i in result.warnings] == ["@context"]


def test_unknown_state_is_rejected():
    result = validate_document(
        {"@id": "urn:aiop:person:a", "@type": "Person", "state": "zombie"}
    )
    assert "not a known state" in str(result.errors[0])


def test_relation_and_provenance_payloads_are_checked():
    result = validate_document(
        {
            "@id": "urn:aiop:person:a",
            "@type": "Person",
            "relations": [{"subject": "urn:aiop:person:a", "predicate": "owns"}],
            "provenance": [{"agent": "urn:aiop:agent:x", "confidence": 4}],
        }
    )
    paths = {i.path for i in result.errors}
    assert paths == {"relations[0].object", "provenance[0].confidence"}


def test_validate_object_flags_foreign_relation_subject():
    obj = AIOPObject(types="Person", id="urn:aiop:person:a")
    obj.relations.append(
        Relation(subject="urn:aiop:person:other", predicate="owns", object="urn:aiop:x")
    )
    result = validate_object(obj)
    assert not result.is_valid
    assert "expected 'urn:aiop:person:a'" in result.errors[0].message


def test_untyped_object_is_rejected():
    result = validate_object(AIOPObject(id="urn:aiop:thing:a"))
    assert [i.path for i in result.errors] == ["types"]


def test_missing_provenance_is_a_warning_only():
    result = validate_object(AIOPObject(types="Person", id="urn:aiop:person:a"))
    assert result.is_valid
    assert [i.path for i in result.warnings] == ["provenance"]


# -- the profile layer -----------------------------------------------


def test_profile_supplies_the_domain_rules():
    document = {"@context": "x", "@id": "urn:aiop:opportunity:a", "@type": "Opportunity"}
    assert validate_document(document).is_valid
    assert {i.path for i in validate_document(document, DEMO_PROFILE).errors} == {
        "$.title",
        "$.value",
    }


def test_requirements_accumulate_across_declared_types():
    """A ["Dog", "Animal"] object owes the union of both types' properties."""
    assert DEMO_PROFILE.requirements_for(["Dog"]) == ["breed"]
    assert DEMO_PROFILE.requirements_for(["Dog", "Animal"]) == ["breed", "name"]

    document = {"@context": "x", "@id": "urn:aiop:animal:a", "@type": ["Dog", "Animal"]}
    assert {i.path for i in validate_document(document, DEMO_PROFILE).errors} == {
        "$.breed",
        "$.name",
    }


def test_unknown_types_and_predicates_are_profile_warnings():
    result = validate_document(
        {
            "@context": "x",
            "@id": "urn:aiop:widget:1",
            "@type": "Widget",
            "relations": [
                {"subject": "urn:aiop:widget:1", "predicate": "smells", "object": "b"}
            ],
        },
        DEMO_PROFILE,
    )
    assert result.is_valid
    assert {i.path for i in result.warnings} == {
        "relations[0].predicate",
        "$.@type",
    }


def test_profiles_are_swappable():
    strict = Profile(
        name="strict",
        required_properties={"Widget": ["serial"]},
        vocabulary=Vocabulary(inverses={"boltedTo": "carries"}),
    )
    widget = AIOPObject(types="Widget", id="urn:aiop:widget:1")
    widget.attest(Provenance(agent="urn:aiop:agent:x"))
    widget.relate("boltedTo", "urn:aiop:widget:2")

    result = validate_object(widget, strict)
    assert [i.path for i in result.errors] == ["properties.serial"]
    assert not result.warnings

    widget.set("serial", "W-001")
    assert validate_object(widget, strict).is_valid
    assert validate_object(widget, DEMO_PROFILE).warnings


def test_examples_satisfy_the_demo_profile(example_documents):
    for name, document in example_documents.items():
        result = validate_document(document, DEMO_PROFILE)
        assert result.is_valid, f"{name}: {[str(i) for i in result.errors]}"
        assert not result.warnings, f"{name}: {[str(i) for i in result.warnings]}"


# -- graphs -----------------------------------------------------------


def test_graph_validation_detects_duplicates_and_dangling_references():
    ada = AIOPObject(types="Person", id="urn:aiop:person:a", properties={"name": "Ada"})
    ada.attest(Provenance(agent="urn:aiop:agent:x"))
    ada.relate("owns", "urn:aiop:animal:missing")
    twin = AIOPObject(types="Person", id="urn:aiop:person:a", properties={"name": "Ada"})
    twin.attest(Provenance(agent="urn:aiop:agent:x"))

    result = validate_graph([ada, twin], profile=DEMO_PROFILE)
    assert not result.is_valid
    assert any("duplicate" in i.message for i in result.errors)
    assert any("dangling" in i.message for i in result.warnings)


def test_example_graph_resolves(example_objects):
    result = validate_graph(example_objects, profile=DEMO_PROFILE)
    assert result.is_valid
    assert not result.warnings


def test_raise_for_errors():
    result = validate_document({"@type": "Person"})
    with pytest.raises(ValidationError) as excinfo:
        result.raise_for_errors()
    assert "@id" in str(excinfo.value)
