"""Jewelry & bullion appraiser: adapter over :mod:`leads.valuation`.

Floor = gram weight melted at spot + gem value (Vinny's value test).
Designer/period pieces: the floor can't veto (worth more whole).
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from .. import valuation
from . import Appraisal, register


def matches(text: str) -> bool:
    text = text.lower()
    return bool(re.search(r"\b(?:gold|silver|sterling|925|14k|10k|18k|platinum|jewelry|jewellery|ring|necklace|"
                          r"bracelet|earrings?|brooch|diamond|sapphire|ruby|emerald|coin|bullion)\b", text))


@register("jewelry")
def appraise(text: str, cost: float = 0.0, spot: Optional[Dict[str, float]] = None,
             recovery: Optional["valuation.Recovery"] = None, **_) -> Optional[Appraisal]:
    recovery = recovery or valuation.Recovery()
    spot = spot or {}
    metal = valuation.read_metal(text)
    gem = valuation.read_gem(text)
    melt = metal.melt(spot) if metal else None
    metal_value = round((melt or 0) * recovery.payout.get(metal.metal, 1.0), 2) if metal else 0.0
    stones, stone_note = valuation.gem_value(gem, recovery.stone_per_ct, recovery.gem_factors)
    if not metal and not stones:
        return None
    facts = []
    if metal:
        facts.append(f"{metal.ozt:g} ozt {metal.metal} ({metal.basis})" + (f", melt ${melt:,.2f}" if melt else ", no spot set"))
    if stone_note:
        facts.append(stone_note)
    designer = valuation._words(" " + text.lower() + " ", valuation.DESIGNERS)
    confidence = 0.5 if (metal and metal.estimated) else 0.8
    extra = [(10, f"designer/period '{designer[0]}': worth more whole, check sold comps")] if designer else []
    return Appraisal("jewelry", metal.basis if metal else (gem.stone or "gem"), floor=round(metal_value + stones, 2),
                     confidence=confidence, facts=facts, extra=extra, no_veto=bool(designer))


appraise.matches = matches
