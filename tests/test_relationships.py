import ast
import operator

import pytest

from aiop import AIOPObject, Relation, RelationGraph, Vocabulary, index
from profiles import DEMO_VOCABULARY

STORY = "urn:aiop:story:the-long-walk"
CHARACTER = "urn:aiop:character:the-collie"
DOG = "urn:aiop:animal:biscuit"
PERSON = "urn:aiop:person:ada"
OPPORTUNITY = "urn:aiop:opportunity:northwind-q1-retrofit"
POLICY = "urn:aiop:policy:northwind-commission"
CALCULATION = "urn:aiop:calculation:northwind-q1-commission"

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def evaluate(expression: str, bindings):
    """Evaluate an arithmetic expression against variable bindings."""

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.BinOp):
            return _OPERATORS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return bindings[node.id]
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    return visit(ast.parse(expression, mode="eval"))


def free_variables(expression: str):
    return {
        node.id
        for node in ast.walk(ast.parse(expression, mode="eval"))
        if isinstance(node, ast.Name)
    }


# -- vocabulary and inverses ------------------------------------------


def test_core_has_no_predicates_of_its_own():
    from aiop import EMPTY_VOCABULARY

    assert EMPTY_VOCABULARY.predicates() == set()
    assert EMPTY_VOCABULARY.inverse_of("owns") is None
    assert Relation(subject="a", predicate="owns", object="b").inverse() is None


def test_vocabulary_lookup_is_bidirectional_and_symmetric_aware():
    assert DEMO_VOCABULARY.inverse_of("owns") == "ownedBy"
    assert DEMO_VOCABULARY.inverse_of("ownedBy") == "owns"
    assert DEMO_VOCABULARY.inverse_of("relatedTo") == "relatedTo"
    assert DEMO_VOCABULARY.inverse_of("smells") is None


def test_vocabulary_extend_does_not_mutate_the_original():
    extended = DEMO_VOCABULARY.extend(inverses={"boltedTo": "carries"}, symmetric=["nextTo"])
    assert extended.inverse_of("carries") == "boltedTo"
    assert extended.inverse_of("nextTo") == "nextTo"
    assert DEMO_VOCABULARY.inverse_of("boltedTo") is None


def test_relation_inverse_uses_the_supplied_vocabulary():
    relation = Relation(subject="a", predicate="employs", object="b")
    assert relation.inverse(DEMO_VOCABULARY) == Relation(
        subject="b", predicate="worksFor", object="a"
    )


def test_relate_attaches_outbound_edge_with_attributes():
    ada = AIOPObject(types="Person", id=PERSON)
    biscuit = AIOPObject(types=["Dog", "Animal"], id=DOG)

    relation = ada.relate("owns", biscuit, since="2022-06-01")
    assert relation.subject == ada.id
    assert relation.object == biscuit.id
    assert relation.attributes == {"since": "2022-06-01"}
    assert ada.related("owns") == [biscuit.id]
    assert ada.related("employs") == []


def test_graph_deduplicates_and_adds_inverses():
    graph = RelationGraph(vocabulary=DEMO_VOCABULARY)
    relation = Relation(subject="a", predicate="owns", object="b")
    graph.add(relation, with_inverse=True)
    graph.add(relation, with_inverse=True)

    assert len(graph) == 2
    assert graph.find(subject="b", predicate="ownedBy") == [
        Relation(subject="b", predicate="ownedBy", object="a")
    ]


def test_graph_without_a_vocabulary_implies_nothing():
    graph = RelationGraph()
    graph.add(Relation(subject="a", predicate="owns", object="b"), with_inverse=True)
    assert len(graph) == 1


def test_graph_queries():
    graph = RelationGraph(
        [
            Relation(subject="a", predicate="parentOf", object="b"),
            Relation(subject="b", predicate="parentOf", object="c"),
            Relation(subject="a", predicate="owns", object="d"),
        ],
        vocabulary=DEMO_VOCABULARY,
    )
    assert graph.neighbours("a") == ["b", "d"]
    assert graph.neighbours("a", "parentOf") == ["b"]
    assert graph.reachable("a", "parentOf") == {"b", "c"}
    assert not graph.has_cycle("parentOf")


def test_cycle_detection():
    graph = RelationGraph(
        [
            Relation(subject="a", predicate="contains", object="b"),
            Relation(subject="b", predicate="contains", object="a"),
        ]
    )
    assert graph.has_cycle("contains")


def test_relation_attributes_survive_roundtrip():
    relation = Relation(
        subject="a", predicate="worksFor", object="b", attributes={"role": "CTO"}
    )
    assert Relation.from_dict(relation.to_dict()).attributes == {"role": "CTO"}


# -- Story -> Character -> Dog ----------------------------------------


def test_story_reaches_the_dog_only_through_the_character(example_graph):
    """The story never points at the animal; it points at a Character that does."""
    assert example_graph.find(subject=STORY, object=DOG) == []

    narrative = example_graph.paths(STORY, DOG, predicates={"contains", "portrays"})
    assert len(narrative) == 1
    assert [(r.predicate, r.object) for r in narrative[0]] == [
        ("contains", CHARACTER),
        ("portrays", DOG),
    ]

    # The same animal is also reachable by an entirely separate route.
    assert [(r.predicate, r.object) for r in example_graph.paths(PERSON, DOG)[0]] == [
        ("owns", DOG)
    ]


