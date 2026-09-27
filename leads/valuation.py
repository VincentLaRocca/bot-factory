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
    estimated: bool = False     # True when the weight is a typical-weight guess, not stated

    def melt(self, spot: Dict[str, float]) -> Optional[float]:
        price = spot.get(self.metal)
        return round(self.ozt * price, 2) if price else None


@dataclass
class Gem:
    stone: Optional[str] = None
    carats: Optional[float] = None
    certified: Optional[str] = None
    signals: List[str] = field(default_factory=list)
    natural: Optional[bool] = None      # True natural/genuine/mined, False lab/synthetic/created, None unstated
    clarity: Optional[str] = None       # diamond grade (VS1…) or a coloured-stone word (eye clean…)
    color: Optional[str] = None         # diamond letter (D–M) or a coloured-stone word (vivid, royal blue…)
    treatment: Optional[str] = None     # heated, filled, diffused… (or "untreated")


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

    # 4. No weight stated: guesstimate from what the item is (low-end typical weights).
    guess = estimate_grams(text)
    if guess:
        grams, item = guess
        _, metal, purity, label = marks[0]
        ozt = grams / GRAMS_PER_OZT * purity * qty
        how = f"~{grams:g} g est. {item}"
        return Metal(metal, round(ozt, 4), f"{qty} × {how} of {label}" if qty > 1 else f"{how} of {label}",
                     estimated=True)
    return None


# Typical weights, deliberately at the LOW end, so a guess never flatters a listing.
# Checked in order: more specific items first.
TYPICAL_GRAMS = [
    (r"\bclass ring\b", 7.0, "class ring"),
    (r"\b(?:men'?s|mens|gents?)\b.*\b(?:ring|band)\b|\bsignet\b", 6.0, "men's ring"),
    (r"\bwedding band\b|\bband\b", 3.0, "band"),
    (r"\bring\b", 2.5, "ring"),
    (r"\b(?:cuban|curb|figaro|franco|miami)\b.*\bchain\b", 10.0, "link chain"),
    (r"\brope chain\b", 6.0, "rope chain"),
    (r"\bchain\b|\bnecklace\b", 4.0, "chain"),
    (r"\bcuff\b", 20.0, "cuff"),
    (r"\bbangle\b", 7.0, "bangle"),
    (r"\btennis bracelet\b", 7.0, "tennis bracelet"),
    (r"\bbracelet\b", 5.0, "bracelet"),
    (r"\bhoop\b", 2.5, "hoop earrings"),
    (r"\bearring\b|\bstud\b", 1.5, "earrings"),
    (r"\bpendant\b|\bcharm\b|\blocket\b|\bcross\b", 2.0, "pendant/charm"),
    (r"\bbrooch\b|\bpin\b", 5.0, "brooch"),
    (r"\bcufflink\b", 6.0, "cufflinks"),
    (r"\btablespoon\b|\bserving spoon\b", 45.0, "serving spoon"),
    (r"\bteaspoon\b", 20.0, "teaspoon"),
    (r"\bspoon\b", 25.0, "spoon"),
    (r"\bfork\b", 35.0, "fork"),
    (r"\bnapkin ring\b", 15.0, "napkin ring"),
    (r"\bmoney clip\b", 12.0, "money clip"),
]


def estimate_grams(text: str):
    """(grams, item) from a low-end typical-weight table, or None."""
    no_s = re.sub(r"\b(\w{3,})s\b", r"\1", text)       # "spoons" → "spoon", "bangles" → "bangle"
    no_es = re.sub(r"\b(\w{3,})es\b", r"\1", text)     # "brooches" → "brooch"
    for pattern, grams, item in TYPICAL_GRAMS:
        if any(re.search(pattern, t) for t in (text, no_s, no_es)):
            return grams, item
    return None


SIMULANTS = ["simulated", "simulant", "cz", "cubic zirconia", "glass", "imitation", "faux", "diamonique",
             "costume", "crystal", "rhinestone", "resin", "acrylic", "plastic", "paste"]
