"""Live spot prices for the melt test.

v0 read spot from SILVER_SPOT_USD / GOLD_SPOT_USD by hand. When those were
blank, every listing said "no spot price set" and nothing was flagged on metal.
This fills the blanks from a free, no-key feed (gold-api.com) so the hunter
works on its own.

Order of trust, per metal:
  1. a number set by hand in config/env (Vinny's override always wins)
  2. a fresh live price (cached ``ttl_minutes`` so a sweep makes one call)
  3. the last good live price, if under ``stale_hours`` old (noted as stale)
  4. nothing: that metal is left out and the appraiser says so

Prices outside sane bounds are rejected rather than trusted: a bad tick that
read gold at $40 would make every chain look like a steal.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional, Tuple

from .http import Fetch, fetch as default_fetch

FEED = "https://api.gold-api.com/price/{symbol}"
SYMBOLS = {"gold": "XAU", "silver": "XAG"}
# USD per troy ounce. Wide on purpose: catches feed garbage, not real moves.
BOUNDS = {"gold": (500.0, 25000.0), "silver": (5.0, 1000.0)}


def _number(value) -> Optional[float]:
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _sane(metal: str, price: Optional[float]) -> bool:
    low, high = BOUNDS[metal]
    return price is not None and low <= price <= high


class SpotFeed:
    def __init__(self, fetcher: Optional[Fetch] = None, cache_path: str = "var/spot.json",
                 ttl_minutes: float = 15, stale_hours: float = 24, clock=time.time):
        self.fetch = fetcher or default_fetch
        self.cache_path = cache_path
        self.ttl = ttl_minutes * 60
        self.stale = stale_hours * 3600
        self.clock = clock
        self.notes: Dict[str, str] = {}

    # -- cache -------------------------------------------------------------
    def _read_cache(self) -> Dict[str, Dict[str, float]]:
        try:
            with open(self.cache_path, encoding="utf-8") as handle:
                data = json.load(handle)
            return {m: v for m, v in data.items() if m in SYMBOLS and _sane(m, _number(v.get("price")))}
        except (OSError, ValueError, AttributeError):
            return {}

    def _write_cache(self, cache: Dict[str, Dict[str, float]]) -> None:
        try:
            folder = os.path.dirname(self.cache_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as handle:
                json.dump(cache, handle, indent=2)
        except OSError:
            pass  # a read-only disk must not stop a sweep

    # -- live --------------------------------------------------------------
    def _live(self, metal: str) -> Optional[float]:
        try:
            reply = self.fetch(FEED.format(symbol=SYMBOLS[metal]), headers={"Accept": "application/json"},
                               timeout=15, retries=1)
            if reply.status != 200:
                return None
            price = _number((reply.json() or {}).get("price"))
        except Exception:  # network, JSON, a test double that doesn't know this URL
            return None
        return price if _sane(metal, price) else None

    def prices(self, metals=tuple(SYMBOLS)) -> Dict[str, float]:
        """Live (or cached) USD/ozt for each metal it can vouch for."""
        now = self.clock()
        cache = self._read_cache()
        out: Dict[str, float] = {}
        changed = False
        for metal in metals:
            held = cache.get(metal)
            age = now - float(held.get("at", 0)) if held else None
            if held and age is not None and age < self.ttl:
                out[metal] = float(held["price"])
                self.notes[metal] = "live (cached)"
                continue
            price = self._live(metal)
            if price is not None:
                out[metal] = round(price, 2)
                cache[metal] = {"price": round(price, 2), "at": now}
                self.notes[metal] = "live"
                changed = True
            elif held and age is not None and age < self.stale:
                out[metal] = float(held["price"])
                self.notes[metal] = f"stale, {age / 3600:.1f}h old (feed down)"
            else:
                self.notes[metal] = "unavailable"
        if changed:
            self._write_cache(cache)
        return out


def resolve(manual: Optional[Dict[str, object]], feed: Optional[SpotFeed]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Merge hand-set spot with live spot. Hand-set wins per metal."""
    spot: Dict[str, float] = {}
    source: Dict[str, str] = {}
    for metal, value in (manual or {}).items():
        number = _number(value)
        if number is not None:
            spot[metal] = number
            source[metal] = "set by hand"
    missing = [m for m in SYMBOLS if m not in spot]
    if missing and feed is not None:
        live = feed.prices(missing)
        for metal in missing:
            if metal in live:
                spot[metal] = live[metal]
            source[metal] = feed.notes.get(metal, "unavailable")
    return spot, source


def feed_from_config(config: Dict[str, object], fetcher: Optional[Fetch] = None) -> Optional[SpotFeed]:
    """``spot_feed`` block in the config; on unless enabled is false or SPOT_FEED=off."""
    opts = dict(config.get("spot_feed") or {})
    if str(os.environ.get("SPOT_FEED", "")).lower() in ("off", "0", "false", "no"):
        return None
    if opts.get("enabled") is False or str(opts.get("enabled", "")).lower() in ("false", "off", "0"):
        return None
    return SpotFeed(fetcher, cache_path=str(opts.get("cache") or "var/spot.json"),
                    ttl_minutes=float(opts.get("ttl_minutes") or 15),
                    stale_hours=float(opts.get("stale_hours") or 24))
