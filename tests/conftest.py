import json
from pathlib import Path
from typing import Dict, List

import pytest

import aiop
from agents.asymmetry import (
    AsymmetryAnalyst,
    ChainedResearchProvider,
    MockResearchProvider,
    StoreResearchProvider,
)
from aiop import AIOPObject, RelationGraph
from profiles import (
    DEMO_CALCULATION_SCHEMA,
    DEMO_CONTEXT_FILE,
    DEMO_FUNCTIONS,
    DEMO_PROFILE,
    DEMO_VOCABULARY,
    VERSION_PREDICATE,
)
from reasoning import ReasoningEngine
from store import ObjectStore

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
WORLD_DIR = EXAMPLES_DIR / "world"
REASONING_DIR = EXAMPLES_DIR / "reasoning"
CORE_CONTEXT_FILE = Path(aiop.__file__).with_name("context.jsonld")

#: Keys the protocol reserves; everything else in a document is vocabulary.
RESERVED = {"@context", "@id", "@type"}


def load_document(name: str) -> Dict:
    return json.loads((EXAMPLES_DIR / f"{name}.jsonld").read_text())


def load_context(path: Path) -> Dict:
    return json.loads(path.read_text())["@context"]


def opaque_terms(context: Dict) -> set:
    """Terms whose values are literal JSON, not more vocabulary."""
    return {
        term
        for term, definition in context.items()
        if isinstance(definition, dict) and definition.get("@type") == "@json"
    }


def used_terms(document: Dict, opaque: set = frozenset()) -> set:
    """Every type, property and predicate name a document relies on."""
    terms = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in RESERVED:
                    terms.add(key)
                if key == "predicate":
                    terms.add(child)
                if key in opaque:
                    continue
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    types = document.get("@type", [])
    terms.update([types] if isinstance(types, str) else types)
    walk(document)
    return terms


@pytest.fixture
def core_context() -> Dict:
    return load_context(CORE_CONTEXT_FILE)


@pytest.fixture
def profile_context() -> Dict:
    return load_context(DEMO_CONTEXT_FILE)


@pytest.fixture
def demo_profile():
    return DEMO_PROFILE


@pytest.fixture
def example_documents() -> Dict[str, Dict]:
    return {
        path.stem: json.loads(path.read_text())
        for path in sorted(EXAMPLES_DIR.glob("*.jsonld"))
    }


@pytest.fixture
def example_objects(example_documents) -> List[AIOPObject]:
    return [AIOPObject.from_jsonld(doc) for doc in example_documents.values()]


@pytest.fixture
def world_documents() -> Dict[str, Dict]:
    """The demonstration world: a story, a company, and what connects them."""
    return {
        path.stem: json.loads(path.read_text())
        for path in sorted(WORLD_DIR.glob("*.jsonld"))
    }


@pytest.fixture
def world_store(world_documents) -> ObjectStore:
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    store.load(list(world_documents.values()))
    return store


@pytest.fixture
def reasoning_documents() -> Dict[str, Dict]:
    """What the reasoning layer adds to the world: a market and a calculation."""
    return {
        path.stem: json.loads(path.read_text())
        for path in sorted(REASONING_DIR.glob("*.jsonld"))
    }


@pytest.fixture
def reasoning_store(world_documents, reasoning_documents) -> ObjectStore:
    """The demonstration world with something worth calculating in it."""
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    store.load(list(world_documents.values()) + list(reasoning_documents.values()))
    return store


@pytest.fixture
def engine(reasoning_store) -> ReasoningEngine:
    return ReasoningEngine(
        reasoning_store, DEMO_FUNCTIONS, DEMO_CALCULATION_SCHEMA
    )


@pytest.fixture
def example_graph(example_objects) -> RelationGraph:
    return RelationGraph(
        (relation for obj in example_objects for relation in obj),
        vocabulary=DEMO_VOCABULARY,
    )


ASYMMETRY_DIR = EXAMPLES_DIR / "asymmetry"


def asymmetry_documents(pattern: str) -> List[Dict]:
    return [json.loads(path.read_text()) for path in sorted(ASYMMETRY_DIR.glob(pattern))]


@pytest.fixture
def asymmetry_store() -> ObjectStore:
    """A deliberately incomplete Human x AI opportunity and its graph."""
    store = ObjectStore(version_predicate=VERSION_PREDICATE)
    store.load(asymmetry_documents("*.jsonld"))
    return store


@pytest.fixture
def available_evidence() -> Dict[str, List[AIOPObject]]:
    """Evidence that exists out in the world, keyed by the dimension it answers."""
    findings: Dict[str, List[AIOPObject]] = {}
    for document in asymmetry_documents("research/*.jsonld"):
        obj = AIOPObject.from_jsonld(document)
        findings.setdefault(obj.get("dimension"), []).append(obj)
    return findings


@pytest.fixture
def late_evidence() -> List[AIOPObject]:
    """Evidence that turns up after the first analysis is already filed."""
    return [
        AIOPObject.from_jsonld(document)
        for document in asymmetry_documents("late/*.jsonld")
    ]


@pytest.fixture
def research(asymmetry_store, available_evidence):
    return ChainedResearchProvider(
        StoreResearchProvider(asymmetry_store),
        MockResearchProvider(available_evidence),
    )


@pytest.fixture
def analyst(asymmetry_store, research):
    return AsymmetryAnalyst(asymmetry_store, research=research)


@pytest.fixture
def blind_analyst(asymmetry_store):
    """An analyst with no research at all: everything unknown stays unknown."""
    return AsymmetryAnalyst(asymmetry_store)


@pytest.fixture
def opportunity_id() -> str:
    return "urn:aiop:opportunity:clinical-triage"