SYNTHETICS = ["lab created", "lab-created", "lab grown", "lab-grown", "created", "synthetic", "man made",
              "man-made", "cultured diamond", "cvd", "hpht", "moissanite"]
NATURAL_WORDS = ["natural", "genuine", "mined", "earth mined", "earth-mined", "real"]
DIAMOND_CLARITY = ["fl", "if", "vvs1", "vvs2", "vvs", "vs1", "vs2", "vs", "si1", "si2", "si3", "si", "i1", "i2", "i3"]
STONE_CLARITY = ["eye clean", "loupe clean", "transparent", "translucent", "included", "heavily included", "opaque", "cloudy"]
STONE_COLOR = ["pigeon blood", "royal blue", "cornflower", "padparadscha", "vivid", "intense", "deep", "rich",
               "medium", "light", "pale", "dark"]
TREATMENTS = ["untreated", "no heat", "unheated", "heated", "heat treated", "oiled", "minor oil", "filled",
              "glass filled", "lead glass", "fracture filled", "diffused", "diffusion", "irradiated", "dyed",
              "coated", "enhanced", "treated"]


def read_gem(title: str) -> Gem:
    text = " " + title.lower() + " "
    gem = Gem()
    # "glass filled" / "lead glass" rubies are real (heavily treated) stones, not glass
    if _words(re.sub(r"glass[- ]filled|lead[- ]glass", " ", text), SIMULANTS):
        gem.signals.append("fake")          # not a gemstone at all
        return gem
    spelled = [f"{wrong}→{right}" for wrong, right in MISSPELLINGS.items() if re.search(r"\b" + wrong + r"\b", text)]
    if spelled:
        gem.signals.append("misspelled: " + ", ".join(spelled))
    for fixed, right in MISSPELLINGS.items():
        text = re.sub(r"\b" + fixed + r"\b", right, text)
    gem.stone = next((st for st in STONES if re.search(r"\b" + st + r"s?\b", text)), None)
    if _words(text, SYNTHETICS):
        gem.natural = False
        gem.signals.append("synthetic")
        if "moissanite" in text:
            gem.stone = gem.stone or "moissanite"
    elif _words(text, NATURAL_WORDS):
        gem.natural = True
    carat = re.search(_NUM + r"\s*(?:ct|cts|carats?|cttw|ctw|tcw)\b", text)
    if carat:
        gem.carats = _number(carat.group(1))
    cert = _words(text, CERTS)
    if cert:
        gem.certified = cert[0].upper()
    clarity = _words(text, STONE_CLARITY) or _words(text, DIAMOND_CLARITY)
    if clarity:
        gem.clarity = clarity[0]
    letter = re.search(r"\b([d-m])\s*(?:color|colour)\b|\b(?:color|colour)\s*:?\s*([d-m])\b"
                       r"|\b([d-m])\s*[/,]?\s*(?:fl|if|vvs\d?|vs\d?|si\d?|i\d)\b", text)
    if letter:
        gem.color = next(g for g in letter.groups() if g)
    else:
        words = _words(text, STONE_COLOR)
        if words:
            gem.color = max(words, key=len)
    treatment = _words(text, TREATMENTS)
    if treatment:
        gem.treatment = max(treatment, key=len)   # "glass filled" beats "filled"
    return gem


