import json
from pathlib import Path
from typing import Dict, List

import pytest

import aiop
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


def used_terms(document: Dict) -> set:
    """Every type, property and predicate name a document relies on."""
    terms = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in RESERVED:
                    terms.add(key)
                if key == "predicate":
                    terms.add(child)
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
