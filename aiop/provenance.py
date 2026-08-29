"""Provenance records describing where an object's content came from.

Each record keeps its own ``confidence`` as an individual, opaque value. Core
records evidence; it never folds several values into a single score. Deriving
one figure from many is a modelling decision, and belongs to objects layered
above Core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Provenance:
    """A single attestation about how a value or object was produced."""

    agent: str
    method: str = "asserted"
    source: Optional[str] = None
    confidence: float = 1.0
    generated_at: datetime = field(default_factory=utcnow)
    note: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0.0, 1.0]")
        if isinstance(self.generated_at, str):
            self.generated_at = parse_timestamp(self.generated_at)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "agent": self.agent,
            "method": self.method,
            "confidence": self.confidence,
            "generatedAt": self.generated_at.isoformat(),
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.note is not None:
            payload["note"] = self.note
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Provenance":
        return cls(
            agent=payload["agent"],
            method=payload.get("method", "asserted"),
            source=payload.get("source"),
            confidence=float(payload.get("confidence", 1.0)),
            generated_at=parse_timestamp(payload["generatedAt"])
            if "generatedAt" in payload
            else utcnow(),
            note=payload.get("note"),
        )


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, normalising a trailing ``Z``."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class ProvenanceChain:
    """An ordered chain of attestations."""

    def __init__(self, records: Optional[Iterable[Provenance]] = None) -> None:
        self._records: List[Provenance] = sorted(
            records or [], key=lambda p: p.generated_at
        )

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self):
        return iter(self._records)

    def append(self, record: Provenance) -> "ProvenanceChain":
        self._records.append(record)
        self._records.sort(key=lambda p: p.generated_at)
        return self

    @property
    def records(self) -> List[Provenance]:
        return list(self._records)

    @property
    def latest(self) -> Optional[Provenance]:
        return self._records[-1] if self._records else None

    def confidences(self) -> List[float]:
        """The individual confidences, in chain order, exactly as recorded."""
        return [record.confidence for record in self._records]

    def by_agent(self, agent: str) -> List[Provenance]:
        return [r for r in self._records if r.agent == agent]
