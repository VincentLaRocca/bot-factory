"""Appraisers: the heart of the opportunity finder.

A source (eBay, GSA surplus, estate alerts, Chrome) hands over a listing: its
text and what it costs. An appraiser answers two questions:

1. **The floor.** Vinny's value test: if it were broken into its elements, could
   we get our money back? (Metal melt + gems for jewelry; scrap weight + key
   parts for vehicles and equipment.)
2. **The estimate.** What it's worth whole, from a price sheet of comparable
   sales, adjusted for condition, with an honest confidence.

Every appraiser returns an :class:`Appraisal`. :func:`score` turns it into
evidence points (``Lead.bonus``) the same way for every domain, so a new
domain only needs a new appraiser.

    from leads.appraisers import appraise
    a = appraise("2014 Ford F-150 4x4 runs and drives", cost=4200)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

Bonus = List[Tuple[int, str]]


@dataclass
class Appraisal:
    domain: str                     # "jewelry" | "vehicle" | "equipment" | "electronics"
    item: str                       # what we think it is, in words
    floor: float = 0.0              # break-down value: money-back line
    estimate: float = 0.0           # whole value from comps (0 = no comp)
    confidence: float = 0.5         # 0–1, how much to trust the numbers
    facts: List[str] = field(default_factory=list)
    extra: Bonus = field(default_factory=list)   # domain-specific evidence points
    no_veto: bool = False           # e.g. designer pieces: the floor test can't penalise
    reference: float = 0.0          # the yardstick for "X% under": book (vehicles), melt+gems (jewelry), comp (others)


def score(appraisal: Optional[Appraisal], cost: float, cushion: float = 0.0) -> Tuple[Bonus, List[str]]:
    """Same scoring for every domain: money back on the floor, upside on the estimate."""
    if appraisal is None:
        return [], []
    bonus: Bonus = list(appraisal.extra)
    facts = list(appraisal.facts)
    sure = appraisal.confidence
    if appraisal.floor and cost:
        pct = (appraisal.floor - cost) / cost
        facts.append(f"floor ${appraisal.floor:,.0f} vs cost ${cost:,.0f} ({pct:+.0%})")
        if pct >= cushion:
            bonus.append((int((40 + min(40, pct * 100)) * (0.5 + sure / 2)),
                          f"money back: breaks down to ${appraisal.floor:,.0f} vs ${cost:,.0f}"))
        elif pct < -0.15 and not appraisal.no_veto and sure >= 0.6:
            bonus.append((-30, f"break-down ${appraisal.floor:,.0f} is {-pct:.0%} short of ${cost:,.0f}"))
    elif appraisal.floor and not cost:
        bonus.append((int(25 * (0.5 + sure / 2)), f"breaks down to ~${appraisal.floor:,.0f}; no bid yet"))
    if appraisal.estimate and cost:
        upside = (appraisal.estimate - cost) / cost
        facts.append(f"est. ${appraisal.estimate:,.0f} whole ({upside:+.0%} vs cost, confidence {sure:.0%})")
        if upside >= 0.5:
            bonus.append((int(min(40, upside * 25) * sure), f"est. {upside:.0%} upside (${appraisal.estimate:,.0f} vs ${cost:,.0f})"))
    elif appraisal.estimate:
        facts.append(f"est. ${appraisal.estimate:,.0f} whole (confidence {sure:.0%})")
    return bonus, facts


Appraiser = Callable[..., Optional[Appraisal]]
REGISTRY: Dict[str, Appraiser] = {}


def register(domain: str):
    def wrap(fn: Appraiser) -> Appraiser:
        REGISTRY[domain] = fn
        return fn
    return wrap


def _load() -> None:
    """Import the built-in appraisers so they register themselves."""
    from . import electronics, equipment, jewelry, vehicle
    assert electronics and equipment and jewelry and vehicle


def detect(text: str) -> Optional[str]:
    """Which appraiser fits this listing text? Equipment first (a dump truck is equipment), then vehicles, then jewelry."""
    _load()
    for domain in ("equipment", "vehicle", "electronics", "jewelry"):
        if REGISTRY[domain].__dict__.get("matches", lambda _t: False)(text):
            return domain
    return None


def appraise(text: str, cost: float = 0.0, domain: Optional[str] = None, **settings) -> Optional[Appraisal]:
    _load()
    domain = domain or detect(text)
    if not domain or domain not in REGISTRY:
        return None
    return REGISTRY[domain](text, cost=cost, **settings)
