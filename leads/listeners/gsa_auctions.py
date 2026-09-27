"""Estate & surplus listener: GSA Auctions (government surplus), official API.

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


def _money(value: Any) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


class GsaAuctionsListener:
    kind = "gsa_auctions"

    def __init__(self, name: str, api_key: str = "DEMO_KEY", states: Optional[List[str]] = None,
                 spot: Optional[Dict[str, Any]] = None, margin: float = 0.10, fetcher: Optional[Fetch] = None,
                 recovery: Optional["valuation.Recovery"] = None):
        self.name = name
        self.api_key = api_key or "DEMO_KEY"
        self.states = {s.upper() for s in (states or []) if s}
        self.spot = {k: float(v) for k, v in (spot or {}).items() if str(v).strip()}
        self.margin = margin
        self.recovery = recovery or valuation.Recovery(cushion=margin)
        self.fetch = fetcher or default_fetch
        self.errors: List[str] = []

    def listen(self) -> Iterator[Lead]:
        self.errors = []
        try:
            data = self.fetch(f"{ENDPOINT}?api_key={self.api_key}&format=JSON").json()
        except Exception as error:
            self.errors.append(str(error))
            return
        for row in _rows(data):
            state = str(row.get("PropertyState") or row.get("LocationST") or "").upper()
            if self.states and state and state not in self.states:
                continue
            if str(row.get("AuctionStatus", "")).strip().upper() not in ("A", "P", ""):
                continue
            text = " ".join(clean(row.get(k)) for k in ("ItemName", "LotDescript"))
            high = _money(row.get("HighBidAmount"))
            bonus, facts = valuation.break_down(text, high, self.spot, self.recovery)
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
                tags=["gsa", "auction", "estate"], bonus=bonus,
                raw={"sale": row.get("SaleNo"), "lot": row.get("LotNo"), "image": row.get("ImageURL")},
            )
