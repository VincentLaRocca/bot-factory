"""AIOP Calculation & Reasoning v0.1.

The layer where the graph starts doing intellectual work. A calculation is an
object that declares which properties of which objects it consumes and which
named function combines them. Evaluating it produces another object — value,
provenance, input snapshot, and a derivation edge to every source — so a
conclusion is addressable, inspectable and reproducible in the same way a fact
is.

Because the derivation edges are indexed both ways, "what did this new evidence
just invalidate?" is a lookup. Because each result carries a fingerprint of the
inputs it was computed from, "is this still true?" is a comparison. Because
recomputation supersedes rather than overwrites, the history of a conclusion
survives being wrong.

Nothing here knows a domain word: every term is supplied by a
:class:`CalculationSchema`, and every formula by a :class:`FunctionRegistry`.
"""

from .binding import (
    Binding,
    BindingKeys,
    ResolvedBinding,
    UnresolvedBinding,
    resolve,
    values,
)
from .calculation import (
    Calculation,
    CalculationSchema,
    MalformedCalculation,
    bindings_of,
    fingerprint,
    input_snapshot,
    is_result,
)
from .engine import DEFAULT_AGENT, ReasoningEngine
from .functions import (
    ArgumentMismatch,
    CalculationFunction,
    FunctionRegistry,
    UnknownFunction,
)
from .staleness import (
    Staleness,
    check,
    dependents_of,
    invalidated_by,
    is_stale,
    results,
    stale,
)

__all__ = [
    "ArgumentMismatch",
    "Binding",
    "BindingKeys",
    "Calculation",
    "CalculationFunction",
    "CalculationSchema",
    "DEFAULT_AGENT",
    "FunctionRegistry",
    "MalformedCalculation",
    "ReasoningEngine",
    "ResolvedBinding",
    "Staleness",
    "UnknownFunction",
    "UnresolvedBinding",
    "bindings_of",
    "check",
    "dependents_of",
    "fingerprint",
    "input_snapshot",
    "invalidated_by",
    "is_result",
    "is_stale",
    "resolve",
    "results",
    "stale",
    "values",
]
