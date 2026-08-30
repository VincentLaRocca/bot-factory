"""Detectors: the small, inspectable arithmetic behind an anomaly score.

Each detector answers one narrow question about a new value in the light of the
values before it, and returns a signal saying what it looked at, what it
expected, what it got and how far apart those were. A score nobody can
recompute by hand is a score nobody can argue with, so every number here comes
from a formula written in its own docstring.

The list is deliberately short. There are more dimensions an anomaly might
have than are implemented here; pretending to measure all of them would be
worse than measuring six honestly, so the registry is open and the
unimplemented dimensions stay unimplemented rather than faked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

#: How many standard deviations count as "as unusual as it gets".
SIGMA_CEILING = 4.0
#: Below this many σ nothing is reported at all.
SIGMA_FLOOR = 2.0
#: A jump smaller than this fraction of the previous value is just noise.
STEP_FLOOR = 0.25
#: A value seen in no more than this fraction of history is rare.
RARITY_CEILING = 0.10


@dataclass(frozen=True)
class Signal:
    """One dimension's verdict, with the numbers it was computed from."""

    dimension: str
    score: float
    reason: str
    expected: Any = None
    observed: Any = None
    magnitude: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "dimension": self.dimension,
            "score": self.score,
            "reason": self.reason,
        }
        if self.expected is not None:
            payload["expected"] = self.expected
        if self.observed is not None:
            payload["observed"] = self.observed
        if self.magnitude is not None:
            payload["magnitude"] = self.magnitude
        return payload


@dataclass(frozen=True)
class Comparison:
    """A new value, and the remembered ones it is being read against."""

    target: str
    value: Any
    target_property: Optional[str] = None
    values: Tuple[Any, ...] = ()
    at: Optional[datetime] = None
    expected_range: Optional[Tuple[float, float]] = None

    @property
    def numeric(self) -> bool:
        return is_number(self.value)

    @property
    def numbers(self) -> Tuple[float, ...]:
        return tuple(float(v) for v in self.values if is_number(v))

    @property
    def previous(self) -> Optional[Any]:
        return self.values[-1] if self.values else None

    def frequency(self, value: Any) -> float:
        if not self.values:
            return 0.0
        return self.values.count(value) / len(self.values)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def rounded(value: float, places: int = 4) -> float:
    return round(float(value), places)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def deviation(values: Sequence[float]) -> float:
    """Population standard deviation: the history *is* the population."""
    average = mean(values)
    return math.sqrt(sum((value - average) ** 2 for value in values) / len(values))


Detector = Callable[[Comparison], Optional[Signal]]


def first_observation(comparison: Comparison) -> Optional[Signal]:
    """Nothing to compare against is itself worth noting, quietly.

    Score is a flat 0.3: with no memory, everything is unprecedented, and a
    system that shouted about that would shout about everything.
    """
    if comparison.values:
        return None
    return Signal(
        dimension="first_observation",
        score=0.3,
        reason="no prior observation of this target and property",
        observed=comparison.value,
    )


def deviation_from_expected(comparison: Comparison) -> Optional[Signal]:
    """How many standard deviations the new value sits from the historical mean.

    ``score = min(1, σ_distance / 4)``, reported only from 2σ. Where history
    has never moved, σ is zero and the fallback is relative change against the
    constant, which is the same question asked of a degenerate distribution.
    """
    numbers = comparison.numbers
    if not comparison.numeric or len(numbers) < 2:
        return None
    value = float(comparison.value)
    average = mean(numbers)
    spread = deviation(numbers)

    if spread == 0.0:
        if value == average:
            return None
        relative = abs(value - average) / abs(average) if average else 1.0
        if relative < STEP_FLOOR:
            return None
        return Signal(
            dimension="deviation_from_expected",
            score=rounded(min(1.0, relative)),
            reason=(
                f"held at {average:g} across {len(numbers)} observations, "
                f"now {value:g}"
            ),
            expected=rounded(average),
            observed=value,
            magnitude=rounded(relative),
        )

    sigmas = abs(value - average) / spread
    if sigmas < SIGMA_FLOOR:
        return None
    return Signal(
        dimension="deviation_from_expected",
        score=rounded(min(1.0, sigmas / SIGMA_CEILING)),
        reason=(
            f"{value:g} is {sigmas:.2f}σ from the mean {average:.4g} "
            f"of {len(numbers)} observations"
        ),
        expected=rounded(average),
        observed=value,
        magnitude=rounded(sigmas),
    )