# Price-per-carat multipliers. Vinny sets the BASE $/ct per stone (a clean,
# natural, untreated, ~1 ct stone of ordinary color); these adjust it. All are
# overridable in the hunt config ("gem_factors").
GEM_FACTORS = {
    "synthetic": 0.03,          # lab/created stones: a few % of natural
    "unstated_origin": 0.6,     # neither "natural" nor "lab" stated: discount the doubt
    "certified": 1.15,
    "size": [(0.5, 0.6), (1.0, 1.0), (2.0, 1.5), (3.0, 2.0), (99, 2.6)],   # (up to ct, x per-ct price)
    "clarity": {"fl": 2.0, "if": 1.8, "vvs1": 1.5, "vvs2": 1.4, "vvs": 1.4, "vs1": 1.2, "vs2": 1.1, "vs": 1.1,
                "si1": 0.9, "si2": 0.75, "si3": 0.6, "si": 0.8, "i1": 0.5, "i2": 0.35, "i3": 0.25,
                "eye clean": 1.2, "loupe clean": 1.4, "transparent": 1.1, "translucent": 0.6,
                "included": 0.6, "heavily included": 0.35, "opaque": 0.2, "cloudy": 0.4},
    "color": {"d": 1.6, "e": 1.5, "f": 1.4, "g": 1.25, "h": 1.1, "i": 1.0, "j": 0.9, "k": 0.75, "l": 0.65, "m": 0.55,
              "pigeon blood": 2.5, "royal blue": 2.2, "cornflower": 1.8, "padparadscha": 2.5, "vivid": 1.6,
              "intense": 1.3, "deep": 1.2, "rich": 1.2, "medium": 1.0, "light": 0.7, "pale": 0.5, "dark": 0.6},
    "treatment": {"untreated": 1.5, "no heat": 1.5, "unheated": 1.5, "heated": 1.0, "heat treated": 1.0,
                  "minor oil": 1.0, "oiled": 0.9, "enhanced": 0.7, "treated": 0.7, "irradiated": 0.6,
                  "coated": 0.3, "dyed": 0.2, "diffused": 0.2, "diffusion": 0.2, "filled": 0.15,
                  "glass filled": 0.05, "lead glass": 0.05, "fracture filled": 0.3},
}


def gem_value(gem: Gem, base_per_ct: Dict[str, float], factors: Optional[Dict] = None):
    """(value, explanation) for a stone: carats x base $/ct x size x clarity x color x treatment x origin x cert.

    Returns (0, reason) when there's nothing to value (no base price set, no carat weight, a simulant).
    """
    f = {**GEM_FACTORS, **(factors or {})}
    if "fake" in gem.signals:
        return 0.0, "simulant: no gem value"
    if not gem.stone or not gem.carats:
        return 0.0, ""
    base = base_per_ct.get(gem.stone, 0.0)
    if not base:
        return 0.0, f"{gem.carats:g} ct {gem.stone}: no base $/ct set"
    per_ct, why = base, [f"base ${base:,.0f}/ct"]
    size = next(mult for limit, mult in f["size"] if gem.carats <= limit)
    if size != 1.0:
        per_ct *= size
        why.append(f"size x{size:g}")
    for key, value in (("clarity", gem.clarity), ("color", gem.color), ("treatment", gem.treatment)):
        mult = f[key].get(value) if value else None
        if mult and mult != 1.0:
            per_ct *= mult
            why.append(f"{value} x{mult:g}")
    if gem.natural is False:
        per_ct *= f["synthetic"]
        why.append(f"synthetic x{f['synthetic']:g}")
    elif gem.natural is None:
        per_ct *= f["unstated_origin"]
        why.append(f"origin unstated x{f['unstated_origin']:g}")
    if gem.certified:
        per_ct *= f["certified"]
        why.append(f"{gem.certified} x{f['certified']:g}")
    value = round(gem.carats * per_ct, 2)
    return value, f"{gem.carats:g} ct {'natural' if gem.natural else 'lab' if gem.natural is False else ''} {gem.stone} ≈ ${value:,.0f} ({', '.join(why)})".replace("  ", " ")


def misspelled(title: str) -> List[str]:
    text = title.lower()
    return [f"{w}→{r}" for w, r in MISSPELLINGS.items() if re.search(r"\b" + w + r"\b", text)]


