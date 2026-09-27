"""Surplus listener: GSA Auctions (government surplus), official API. Virginia is a hotbed.

Every lot goes through the appraisers (jewelry, vehicle, equipment; picked
automatically from the lot text) and gets the same money-back / upside scoring.

Part of the bid system's repurposing for estate sales: the same "find the lot
before others do" job, pointed at precious metals, jewelry and coins instead
of painting contracts. GSA Auctions publishes every federal surplus lot
through ``api.gsa.gov`` with an api.data.gov key (``DEMO_KEY`` works for a
trial, with low limits). Rate limit: 5,000 calls/day, 5 per 5 seconds; one
call per sweep.

Read-only. Registering and bidding on gsaauctions.gov is Vinny's, by hand.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from ..http import Fetch, fetch as default_fetch
from ..model import Lead, clean
from .. import valuation
from .. import appraisers
from ..appraisers import comps as comps_module

ENDPOINT = "https://api.gsa.gov/assets/gsaauctions/v2/auctions"


def _rows(data: Any) -> List[Dict]:
    """The API wraps its list in a key; take the first list of dicts we find."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for value in data.values():
            rows = _rows(value)
            if rows:
                return rows
    return []


class _Caseless(dict):
    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


def _money(value: Any) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


class GsaAuctionsListener:
    kind = "gsa_auctions"

    def __init__(self, name: str, api_key: str = "DEMO_KEY", states: Optional[List[str]] = None,
                 spot: Optional[Dict[str, Any]] = None, margin: float = 0.10, fetcher: Optional[Fetch] = None,
                 recovery: Optional["valuation.Recovery"] = None, appraiser: str = "auto",
                 scrap_per_ton: float = 180.0, cat_value: float = 100.0, comps_csv: Optional[str] = None):
        self.name = name
        self.api_key = api_key or "DEMO_KEY"
        self.states = {s.upper() for s in (states or []) if s}
        self.spot = {k: float(v) for k, v in (spot or {}).items() if str(v).strip()}
        self.margin = margin
        self.recovery = recovery or valuation.Recovery()
        self.appraiser = None if appraiser in ("", "auto") else appraiser
        self.settings = {"spot": self.spot, "recovery": self.recovery, "scrap_per_ton": scrap_per_ton,
                         "cat_value": cat_value, "comps": comps_module.load(comps_csv)}
        self.fetch = fetcher or default_fetch
        self.errors: List[str] = []

    def listen(self) -> Iterator[Lead]:
        self.errors = []
        try:
            data = self.fetch(f"{ENDPOINT}?api_key={self.api_key}&format=JSON").json()
        except Exception as error:
            self.errors.append(str(error))
            return
        for raw in _rows(data):
            # The live API answers in camelCase (itemName) while the docs say ItemName: match either.
            row = {str(k).lower(): v for k, v in raw.items()}
            row = _Caseless(row)
            state = str(row.get("PropertyState") or row.get("LocationST") or "").upper()
            if self.states and state and state not in self.states:
                continue
            status = str(row.get("AuctionStatus") or "").strip().upper()[:1]   # live: "Active"/"Preview"; docs: A/P
            if status not in ("A", "P", ""):
                continue
            text = " ".join(clean(row.get(k)) for k in ("ItemName", "LotDescript"))
            high = _money(row.get("HighBidAmount"))
            appraisal = appraisers.appraise(text, high, self.appraiser, **self.settings)
            bonus, facts = appraisers.score(appraisal, high, self.recovery.cushion)
            yield Lead(
                source=self.name,
                external_id=f"{row.get('SaleNo')}-{row.get('LotNo')}",
                title=clean(row.get("ItemName"), 200) or f"GSA lot {row.get('SaleNo')}-{row.get('LotNo')}",
                channel="Open Boards", medium="Board Scraping",
                body=" · ".join(facts + [clean(row.get("LotDescript"), 1200),
                                         f"high bid ${high:,.2f}", f"{row.get('BiddersCount') or 0} bidders"]),
                url=row.get("ItemDescURL") or "",
                contact=f"GSA · {clean(row.get('AgencyName'))}",
                location=", ".join(x for x in (clean(row.get("PropertyCity")), state) if x),
                value=high, deadline=str(row.get("AucEndDt") or ""), posted_at=str(row.get("AucStartDt") or ""),
                tags=["gsa", "auction"] + ([appraisal.domain] if appraisal else []), bonus=bonus,
                raw={"sale": row.get("SaleNo"), "lot": row.get("LotNo"), "image": row.get("ImageURL")},
            )
