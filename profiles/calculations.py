"""Demo calculations: the vocabulary and the formulas.

Two things live here that deliberately do not live in ``reasoning/``:

* the **schema** — which property holds a function name, what a result object
  is called, which predicate means "derived from". The reasoning layer takes
  all of it as configuration, exactly as the store takes its version predicate.
* the **formulas** — expected value is a modelling decision about opportunities,
  not a universal truth about objects, so it belongs to a profile.

Swap this module and the same engine reasons in another domain.
"""

from reasoning import CalculationFunction, CalculationSchema, FunctionRegistry

from .demo import VERSION_PREDICATE

#: How the demo world writes calculations and results down.
DEMO_CALCULATION_SCHEMA = CalculationSchema(
    result_type="Result",
    function_property="function",
    inputs_property="inputs",
    value_property="value",
    fingerprint_property="inputFingerprint",
    calculation_property="calculation",
    variable_key="variable",
    source_key="source",
    source_property_key="sourceProperty",
    derivation_predicate="derivedFrom",
    version_predicate=VERSION_PREDICATE,
)

DEMO_FUNCTIONS = FunctionRegistry()


@DEMO_FUNCTIONS.function(
    "expected_value",
    description=(
        "Upside weighted by the joint probability of execution, technical "
        "success and market adoption, less the downside carried if it misses."
    ),
)
def expected_value(
    upside: float,
    downside: float,
    execution_probability: float,
    success_probability: float,
    adoption_probability: float,
) -> float:
    """The asymmetry of an opportunity as a single figure."""
    probability = execution_probability * success_probability * adoption_probability
    return upside * probability - downside * (1.0 - probability)


@DEMO_FUNCTIONS.function(
    "payoff_ratio",
    description="How many times the downside the upside is worth.",
)
def payoff_ratio(upside: float, downside: float) -> float:
    """Asymmetry before probability is considered at all."""
    if downside == 0:
        raise ZeroDivisionError("payoff_ratio needs a non-zero downside")
    return upside / downside


__all__ = [
    "CalculationFunction",
    "DEMO_CALCULATION_SCHEMA",
    "DEMO_FUNCTIONS",
    "expected_value",
    "payoff_ratio",
]
