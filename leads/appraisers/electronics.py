"""Electronics appraiser: laptops, desktops, servers, monitors, networking. Vinny's old trade.

Government surplus is full of IT lots ("lot of 25 Dell Latitude laptops, no
hard drives"). Refurbishers know the drill: per-unit value x count, minus what
is missing.

Floor (money back if broken down): per-unit parts / e-scrap value x count
(RAM, CPUs, screens, boards). Placeholder per-unit numbers, so set your own.
Estimate: price-sheet comp per unit (e.g. "latitude 5490") x count x condition.
"""

from __future__ import annotations

import re
from typing import List, Optional

from . import Appraisal, register
from . import comps as comps_module

TYPES = [  # (pattern, parts value per unit $, label). More specific first.
    (r"\bservers?\b|\bpoweredge\b|\bproliant\b", 60.0, "server"),
    (r"\bworkstations?\b|\bprecision\b|\bz[468]\d0\b", 30.0, "workstation"),
    (r"\blaptops?\b|\bnotebooks?\b|\blatitude\b|\bthinkpad\b|\belitebook\b|\bprobook\b|\bmacbook\b|\bchromebooks?\b|\btoughbook\b", 15.0, "laptop"),
    (r"\bdesktops?\b|\boptiplex\b|\bprodesk\b|\belitedesk\b|\bthinkcentre\b|\bimac\b|\bmac mini\b|\btower\b", 10.0, "desktop"),
    (r"\btablets?\b|\bipads?\b|\bsurface\b", 10.0, "tablet"),
    (r"\bmonitors?\b|\bdisplays?\b", 4.0, "monitor"),
    (r"\bswitch(?:es)?\b|\brouters?\b|\bfirewalls?\b|\bcisco\b|\bjuniper\b", 8.0, "network gear"),
    (r"\bprinters?\b|\bcopiers?\b", 2.0, "printer"),
    (r"\bcell ?phones?\b|\biphones?\b|\bsmartphones?\b", 5.0, "phone"),
]
CONDITION = [
    (r"\bfor parts\b|\bparts only\b|\bdamaged\b|\bbroken\b|\bcracked\b|\bno power\b|\bdoes not power\b", 0.25, "parts/damaged"),
    (r"\bno (?:hard ?drives?|hdds?|ssds?|drives?|storage)\b|\bdrives? removed\b|\bwithout (?:hard ?drives?|hdd)\b", 0.8, "no drives (gov standard)"),
    (r"\bno (?:ram|memory)\b", 0.8, "no RAM"),
    (r"\bno (?:power )?(?:adapters?|chargers?|power cords?)\b", 0.9, "no chargers"),
    (r"\buntested\b|\bas[- ]is\b|\bunknown condition\b", 0.6, "untested / as-is"),
    (r"\btested\b|\bworking\b|\bpowers on\b|\bboots\b|\bfunctional\b", 1.0, "tested working"),
]
_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10, "twelve": 12, "twenty": 20}


def matches(text: str) -> bool:
    text = text.lower()
    return any(re.search(p, text) for p, _, _ in TYPES)


def count(text: str) -> int:
    for pattern in (r"\blot of\s*\(?(\d+)\)?", r"\bqty\.?\s*:?\s*(\d+)", r"\((\d+)\)", r"\b(\d+)\s*(?:x\b|ea\b|each|units?|pcs|pieces)",
                    r"\b(\d+)\s+(?:\w+\s+){0,3}(?:laptops|desktops|computers|monitors|servers|tablets|phones|switches|printers|pcs)\b"):
        m = re.search(pattern, text)
        if m and 1 < int(m.group(1)) <= 2000:
            return int(m.group(1))
    m = re.search(r"\blot of (" + "|".join(_WORDS) + r")\b", text)
    return _WORDS[m.group(1)] if m else 1


@register("electronics")
def appraise(text: str, cost: float = 0.0, comps: Optional[List] = None, parts_value: Optional[dict] = None,
             **_) -> Optional[Appraisal]:
    text = " " + text.lower() + " "
    found = next(((value, label) for p, value, label in TYPES if re.search(p, text)), None)
    if not found:
        return None
    per_unit_parts, label = found
    per_unit_parts = (parts_value or {}).get(label, per_unit_parts)
    n = count(text)
    factor, cond = next(((f, c) for p, f, c in CONDITION if re.search(p, text)), (0.7, "condition not stated"))
    floor = round(per_unit_parts * n, 2)
    facts = [f"{n} × {label}: parts/e-scrap ~${per_unit_parts:,.0f} each → ${floor:,.0f}"]
    estimate, confidence = 0.0, 0.4
    comp = comps_module.best(comps if comps is not None else comps_module.load(), "electronics", text)
    if comp:
        estimate = round(comp.value * n * factor, 2)
        confidence = 0.65 if len(comp.words) > 1 else 0.45
        facts.append(f"comp '{' '.join(comp.words)}' ${comp.value:,.0f}/unit × {n} × {cond} {factor:g}"
                     + (f" · {comp.note}" if comp.note else ""))
    else:
        facts.append(f"no price-sheet comp; condition: {cond}")
    extra = [(10, f"bulk lot of {n}")] if n >= 10 else []
    return Appraisal("electronics", f"{n} × {label}", floor=floor, estimate=estimate, confidence=confidence,
                     facts=facts, extra=extra, no_veto=True, reference=estimate)


appraise.matches = matches
