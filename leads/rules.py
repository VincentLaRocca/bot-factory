"""Rule-based scoring. No model, no API call — every point has a reason.

This follows the Maker/Breaker call on the bid hunter: v0 filters are rules a
human can read and argue with. A rule set is plain config:

```json
{
  "require_any": ["paint", "painting", "coating"],
  "exclude_any": ["hiring", "full-time"],
  "boost": {"sdvosb": 25, "richmond": 10, "asap": 15},
  "geo_any": ["virginia", " va ", "richmond", "norfolk"],
  "geo_points": 15,
  "urgent_any": ["asap", "emergency", "today"],
  "min_score": 20
}
```

Gates (a miss → score 0, dropped):

- `require_any`        at least one term anywhere in title/body/location
- `require_title_any`  at least one term in the *title* — social posts mention
                       "painting" in passing all the time; a title hit means
                       the post is actually about it
- `intent_any`         at least one buying-intent phrase ("looking for",
                       "need a", "recommend", "[hiring]") — separates someone
                       who wants to hire from someone chatting about the topic

`exclude_any` is a hard veto; everything else adds points. The score is
clamped to 0–100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

from .model import Lead

BASE_SCORE = 20


def _hits(text: str, terms) -> List[str]:
    return [t for t in terms if t and t.lower() in text]


@dataclass
class RuleSet:
    require_any: List[str] = field(default_factory=list)
    require_title_any: List[str] = field(default_factory=list)
    intent_any: List[str] = field(default_factory=list)
    exclude_any: List[str] = field(default_factory=list)
    boost: Dict[str, int] = field(default_factory=dict)
    geo_any: List[str] = field(default_factory=list)
    geo_points: int = 15
    urgent_any: List[str] = field(default_factory=list)
    min_score: int = 20

    @classmethod
    def from_config(cls, data: Mapping[str, Any] = None) -> "RuleSet":
        data = dict(data or {})
        return cls(
            require_any=list(data.get("require_any", [])),
            require_title_any=list(data.get("require_title_any", [])),
            intent_any=list(data.get("intent_any", [])),
            exclude_any=list(data.get("exclude_any", [])),
            boost={str(k): int(v) for k, v in dict(data.get("boost", {})).items()},
            geo_any=list(data.get("geo_any", [])),
            geo_points=int(data.get("geo_points", 15)),
            urgent_any=list(data.get("urgent_any", [])),
            min_score=int(data.get("min_score", 20)),
        )

    def merged(self, override: Mapping[str, Any] = None) -> "RuleSet":
        """A listener's own rules layered over the global defaults."""
        if not override:
            return self
        base = {
            "require_any": self.require_any, "require_title_any": self.require_title_any,
            "intent_any": self.intent_any, "exclude_any": self.exclude_any,
            "boost": dict(self.boost), "geo_any": self.geo_any, "geo_points": self.geo_points,
            "urgent_any": self.urgent_any, "min_score": self.min_score,
        }
        for key, value in override.items():
            if key == "boost":
                base["boost"].update(value)
            else:
                base[key] = value
        return RuleSet.from_config(base)

    def score(self, lead: Lead) -> Tuple[int, str, List[str]]:
        """Return (score, urgency, reasons). Does not mutate the lead."""
        text = " " + lead.text() + " "
        reasons: List[str] = []

        vetoes = _hits(text, self.exclude_any)
        if vetoes:
            return 0, "LOW", [f"excluded: {', '.join(vetoes)}"]
        if self.require_any:
            required = _hits(text, self.require_any)
            if not required:
                return 0, "LOW", ["no required keyword"]
            reasons.append(f"matched: {', '.join(required[:4])}")
        if self.require_title_any:
            titled = _hits(" " + lead.title.lower() + " ", self.require_title_any)
            if not titled:
                return 0, "LOW", ["topic not in title"]
            reasons.append(f"title: {', '.join(titled[:3])}")
        if self.intent_any:
            intent = _hits(text, self.intent_any)
            if not intent:
                return 0, "LOW", ["no buying intent"]
            reasons.append(f"intent: {intent[0]}")

        score = BASE_SCORE
        for term, points in self.boost.items():
            if term.lower() in text:
                score += points
                reasons.append(f"{'+' if points >= 0 else ''}{points} {term}")
        geo = _hits(text, self.geo_any)
        if geo:
            score += self.geo_points
            reasons.append(f"+{self.geo_points} in area ({geo[0].strip()})")
        if lead.value and lead.value > 0:
            score += 5
            reasons.append("+5 has a stated value")
        urgent = _hits(text, self.urgent_any)
        if urgent:
            score += 15
            reasons.append(f"+15 urgent ({urgent[0]})")

        score = max(0, min(100, score))
        if urgent and score >= 60:
            urgency = "CRITICAL"
        elif score >= 70 or urgent:
            urgency = "HIGH"
        elif score >= 40:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"
        return score, urgency, reasons

    def passes(self, score: int) -> bool:
        return score >= self.min_score
