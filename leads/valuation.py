"""What's in it? Title-reading valuation for silver, gold and gemstones.

Everything here is a *reading of the title*, not an appraisal: it finds a
weight, a purity or a known coin, and turns that into troy ounces of pure
metal. Melt value is then ozt × spot. When the title doesn't say enough, it
returns nothing rather than guessing, and a human decides.

Troy ounce = 31.1035 g · pennyweight (dwt) = 1.55517 g.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

GRAMS_PER_OZT = 31.1034768
GRAMS_PER_DWT = 1.55517384

# Words that mean "not the real metal / not a natural stone". Whole-word matches.
METAL_FAKES = [
    "plated", "plate", "silverplate", "silverplated", "electroplate", "electroplated", "epns", "ep",
    "gold filled", "gold-filled", "gf", "rolled gold", "rgp", "hge", "hgp", "vermeil",
    "gold tone", "goldtone", "silver tone", "silvertone", "nickel silver", "german silver",
    "tibetan silver", "tibet silver", "alpaca", "clad", "replica", "copy", "fake", "tribute",
    "costume", "wash", "overlay", "bonded", "weighted", "reinforced",
]
GEM_FAKES = [
    "lab created", "lab-created", "lab grown", "lab-grown", "created", "simulated", "simulant",
    "synthetic", "cz", "cubic zirconia", "moissanite", "glass", "imitation", "faux", "diamonique",
    "costume", "crystal", "rhinestone", "resin", "acrylic", "dyed",
]
# Common misspellings: listings other buyers' searches miss.
MISSPELLINGS = {
    "sterlng": "sterling", "sterlin": "sterling", "sterliing": "sterling", "stirling": "sterling",
    "silvr": "silver", "sliver": "silver", "silber": "silver", "golde": "gold", "gld": "gold",
    "saphire": "sapphire", "sapphre": "sapphire", "saphhire": "sapphire", "emrald": "emerald",
    "emerld": "emerald", "emarald": "emerald", "rubie": "ruby", "diamnd": "diamond",
    "dimond": "diamond", "daimond": "diamond", "tanzinite": "tanzanite", "tanznite": "tanzanite",
    "alexandrit": "alexandrite", "opel": "opal", "aquamarin": "aquamarine",
}
STONES = ["sapphire", "ruby", "emerald", "diamond", "opal", "tanzanite", "alexandrite", "spinel",
          "garnet", "aquamarine", "tourmaline", "topaz", "amethyst", "jade", "morganite", "peridot"]
CERTS = ["gia", "ags", "igi", "gcal", "agl", "grs", "gubelin", "ssef", "egl"]

# Actual silver / gold weight (troy oz) per coin.
SILVER_COINS = [
    (r"\bmorgan\b", 0.7734, "Morgan dollar"),
    (r"\bpeace dollar\b", 0.7734, "Peace dollar"),
    (r"\b(?:silver eagle|ase)\b", 1.0, "American Silver Eagle"),
    (r"\bsilver maple\b", 1.0, "Silver Maple Leaf"),
    (r"\bwalking liberty\b", 0.3617, "Walking Liberty half"),
    (r"\bfranklin half\b", 0.3617, "Franklin half"),
    (r"\b1964\b.*\bkennedy\b|\bkennedy\b.*\b1964\b", 0.3617, "1964 Kennedy half"),
    (r"\b40%.*\bkennedy\b|\bkennedy\b.*\b40%|\b19(?:6[5-9]|70)\b.*\bkennedy\b", 0.1479, "40% Kennedy half"),
    (r"\bmercury dime\b", 0.0723, "Mercury dime"),
    (r"\bwar nickel\b", 0.0563, "War nickel"),
]
GOLD_COINS = [
    (r"\b(?:double eagle|\$20 (?:gold|liberty|saint)|saint[- ]gaudens)\b", 0.9675, "$20 Double Eagle"),
    (r"\$10 (?:gold|liberty|indian)\b", 0.48375, "$10 Eagle"),
    (r"\$5 (?:gold|liberty|indian)\b", 0.24187, "$5 Half Eagle"),
    (r"\$2\.5\b|\bquarter eagle\b", 0.12094, "$2.50 Quarter Eagle"),
    (r"\bsovereign\b", 0.2354, "British Sovereign"),
    (r"\bkrugerrand\b", 1.0, "Krugerrand"),
    (r"\bgold (?:american )?eagle\b|\bamerican gold eagle\b", 1.0, "American Gold Eagle"),
    (r"\bgold (?:american )?buffalo\b", 1.0, "Gold Buffalo"),
    (r"\bgold maple\b", 1.0, "Gold Maple Leaf"),
]
KARATS = {"24": 0.999, "22": 0.9167, "18": 0.750, "14": 0.585, "10": 0.417}
FINENESS = {"999": ("silver", 0.999), "925": ("silver", 0.925), "900": ("silver", 0.900),
            "800": ("silver", 0.800), "750": ("gold", 0.750), "585": ("gold", 0.585),
            "417": ("gold", 0.417), "916": ("gold", 0.9167)}

_NUM = r"(\d+(?:\.\d+)?|\d+/\d+)"


def _words(text: str, terms: List[str]) -> List[str]:
    return [t for t in terms if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", text)]


def _number(raw: str) -> float:
    if "/" in raw:
        top, bottom = raw.split("/", 1)
        return float(top) / float(bottom) if float(bottom) else 0.0
    return float(raw)


def quantity(text: str) -> int:
    for pattern in (r"\blot of\s*(\d+)\b", r"\bqty\.?\s*:?\s*(\d+)\b", r"\b(\d+)\s*(?:pcs|pieces|coins)\b",
                    r"\(\s*(\d+)\s*\)", r"\bx\s*(\d+)\b", r"\b(\d+)\s*x\b"):
        match = re.search(pattern, text)
        if match and 1 < int(match.group(1)) <= 1000:
            return int(match.group(1))
    return 1


@dataclass
class Metal:
    metal: str                  # "silver" | "gold"
    ozt: float                  # troy ounces of pure metal
    basis: str                  # how we got there, in words

    def melt(self, spot: Dict[str, float]) -> Optional[float]:
        price = spot.get(self.metal)
        return round(self.ozt * price, 2) if price else None


@dataclass
class Gem:
    stone: Optional[str] = None
    carats: Optional[float] = None
    certified: Optional[str] = None
    signals: List[str] = field(default_factory=list)


def read_metal(title: str) -> Optional[Metal]:
    """Troy ounces of silver or gold that the title says are in the item, or None."""
    text = " " + title.lower() + " "
    if _words(text, METAL_FAKES):
        return None
    for fixed, right in MISSPELLINGS.items():
        text = re.sub(r"\b" + fixed + r"\b", right, text)
    qty = quantity(text)

    # 1. Known coins (the surest reading).
    for coins, metal in ((GOLD_COINS, "gold"), (SILVER_COINS, "silver")):
        for pattern, ozt, name in coins:
            if re.search(pattern, text):
                size = re.search(r"\b(1/2|1/4|1/10|1/20)\s*(?:oz|ozt)\b", text)
                factor = _number(size.group(1)) if size and ozt == 1.0 else 1.0
                return Metal(metal, round(ozt * factor * qty, 4),
                             f"{qty} × {name}" + (f" ({size.group(1)} oz)" if factor != 1.0 else ""))

    # 2. Junk silver by face value.
    face = re.search(r"\$\s?(\d+(?:\.\d{2})?)\s*(?:face|fv)\b", text)
    if face and ("90%" in text or "junk" in text or "pre-1965" in text or "pre 1965" in text):
        dollars = float(face.group(1))
        return Metal("silver", round(dollars * 0.715, 4), f"${dollars:g} face of 90% silver")

    # 3. Purity + weight. Text can mention several metals ("14k jewelry, sterling
    #    flatware 1200 grams"), so each weight is paired with the purity mention
    #    nearest to it, never just the first one found.
    marks = []  # (position, metal, purity, label)
    for m in re.finditer(r"\b(10|14|18|22|24)\s?k(?:t|arat)?\b", text):
        marks.append((m.start(), "gold", KARATS[m.group(1)], f"{m.group(1)}k gold"))
    for m in re.finditer(r"\bsterling\b", text):
        marks.append((m.start(), "silver", 0.925, "925 silver"))
    for m in re.finditer(r"\bcoin silver\b", text):
        marks.append((m.start(), "silver", 0.900, "900 silver"))
    for m in re.finditer(r"\bfine silver\b", text):
        marks.append((m.start(), "silver", 0.999, "999 silver"))
    for m in re.finditer(r"(?<![\d.$])\.?(999|925|900|800|750|585|417|916)(?![\d])", text):
        metal, purity = FINENESS[m.group(1)]
        if m.group(1) == "999":  # fine gold or fine silver: let the nearest metal word decide
            words = [(abs(w.start() - m.start()), w.group(1)) for w in re.finditer(r"\b(gold|silver)\b", text)]
            if not words:
                continue  # a bare .999 names no metal
            metal = min(words)[1]
        marks.append((m.start(), metal, purity, f"{m.group(1)} {metal}"))
    if not marks:
        return None
    weights = []  # (position, grams, how, bullion_oz)
    for m in re.finditer(_NUM + r"\s*(?:g|gr|grams?|gm|gms)\b", text):
        weights.append((m.start(), _number(m.group(1)), f"{m.group(1)} g", False))
    for m in re.finditer(_NUM + r"\s*dwt\b", text):
        weights.append((m.start(), _number(m.group(1)) * GRAMS_PER_DWT, f"{m.group(1)} dwt", False))
    for m in re.finditer(_NUM + r"\s*(?:ozt|troy\s*oz|troy\s*ounces?)\b", text):
        weights.append((m.start(), _number(m.group(1)) * GRAMS_PER_OZT, f"{m.group(1)} ozt", False))
    for m in re.finditer(_NUM + r"\s*(?:oz|ounces?)\b(?!t)", text):
        weights.append((m.start(), _number(m.group(1)) * GRAMS_PER_OZT, f"{m.group(1)} oz", True))
    for position, grams, how, bullion in weights:
        nearest = min(marks, key=lambda mark: abs(mark[0] - position))
        _, metal, purity, label = nearest
        if bullion and purity < 0.999:
            continue  # a plain "oz" on jewelry is usually avoirdupois; only trust it for bullion
        if not grams:
            continue
        ozt = grams / GRAMS_PER_OZT * purity * qty
        return Metal(metal, round(ozt, 4), f"{qty} × {how} of {label}" if qty > 1 else f"{how} of {label}")
    return None


def read_gem(title: str) -> Gem:
    text = " " + title.lower() + " "
    gem = Gem()
    if _words(text, GEM_FAKES):
        gem.signals.append("fake")
        return gem
    spelled = [f"{wrong}→{right}" for wrong, right in MISSPELLINGS.items() if re.search(r"\b" + wrong + r"\b", text)]
    if spelled:
        gem.signals.append("misspelled: " + ", ".join(spelled))
    for fixed, right in MISSPELLINGS.items():
        text = re.sub(r"\b" + fixed + r"\b", right, text)
    gem.stone = next((s for s in STONES if re.search(r"\b" + s + r"s?\b", text)), None)
    carat = re.search(_NUM + r"\s*(?:ct|cts|carats?|cttw|ctw|tcw)\b", text)
    if carat:
        gem.carats = _number(carat.group(1))
    cert = _words(text, CERTS)
    if cert:
        gem.certified = cert[0].upper()
    return gem


def misspelled(title: str) -> List[str]:
    text = title.lower()
    return [f"{w}→{r}" for w, r in MISSPELLINGS.items() if re.search(r"\b" + w + r"\b", text)]


def metal_bonus(text: str, cost: float, spot: Dict[str, float], margin: float = 0.10):
    """(bonus list, facts list) for any listing text + price: shared by eBay, GSA and estate listeners."""
    bonus, facts = [], []
    metal = read_metal(text)
    if not metal:
        return bonus, facts
    facts.append(f"{metal.ozt:g} ozt {metal.metal} ({metal.basis})")
    melt = metal.melt(spot)
    if not melt:
        facts.append(f"no {metal.metal} spot price set")
        bonus.append((10, f"{metal.metal} content stated"))
        return bonus, facts
    facts.append(f"melt ${melt:,.2f}" + (f" vs ${cost:,.2f}" if cost else ""))
    if not cost:
        bonus.append((25, f"{metal.metal} worth ~${melt:,.0f} melt, no bid yet"))
        return bonus, facts
    under = (melt - cost) / melt
    if under >= margin:
        bonus.append((40 + min(40, int(under * 100)), f"{under:.0%} under melt"))
    elif under < 0:
        bonus.append((-30, f"{-under:.0%} over melt"))
    return bonus, facts


# -- mispriced jewelry --------------------------------------------------------
# The seller may not know what they have. Could be a steal; could be a fake.
SELLER_UNSURE = [
    "unmarked", "untested", "not tested", "not sure if real", "unsure if real", "don't know if real",
    "dont know if real", "may be gold", "might be gold", "may be silver", "might be silver", "tests as gold",
    "tested gold", "acid tested", "tests as silver", "tests positive", "no hallmark", "unknown metal",
    "grandma's", "grandmas", "grandmother's", "junk drawer", "unsearched", "unsorted", "found in estate",
    "estate find", "storage unit", "barn find", "as is", "don't know much", "no idea",
]
DESIGNERS = [
    "tiffany", "cartier", "david yurman", "yurman", "georg jensen", "van cleef", "bulgari", "bvlgari",
    "john hardy", "lagos", "mikimoto", "harry winston", "chanel", "hermes", "buccellati", "kieselstein",
    "elsa peretti", "paloma picasso", "spratling", "navajo", "zuni", "taxco", "art deco", "victorian", "edwardian",
]
FINE_MARKS = r"\b(?:10|14|18|22|24)\s?k(?:t|arat)?\b|\bsterling\b|\b925\b|\b585\b|\b750\b|\bplatinum\b|\bpt950\b"


def jewelry_clues(title: str, categories: List[str]) -> List[tuple]:
    """Evidence points for a jewelry listing being mispriced. Returns [(points, reason)]."""
    text = " " + title.lower() + " "
    clues = []
    unsure = _words(text, SELLER_UNSURE)
    if unsure:
        clues.append((20, f"seller unsure ({unsure[0]}): steal or fake, check photos"))
    marked = re.search(FINE_MARKS, text)
    cats = " ".join(categories).lower()
    if marked and any(c in cats for c in ("fashion", "costume", "vintage & antique jewelry > costume")):
        clues.append((25, f"'{marked.group(0).strip()}' listed under {categories[-1] if categories else 'fashion/costume'}"))
    designer = _words(text, DESIGNERS)
    if designer:
        clues.append((10, f"designer/period '{designer[0]}': verify, fakes are common"))
    if re.search(r"\bplatinum\b|\bpt ?950\b|\bpt ?900\b", text):
        clues.append((10, "platinum mentioned"))
    return clues