def magnitude_of_change(comparison: Comparison) -> Optional[Signal]:
    """The size of the step from the most recent value.

    ``score = min(1, |Δ| / |previous|)``, reported from a 25% move. Deviation
    asks whether the value belongs to the distribution; this asks whether it
    got there in one jump.
    """
    numbers = comparison.numbers
    if not comparison.numeric or not numbers:
        return None
    value = float(comparison.value)
    previous = numbers[-1]
    if previous == 0.0:
        return None
    relative = abs(value - previous) / abs(previous)
    if relative < STEP_FLOOR:
        return None
    direction = "up" if value > previous else "down"
    return Signal(
        dimension="magnitude_of_change",
        score=rounded(min(1.0, relative)),
        reason=f"{direction} {relative:.0%} from {previous:g} to {value:g} in one step",
        expected=previous,
        observed=value,
        magnitude=rounded(relative),
    )


def categorical_novelty(comparison: Comparison) -> Optional[Signal]:
    """A value never recorded for this target before.

    The state a thing has never been in is the cheapest anomaly there is to
    detect and often the most interesting: a technology demonstrating a
    capability it has never demonstrated does not need a distribution.
    """
    if comparison.numeric or not comparison.values:
        return None
    if comparison.value in comparison.values:
        return None
    return Signal(
        dimension="categorical_novelty",
        score=1.0,
        reason=(
            f"{comparison.value!r} never observed before across "
            f"{len(comparison.values)} observations "
            f"({', '.join(sorted({str(v) for v in comparison.values}))})"
        ),
        expected=sorted({str(value) for value in comparison.values}),
        observed=comparison.value,
    )


def historical_rarity(comparison: Comparison) -> Optional[Signal]:
    """A value seen before, but hardly ever.

    ``score = 1 - frequency``, reported when a value occupies no more than a
    tenth of a history of at least five observations.
    """
    if comparison.numeric or len(comparison.values) < 5:
        return None
    frequency = comparison.frequency(comparison.value)
    if frequency == 0.0 or frequency > RARITY_CEILING:
        return None
    return Signal(
        dimension="historical_rarity",
        score=rounded(1.0 - frequency),
        reason=(
            f"{comparison.value!r} seen in {frequency:.0%} of "
            f"{len(comparison.values)} observations"
        ),
        observed=comparison.value,
        magnitude=rounded(frequency),
    )


def threshold_crossing(comparison: Comparison) -> Optional[Signal]:
    """A value outside a range somebody declared in advance.

    The only detector whose expectation comes from a person rather than from
    history, which is exactly why it has to be passed in explicitly.
    """
    if not comparison.numeric or comparison.expected_range is None:
        return None
    low, high = comparison.expected_range
    value = float(comparison.value)
    if low <= value <= high:
        return None
    distance = low - value if value < low else value - high
    width = abs(high - low) or 1.0
    return Signal(
        dimension="threshold_crossing",
        score=rounded(min(1.0, distance / width)),
        reason=f"{value:g} is outside the expected range [{low:g}, {high:g}]",
        expected=[low, high],
        observed=value,
        magnitude=rounded(distance),
    )


@dataclass
class DetectorRegistry:
    """The dimensions this listener currently knows how to measure."""

    detectors: Dict[str, Detector] = field(default_factory=dict)

    @classmethod
    def of(cls, *detectors: Detector) -> "DetectorRegistry":
        return cls({detector.__name__: detector for detector in detectors})

    def register(self, name: str, detector: Detector) -> "DetectorRegistry":
        self.detectors[name] = detector
        return self

    def extend(self, other: "DetectorRegistry") -> "DetectorRegistry":
        return DetectorRegistry({**self.detectors, **other.detectors})

    def names(self) -> List[str]:
        return sorted(self.detectors)

    def run(self, comparison: Comparison) -> List[Signal]:
        """Every dimension that fired, strongest first, then alphabetically.

        The ordering is total and content-independent of dictionary order, so
        two runs over the same history produce byte-identical output.
        """
        signals = [
            signal
            for signal in (
                self.detectors[name](comparison) for name in self.names()
            )
            if signal is not None
        ]
        return sorted(signals, key=lambda s: (-s.score, s.dimension))

    def __len__(self) -> int:
        return len(self.detectors)

    def __iter__(self) -> Iterable[str]:
        return iter(self.names())


#: What v0.1 measures: six dimensions honestly, rather than nine decoratively.
DEFAULT_DETECTORS = DetectorRegistry.of(
    first_observation,
    deviation_from_expected,
    magnitude_of_change,
    categorical_novelty,
    historical_rarity,
    threshold_crossing,
)

__all__ = [
    "Comparison",
    "DEFAULT_DETECTORS",
    "Detector",
    "DetectorRegistry",
    "RARITY_CEILING",
    "SIGMA_CEILING",
    "SIGMA_FLOOR",
    "STEP_FLOOR",
    "Signal",
    "categorical_novelty",
    "deviation",
    "deviation_from_expected",
    "first_observation",
    "historical_rarity",
    "is_number",
    "magnitude_of_change",
    "mean",
    "rounded",
    "threshold_crossing",
]