@dataclass
class Recovery:
    """Vinny's value test: if we broke it into its elements, would we get our money back?

    Vinny's version (kept simple on purpose): break-down value = the gram weight
    melted down at full spot, plus the gems' value. Cost = price + shipping.
    If break-down >= cost, we get our money back.

    Optional knobs, off by default: ``payout`` < 1 for what a refiner actually
    pays, ``tax_rate`` and ``fee`` on the cost side, and ``cushion`` to demand
    a margin above break-even.
    """

    payout: Dict[str, float] = field(default_factory=lambda: {"gold": 1.0, "silver": 1.0})
    stone_per_ct: Dict[str, float] = field(default_factory=dict)   # BASE $/ct per stone (see GEM_FACTORS)
    gem_factors: Dict = field(default_factory=dict)
    tax_rate: float = 0.0
    fee: float = 0.0
    cushion: float = 0.0           # 0 = money back at break-even

    @classmethod
    def from_config(cls, data: Optional[Dict] = None) -> "Recovery":
        data = dict(data or {})
        base = cls()
        payout = {**base.payout, **{k: float(v) for k, v in (data.get("payout") or {}).items() if str(v).strip()}}
        return cls(payout=payout,
                   stone_per_ct={k.lower(): float(v) for k, v in (data.get("stone_per_ct") or {}).items()},
                   gem_factors=dict(data.get("gem_factors") or {}),
                   tax_rate=float(data.get("tax_rate", base.tax_rate)), fee=float(data.get("fee", base.fee)),
                   cushion=float(data.get("cushion", base.cushion)))


def break_down(text: str, cost: float, spot: Dict[str, float], recovery: Optional[Recovery] = None,
               gem: Optional[Gem] = None):
    """Run the money-back test on a listing. Returns (bonus list, facts list).

    ``cost`` is price + shipping (0 = no bid yet). Shared by eBay, GSA and estate listeners.
    """
    recovery = recovery or Recovery()
    bonus, facts = [], []
    metal = read_metal(text)
    stones, stone_note = 0.0, ""
    if gem:
        stones, stone_note = gem_value(gem, recovery.stone_per_ct, recovery.gem_factors)
    if not metal and not stones:
        return bonus, facts
    metal_value = 0.0
    if metal:
        facts.append(f"{metal.ozt:g} ozt {metal.metal} ({metal.basis})")
        melt = metal.melt(spot)
        if not melt:
            facts.append(f"no {metal.metal} spot price set")
            bonus.append((10, f"{metal.metal} content stated"))
            if not stones:
                return bonus, facts
        else:
            metal_value = round(melt * recovery.payout.get(metal.metal, 1.0), 2)
            facts.append(f"melt ${melt:,.2f}" + (f" → payout ~${metal_value:,.2f}" if metal_value != melt else ""))
    if stone_note:
        facts.append(("gems " if stones else "") + stone_note)
    floor = round(metal_value + stones, 2)
    if not floor:
        return bonus, facts
    if not cost:
        bonus.append((25, f"breaks down to ~${floor:,.0f}; no bid yet"))
        return bonus, facts
    all_in = round(cost * (1 + recovery.tax_rate) + recovery.fee, 2)
    margin = floor - all_in
    pct = margin / all_in if all_in else 0.0
    if metal and metal.estimated:
        facts.append(f"break-down ~${floor:,.2f} (estimated weight) vs cost ${all_in:,.2f} ({pct:+.0%})")
        if pct >= recovery.cushion:
            bonus.append((20 + min(20, int(pct * 50)),
                          f"money back on estimated weight (~${floor:,.0f} vs ${all_in:,.0f}): confirm weight in photos/description"))
        return bonus, facts  # a guess never earns a penalty
    facts.append(f"break-down ${floor:,.2f} vs cost ${all_in:,.2f} ({pct:+.0%})")
    if pct >= recovery.cushion:
        bonus.append((40 + min(40, int(pct * 100)), f"money back: breaks down to ${floor:,.0f} vs ${all_in:,.0f} cost (+{pct:.0%})"))
    elif pct >= 0:
        bonus.append((15, f"money back, thin cushion (+${margin:,.0f})"))
    elif pct > -0.15:
        facts.append(f"short by ${-margin:,.0f}: only a buy for the piece itself")
    else:
        bonus.append((-30, f"break-down ${floor:,.0f} is {-pct:.0%} short of ${all_in:,.0f} cost"))
    return bonus, facts


def metal_bonus(text: str, cost: float, spot: Dict[str, float], margin: float = 0.10,
                recovery: Optional[Recovery] = None):
    """Back-compat wrapper around :func:`break_down`."""
    return break_down(text, cost, spot, recovery or Recovery())


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