def test_the_recursive_pattern_is_type_agnostic(example_graph, example_objects):
    """Each hop is an ordinary object holding ordinary relations — no nesting."""
    by_id = index(example_objects)
    node, visited = STORY, [STORY]
    while True:
        onward = [
            r for r in example_graph.find(subject=node) if r.predicate in {"contains", "portrays"}
        ]
        if not onward:
            break
        node = onward[0].object
        visited.append(node)
        assert by_id[node].id == node, "every hop is a first-class addressable object"
        assert by_id[node].types, "every hop declares its own types"

    assert visited == [STORY, CHARACTER, DOG]


def test_the_dog_is_independently_addressable_and_reused(example_graph, example_objects):
    dog = index(example_objects)[DOG]

    assert dog.types == ["Dog", "Animal"]
    assert dog.provenance, "the dog carries its own provenance, not the story's"
    assert example_graph.subjects_referencing(DOG) == {PERSON, CHARACTER}

    story = index(example_objects)[STORY]
    assert DOG not in str(story.properties), "the dog is referenced, never embedded"


def test_character_declares_both_ends_of_the_chain(example_objects):
    character = index(example_objects)[CHARACTER]
    assert character.related("partOf") == [STORY]
    assert character.related("portrays") == [DOG]

    portrayal = next(r for r in character if r.predicate == "portrays")
    assert portrayal.inverse(DEMO_VOCABULARY) == Relation(
        subject=DOG, predicate="portrayedBy", object=CHARACTER
    )


# -- calculation lineage ----------------------------------------------


def test_calculation_draws_on_several_independently_addressable_objects(example_objects):
    by_id = index(example_objects)
    calculation = by_id[CALCULATION]

    sources = {i["source"] for i in calculation.get("inputs")}
    assert sources == {OPPORTUNITY, POLICY}
    assert all(by_id[source].id == source for source in sources)
    assert by_id[OPPORTUNITY].types != by_id[POLICY].types


def test_every_variable_is_bound_to_one_input_and_one_property(example_objects):
    by_id = index(example_objects)
    calculation = by_id[CALCULATION]
    inputs = calculation.get("inputs")

    variables = free_variables(calculation.get("expression"))
    assert variables == {binding["variable"] for binding in inputs}
    assert len(inputs) == len(variables), "no variable may be bound twice"

    for binding in inputs:
        source = by_id[binding["source"]]
        assert binding["sourceProperty"] in source, (
            f"{binding['variable']} names a property the source does not have"
        )
        assert binding["value"] == source.get(binding["sourceProperty"])


def test_lineage_relations_mirror_the_variable_bindings(example_objects):
    calculation = index(example_objects)[CALCULATION]
    edges = [r for r in calculation if r.predicate == "derivedFrom"]

    assert {(r.object, r.attributes["variable"], r.attributes["sourceProperty"]) for r in edges} == {
        (OPPORTUNITY, "opportunity_value", "value"),
        (POLICY, "commission_rate", "rate"),
    }
    for binding in calculation.get("inputs"):
        matches = [r for r in edges if r.attributes["variable"] == binding["variable"]]
        assert len(matches) == 1
        assert matches[0].object == binding["source"]
        assert matches[0].attributes["sourceProperty"] == binding["sourceProperty"]


def test_result_is_reproducible_from_the_sources_alone(example_objects):
    by_id = index(example_objects)
    calculation = by_id[CALCULATION]

    bindings = {
        b["variable"]: by_id[b["source"]].get(b["sourceProperty"])
        for b in calculation.get("inputs")
    }
    assert evaluate(calculation.get("expression"), bindings) == pytest.approx(
        calculation.get("result")
    )


def test_changing_a_source_invalidates_the_cached_result(example_objects):
    by_id = index(example_objects)
    calculation = by_id[CALCULATION]
    by_id[POLICY].set("rate", 0.1)

    bindings = {
        b["variable"]: by_id[b["source"]].get(b["sourceProperty"])
        for b in calculation.get("inputs")
    }
    assert evaluate(calculation.get("expression"), bindings) != calculation.get("result")


def test_provenance_names_every_source(example_objects):
    calculation = index(example_objects)[CALCULATION]
    attested = {record.source for record in calculation.provenance}
    assert attested == {OPPORTUNITY, POLICY}


def test_a_calculation_can_be_assembled_through_core_alone():
    """The lineage pattern needs no domain support from Core."""
    left = AIOPObject(types="Reading", id="urn:aiop:reading:a", properties={"celsius": 20})
    right = AIOPObject(types="Reading", id="urn:aiop:reading:b", properties={"celsius": 26})
    calculation = AIOPObject(
        types="Calculation",
        id="urn:aiop:calculation:mean",
        properties={"expression": "(a + b) / 2", "result": 23},
    )
    for variable, source in (("a", left), ("b", right)):
        calculation.relate("derivedFrom", source, variable=variable, sourceProperty="celsius")

    graph = RelationGraph(calculation.relations, vocabulary=Vocabulary())
    bindings = {
        r.attributes["variable"]: index([left, right])[r.object].get(
            r.attributes["sourceProperty"]
        )
        for r in graph
    }
    assert evaluate(calculation.get("expression"), bindings) == calculation.get("result")
