"""Condition, mileage and hours read from listing text, shared by vehicle and equipment appraisers."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# (pattern, factor on whole value, label). The first match wins, worst cases first.
CONDITION = [
    (r"\bparts only\b|\bfor parts\b|\bparts vehicle\b", 0.2, "parts only"),
    (r"\bflood\b|\bfire damage\b|\bburn(?:ed|t)\b", 0.25, "flood/fire"),
    (r"\b(?:does not|doesn'?t|won'?t|will not) (?:run|start|crank)\b|\bnon[- ]?running\b|\bno start\b|\binoperable\b|\bnot running\b", 0.4, "does not run"),
    (r"\bneeds (?:an? )?(?:engine|motor|transmission|trans)\b|\b(?:blown|seized) (?:engine|motor)\b|\bbad (?:engine|transmission)\b", 0.5, "needs engine/transmission"),
    (r"\bno title\b|\bbill of sale only\b", 0.5, "no title"),
    (r"\bsalvage\b|\brebuilt title\b|\bbranded title\b", 0.6, "salvage/rebuilt title"),
    (r"\bneeds (?:work|repair|tlc)\b|\bmechanic special\b|\bas[- ]is\b", 0.75, "needs work / as-is"),
    (r"\bruns (?:and|&) drives\b|\bruns (?:and|&) operates\b|\bruns great\b|\bstarts,? runs\b|\boperational\b|\bin service\b|\bruns\b", 1.0, "runs"),
]


def condition(text: str) -> Tuple[float, str, bool]:
    """(factor, label, known). Unknown condition = 0.8 and known=False."""
    for pattern, factor, label in CONDITION:
        if re.search(pattern, text):
            return factor, label, True
    return 0.8, "condition not stated", False


def _num(raw: str) -> float:
    raw = raw.replace(",", "").lower()
    return float(raw[:-1]) * 1000 if raw.endswith("k") else float(raw)


def mileage(text: str) -> Optional[float]:
    m = re.search(r"(\d[\d,]*\.?\d*k?)\s*(?:miles|mi\b|mileage)", text) or re.search(r"(?:odometer|mileage)\s*:?\s*(\d[\d,]*k?)", text)
    return _num(m.group(1)) if m else None


def hours(text: str) -> Optional[float]:
    m = re.search(r"(\d[\d,]*\.?\d*k?)\s*(?:hours|hrs|hr\b)", text) or re.search(r"(?:hours|hour meter)\s*:?\s*(\d[\d,]*)", text)
    return _num(m.group(1)) if m else None


def year(text: str) -> Optional[int]:
    m = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", text)
    return int(m.group(1)) if m else None


def use_factor(value: Optional[float], bands: List[Tuple[float, float]]) -> float:
    if value is None:
        return 1.0
    return next(mult for limit, mult in bands if value <= limit)
