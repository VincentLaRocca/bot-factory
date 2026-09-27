"""Vehicle appraiser: cars, pickups, SUVs, vans.

Floor (Vinny's money-back test): scrap weight + catalytic converter.
    curb weight (by body type) x scrap yield x $/ton  +  converter value
Estimate: price-sheet comp for make/model/year x condition x mileage.

Scrap $/ton, yield and converter value are placeholders; set them from what
your local yard actually pays (``scrap_per_ton``, ``cat_value``).

**Book test (Vinny's rule):** compare asking price to book value (Blue
Book-style, from the price sheet: his numbers, looked up on KBB/NADA/Edmunds)
adjusted for mileage. **40%+ under book with nothing else wrong in the ad** is
flagged hard. "Nothing else wrong" means no salvage, rebuilt, flood, parts-only,
no-title, non-running or engine/transmission trouble, and no scam tells
("deposit to hold", "gift card", "deployed overseas", "shipping only", "Zelle
only"…). Cheap *and* flawed gets noted, not flagged: the ad already explains the price.
"""

from __future__ import annotations

import re
from typing import List, Optional

from . import Appraisal, register
from . import comps as comps_module
from .condition import condition, mileage, use_factor, year

MAKES = ["ford", "chevrolet", "chevy", "dodge", "ram", "gmc", "toyota", "honda", "nissan", "jeep", "hyundai",
         "kia", "subaru", "mazda", "volkswagen", "vw", "bmw", "mercedes", "lexus", "acura", "buick", "cadillac",
         "chrysler", "lincoln", "mitsubishi", "volvo", "tesla", "infiniti"]
BODIES = [  # (pattern, curb weight lb, label)
    (r"\b(?:pickup|f-?150|f-?250|f-?350|silverado|sierra|ram 1500|ram 2500|tundra|tacoma|colorado|ranger|frontier|titan)\b", 4800, "pickup"),
    (r"\b(?:cargo van|transit|sprinter|promaster|express|savana|econoline|e-?350|minivan|caravan|odyssey|sienna|van)\b", 4500, "van"),
    (r"\b(?:suv|explorer|tahoe|suburban|expedition|durango|4runner|pilot|highlander|escape|equinox|cherokee|wrangler|rav4|cr-?v)\b", 4300, "SUV"),
    (r"\b(?:sedan|coupe|camry|accord|corolla|civic|altima|fusion|malibu|impala|charger|focus|sentra|elantra|sonata|car)\b", 3300, "car"),
]
RED_FLAGS = [
    (r"\bsalvage\b|\brebuilt\b|\bbranded title\b|\breconstructed\b", "salvage/rebuilt title"),
    (r"\bflood\b|\bwater damage\b|\bfire\b|\bhail\b", "flood/fire/hail"),
    (r"\bparts only\b|\bfor parts\b|\bproject car\b", "parts/project"),
    (r"\bno title\b|\bbill of sale only\b|\blost title\b|\btitle (?:issue|problem)s?\b|\blien\b", "title problem"),
    (r"\b(?:does not|doesn'?t|won'?t|will not) (?:run|start|crank)\b|\bnon[- ]?running\b|\bnot running\b|\binoperable\b", "does not run"),
    (r"\b(?:needs|bad|blown|seized|slipping) (?:an? )?(?:engine|motor|transmission|trans|head gasket)\b|\bcheck engine light\b|\bknocking\b", "engine/transmission trouble"),
    (r"\bframe damage\b|\brust(?:ed)? (?:through|out)\b|\bfrozen\b", "frame/rust"),
    (r"\bmechanic special\b|\bneeds work\b|\bas[- ]is\b|\btlc\b", "needs work / as-is"),
    (r"\bmiles? (?:unknown|not actual)\b|\btmu\b|\bexempt\b|\brolled back\b", "mileage not actual"),
]
SCAM_TELLS = [
    r"\bdeposit\b.*\bhold\b|\bhold\b.*\bdeposit\b", r"\bgift ?cards?\b", r"\bdeployed\b|\bdeployment\b|\bmilitary transfer\b",
    r"\bshipping only\b|\bwill ship to you\b|\bdelivered to your door\b", r"\bzelle only\b|\bwire (?:transfer )?only\b|\bcash app only\b",
    r"\bescrow\b", r"\bebay (?:motors )?(?:protection|agent|escrow)\b", r"\bmust sell (?:today|asap)\b.*\bmoving\b",
    r"\bemail me at\b|\btext me at\b.*@",
]
MILEAGE_BANDS = [(60000, 1.15), (120000, 1.0), (160000, 0.85), (200000, 0.7), (1e12, 0.55)]


