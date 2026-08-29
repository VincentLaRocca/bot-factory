"""The reasoning engine: evaluate a calculation, keep its results honest.

Evaluating a calculation produces an ordinary Information Object. It has its
own identity, its own provenance and its own place in the store, and it draws a
derivation edge to every object it read, carrying the variable and property it
took from each. Nothing about the result is special-cased by the store: a
conclusion is a first-class citizen of the graph, which is the whole point.

Recomputation never edits a result. It writes a new one that supersedes the
old, so the store's existing version machinery gives the history of a
conclusion for free.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from aiop import AIOPObject, Provenance, State
from store import ObjectStore

from . import staleness
from .binding import ResolvedBinding
from .calculation import (
    Calculation,
    CalculationSchema,
    fingerprint,
    input_snapshot,
    is_result,
)
from .functions import FunctionRegistry

DEFAULT_AGENT = "urn:aiop:agent:reasoning-engine"


class ReasoningEngine:
    """Runs calculations against a store and keeps their results current."""

    def __init__(
        self,
        store: ObjectStore,
        registry: FunctionRegistry,
        schema: CalculationSchema,
        agent: str = DEFAULT_AGENT,
    ) -> None:
        self.store = store
        self.registry = registry
        self.schema = schema
        self.agent = agent

    # -- reading calculations -------------------------------------------
    def calculation(self, calculation_id: str) -> Calculation:
        return Calculation(self.store.get(calculation_id), self.schema)

    # -- evaluation ------------------------------------------------------
    def evaluate(
        self,
        calculation_id: str,
        state: State = State.ACTIVE,
        reuse: bool = True,
    ) -> AIOPObject:
        """Compute a calculation and store the result as a new object.

        Re-evaluating an unchanged calculation is idempotent by default: the
        inputs fingerprint to the same digest, so the standing result is
        returned rather than a duplicate of it written.
        """
        calculation = self.calculation(calculation_id)
        resolved = calculation.resolve(self.store)
        function = self.registry.get(calculation.function_name)
        value = function.apply({item.variable: item.value for item in resolved})
        digest = fingerprint(calculation.function_name, resolved)

        if reuse:
            standing = self.current_result(calculation_id)
            if standing is not None and standing.get(
                self.schema.fingerprint_property
            ) == digest:
                return standing

        result = self._result_object(calculation, resolved, value, digest, state)
        return self.store.add(result)

    def _result_id(self, calculation_id: str, digest: str) -> str:
        base = f"{calculation_id}#result-{digest[:12]}"
        candidate, attempt = base, 1
        while self.store.contains(candidate):
            attempt += 1
            candidate = f"{base}-{attempt}"
        return candidate

    def _result_object(
        self,
        calculation: Calculation,
        resolved: Sequence[ResolvedBinding],
        value: object,
        digest: str,
        state: State,
    ) -> AIOPObject:
        schema = self.schema
        result = AIOPObject(
            id=self._result_id(calculation.id, digest),
            types=[schema.result_type],
            context=calculation.object.context,
            state=state,
            properties={
                schema.value_property: value,
                schema.function_property: calculation.function_name,
                schema.calculation_property: calculation.id,
                schema.fingerprint_property: digest,
                schema.inputs_property: input_snapshot(resolved, schema),
            },
        )
        result.attest(
            Provenance(
                agent=self.agent,
                method="calculated",
                source=calculation.id,
                note=f"{calculation.function_name} over {len(resolved)} declared inputs",
            )
        )
        result.relate(schema.derivation_predicate, calculation.id)
        for item in resolved:
            result.relate(
                schema.derivation_predicate,
                item.binding.source,
                **{
                    schema.variable_key: item.variable,
                    schema.source_property_key: item.binding.source_property,
                },
            )
        return result

    # -- looking results up ----------------------------------------------
    def results_of(self, calculation_id: str) -> List[AIOPObject]:
        """Every result this calculation has produced, newest first."""
        derived = [
            self.store.get(relation.subject)
            for relation in self.store.inbound(
                calculation_id, self.schema.derivation_predicate
            )
            if self.store.contains(relation.subject)
        ]
        results = [obj for obj in derived if is_result(obj, self.schema)]
        latest = self.current_result(calculation_id)
        if latest is None:
            return sorted(results, key=lambda obj: obj.id)
        return self.store.history_of(latest.id)

    def current_result(self, calculation_id: str) -> Optional[AIOPObject]:
        """The result that has not been superseded, if there is one."""
        live = [
            self.store.get(relation.subject)
            for relation in self.store.inbound(
                calculation_id, self.schema.derivation_predicate
            )
            if self.store.contains(relation.subject)
        ]
        current = sorted(
            (
                obj
                for obj in live
                if is_result(obj, self.schema) and obj.state is not State.SUPERSEDED
            ),
            key=lambda obj: obj.id,
        )
        return current[0] if current else None

    # -- staleness --------------------------------------------------------
    def check(self, result: AIOPObject) -> staleness.Staleness:
        return staleness.check(self.store, result, self.schema)

    def is_stale(self, result: AIOPObject) -> bool:
        return staleness.is_stale(self.store, result, self.schema)

    def stale(self) -> List[AIOPObject]:
        return staleness.stale(self.store, self.schema)

    def dependents_of(self, object_id: str) -> List[AIOPObject]:
        return staleness.dependents_of(self.store, object_id, self.schema)

    def invalidated_by(self, object_id: str) -> List[AIOPObject]:
        return staleness.invalidated_by(self.store, object_id, self.schema)

    # -- recomputation -----------------------------------------------------
    def recompute(self, result: AIOPObject) -> AIOPObject:
        """Recompute a result, superseding it rather than editing it."""
        calculation_id = result.get(self.schema.calculation_property)
        if not calculation_id:
            raise ValueError(f"'{result.id}' does not say which calculation made it")
        replacement = self.evaluate(calculation_id)
        replacement.relate(self.schema.version_predicate, result.id)
        self.store.reindex(replacement.id)
        result.transition(State.SUPERSEDED)
        return replacement

    def recompute_stale(self) -> List[AIOPObject]:
        """Refresh every result the world has moved past."""
        return [self.recompute(result) for result in self.stale()]
