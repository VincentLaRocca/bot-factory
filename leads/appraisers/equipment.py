"""Equipment appraiser: construction, material handling, power, trailers, trucks for work.

Floor (Vinny's money-back test): typical operating weight x scrap yield x $/ton.
Estimate: price-sheet comp x condition x hours.
Weights are low-end typical; set ``scrap_per_ton`` from your local yard.
"""

from __future__ import annotations

import re
from typing import List, Optional

from . import Appraisal, register
from . import comps as comps_module
from .condition import condition, hours, use_factor, year

TYPES = [  # (pattern, typical weight lb, comp word(s), label). More specific first.
    (r"\bmini[- ]?excavator\b", 7000, "mini excavator", "mini excavator"),
    (r"\bexcavator\b|\btrackhoe\b", 30000, "excavator", "excavator"),
    (r"\bbackhoe\b", 15000, "backhoe", "backhoe"),
    (r"\bskid[- ]?steer\b|\bbobcat\b|\btrack loader\b", 6500, "skid steer", "skid steer"),
    (r"\bwheel loader\b|\bfront[- ]end loader\b", 20000, "loader", "wheel loader"),
    (r"\bbull?dozer\b|\bdozer\b", 18000, "dozer", "dozer"),
    (r"\bforklift\b|\bfork lift\b|\blift truck\b", 8000, "forklift", "forklift"),
    (r"\bboom lift\b|\bscissor lift\b|\baerial lift\b|\bmanlift\b", 7000, "lift", "aerial lift"),
    (r"\bdump truck\b", 25000, "dump truck", "dump truck"),
    (r"\bbox truck\b|\bstraight truck\b", 12000, "box truck", "box truck"),
    (r"\btractor\b", 5000, "tractor", "tractor"),
    (r"\bgenerator\b|\bgenset\b", 2500, "generator", "generator"),
    (r"\bair compressor\b|\bcompressor\b", 2000, "air compressor", "compressor"),
    (r"\bzero[- ]turn\b|\briding mower\b|\bmower\b", 1000, "zero turn mower", "mower"),
    (r"\btrailer\b", 2500, "trailer", "trailer"),
    (r"\bwelder\b", 600, "welder", "welder"),
]
HOUR_BANDS = [(1000, 1.15), (3000, 1.0), (6000, 0.85), (10000, 0.65), (1e12, 0.5)]


def matches(text: str) -> bool:
    text = text.lower()
    return any(re.search(p, text) for p, _, _, _ in TYPES)


@register("equipment")
def appraise(text: str, cost: float = 0.0, comps: Optional[List] = None, scrap_per_ton: float = 180.0,
             scrap_yield: float = 0.8, **_) -> Optional[Appraisal]:
    text = " " + text.lower() + " "
    found = next(((lb, word, label) for p, lb, word, label in TYPES if re.search(p, text)), None)
    if not found:
        return None
    weight, word, label = found
    yr, hrs = year(text), hours(text)
    factor, cond, known = condition(text)
    floor = round(weight / 2000 * scrap_yield * scrap_per_ton, 2)
    facts = [f"{label}, ~{weight:,} lb typical → scrap ~${floor:,.0f}"]
    estimate, confidence = 0.0, 0.45
    comp = comps_module.best(comps if comps is not None else comps_module.load(), "equipment", text, yr)
    if comp:
        use = use_factor(hrs, HOUR_BANDS)
        estimate = round(comp.value * factor * use, 2)
        confidence = 0.55
        facts.append(f"comp '{' '.join(comp.words)}' ${comp.value:,.0f} × {cond} {factor:g}"
                     + (f" × {hrs:,.0f} hrs {use:g}" if hrs else "") + (f" · {comp.note}" if comp.note else ""))
    else:
        facts.append(f"no price-sheet comp; condition: {cond}")
    if not known:
        confidence -= 0.15
    extra = [(10, "runs/operational")] if factor >= 1.0 and known else []
    return Appraisal("equipment", " ".join(x for x in (str(yr) if yr else "", label) if x), floor=floor,
                     estimate=estimate, confidence=max(0.2, confidence), facts=facts, extra=extra,
                     no_veto=True)  # a working machine is worth more than its scrap; the floor only rewards


appraise.matches = matches