def ad_problems(text: str) -> list:
    """Everything in the ad that would explain a low price (or make it a trap)."""
    problems = [label for pattern, label in RED_FLAGS if re.search(pattern, text)]
    if any(re.search(p, text) for p in SCAM_TELLS):
        problems.append("scam tells")
    return problems


def matches(text: str) -> bool:
    text = text.lower()
    has_year = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", text)
    return bool(any(re.search(p, text) for p, _, _ in BODIES) or (has_year and any(re.search(r"\b" + m + r"\b", text) for m in MAKES)))


@register("vehicle")
def appraise(text: str, cost: float = 0.0, comps: Optional[List] = None, scrap_per_ton: float = 180.0,
             scrap_yield: float = 0.75, cat_value: float = 100.0, book_discount: float = 0.40,
             **_) -> Optional[Appraisal]:
    text = " " + text.lower() + " "
    text = re.sub(r"\bf ?(150|250|350|450)\b", r"f-\1", text)          # F150 / F 150 → f-150
    text = re.sub(r"\bchevy\b", "chevrolet", text)
    weight, body = 3500, "vehicle"
    for pattern, lb, label in BODIES:
        if re.search(pattern, text):
            weight, body = lb, label
            break
    yr, miles = year(text), mileage(text)
    factor, cond, known = condition(text)
    converter = 0.0 if re.search(r"\b(?:no|missing|removed|stolen) (?:catalytic|cat)\b"
                                 r"|\b(?:catalytic(?: converters?)?|cat)\s+(?:removed|missing|gone|cut|stolen)\b", text) else cat_value
    floor = round(weight / 2000 * scrap_yield * scrap_per_ton + converter, 2)
    facts = [f"{body}, ~{weight:,} lb curb → scrap ~${floor - converter:,.0f}"
             + (f" + converter ~${converter:,.0f}" if converter else " (no converter)")]
    estimate, confidence = 0.0, 0.45
    comp = comps_module.best(comps if comps is not None else comps_module.load(), "vehicle", text, yr)
    extra = []
    problems = ad_problems(text)
    if comp:
        mile = use_factor(miles, MILEAGE_BANDS)
        book = round(comp.value * mile, 2)               # book value for this mileage, before condition
        estimate = round(book * factor, 2)
        dated = bool(yr and (comp.year_from or comp.year_to))
        confidence = 0.7 if dated and len(comp.words) > 1 else 0.5
        facts.append(f"book '{' '.join(comp.words)}' ${comp.value:,.0f}"
                     + (f" ({comp.year_from}–{comp.year_to})" if dated else "")
                     + (f" × {miles:,.0f} mi {mile:g} = ${book:,.0f}" if miles else "")
                     + f"; × {cond} {factor:g}" + (f" · {comp.note}" if comp.note else ""))
        if cost and book:
            under = 1 - cost / book
            facts.append(f"asking ${cost:,.0f} is {under:.0%} {'under' if under >= 0 else 'over'} book")
            if under >= book_discount and not problems:
                extra.append((45 if dated else 30,
                              f"{under:.0%} under book (${cost:,.0f} vs ${book:,.0f}) and the ad looks normal"))
            elif under >= book_discount:
                facts.append(f"{under:.0%} under book, but the ad explains it: {', '.join(problems)}")
    else:
        facts.append(f"no book value on the price sheet; condition: {cond}")
    if problems:
        facts.append("ad flags: " + ", ".join(problems))
    if "scam tells" in problems:
        extra.append((-40, "scam tells in the ad"))
        estimate = 0.0          # never advertise upside on a likely scam
    if re.search(r"\b[a-hj-npr-z0-9]{17}\b", text) and re.search(r"\d", text):
        extra.append((5, "VIN listed"))
    if not known:
        confidence -= 0.15
    if factor >= 1.0 and known:
        extra.append((10, "runs"))
    item = " ".join(x for x in (str(yr) if yr else "", body) if x)
    return Appraisal("vehicle", item, floor=floor, estimate=estimate, confidence=max(0.2, confidence),
                     facts=facts, extra=extra,
                     no_veto=True)  # a working machine is worth more than its scrap; the floor only rewards


appraise.matches = matches
