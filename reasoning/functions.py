"""A registry of named, pure calculation functions.

A calculation object names a function; it never carries executable text. There
is no ``eval`` here and there should never be one: a stored string that the
engine would execute is a stored string that anything upstream of the store can
make the engine execute.

The registry is domain-neutral. The formulas themselves — expected value,
risk-adjusted upside — are modelling decisions and live in a profile.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Mapping, Tuple


class UnknownFunction(KeyError):
    """Raised when a calculation names a function nobody registered."""

    def __init__(self, name: str, known: List[str]) -> None:
        super().__init__(f"'{name}' is not registered (known: {', '.join(known) or 'none'})")
        self.name = name
        self.known = known


class ArgumentMismatch(ValueError):
    """Raised when the resolved variables do not fit the function signature."""


@dataclass(frozen=True)
class CalculationFunction:
    """A named pure function of its declared variables."""

    name: str
    implementation: Callable[..., Any]
    description: str = ""

    @property
    def variables(self) -> Tuple[str, ...]:
        """The variables the function expects, in signature order."""
        return tuple(inspect.signature(self.implementation).parameters)

    def apply(self, values: Mapping[str, Any]) -> Any:
        expected = set(self.variables)
        supplied = set(values)
        if expected != supplied:
            missing = sorted(expected - supplied)
            unexpected = sorted(supplied - expected)
            raise ArgumentMismatch(
                f"'{self.name}' expects {sorted(expected)}"
                + (f"; missing {missing}" if missing else "")
                + (f"; unexpected {unexpected}" if unexpected else "")
            )
        return self.implementation(**values)


class FunctionRegistry:
    """The functions a reasoning engine is allowed to run."""

    def __init__(self, functions: Mapping[str, CalculationFunction] = None) -> None:
        self._functions: Dict[str, CalculationFunction] = dict(functions or {})

    def __len__(self) -> int:
        return len(self._functions)

    def __contains__(self, name: str) -> bool:
        return name in self._functions

    def __iter__(self) -> Iterator[CalculationFunction]:
        return iter(self._functions[name] for name in self.names())

    def names(self) -> List[str]:
        return sorted(self._functions)

    def get(self, name: str) -> CalculationFunction:
        try:
            return self._functions[name]
        except KeyError:
            raise UnknownFunction(name, self.names()) from None

    def add(self, function: CalculationFunction) -> CalculationFunction:
        self._functions[function.name] = function
        return function

    def function(
        self, name: str, description: str = ""
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register the decorated function under ``name``."""

        def register(implementation: Callable[..., Any]) -> Callable[..., Any]:
            self.add(
                CalculationFunction(
                    name=name,
                    implementation=implementation,
                    description=description or (implementation.__doc__ or "").strip(),
                )
            )
            return implementation

        return register

    def apply(self, name: str, values: Mapping[str, Any]) -> Any:
        return self.get(name).apply(values)

    def extend(self, other: "FunctionRegistry") -> "FunctionRegistry":
        """A registry holding both sets of functions; neither is changed."""
        return FunctionRegistry({**self._functions, **other._functions})
