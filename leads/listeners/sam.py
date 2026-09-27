"""Bid listener — SAM.gov Get Opportunities v2.

Honors the Ultra-Thin v0 scope from the Maker/Breaker review: one feed
(SAM.gov), rule filters only, set-aside and NAICS pushed into the query so the
API does the narrowing. eVA, GSA eBuy and local boards stay parked; add them
as separate listeners later rather than widening this one.

Needs ``SAM_API_KEY`` (free: sam.gov → Account Details → Public API Key).
The daily quota on a non-federal key is small (as low as ~10 requests/day for
a key with no role, ~1,000 with one), so one sweep issues one request per
NAICS × set-aside pair, pages only when it must, and filters place of
performance *locally* rather than multiplying requests per state. Schedule it
a couple of times a day, not every 15 minutes.
"""

from __future__ import annotations

import itertools
import urllib.parse
from datetime import date, timedelta
from typing import Any, Dict, Iterator, List, Optional

from ..http import Fetch, fetch as default_fetch
from ..model import Lead, clean

ENDPOINT = "https://api.sam.gov/opportunities/v2/search"
SET_ASIDE_NAMES = {
    "SDVOSBC": "SDVOSB set-aside", "SDVOSBS": "SDVOSB sole source",
    "SBA": "Total small business", "SBP": "Partial small business",
    "VSA": "Veteran-owned set-aside", "8A": "8(a)", "HZC": "HUBZone",
}
# Notice types worth a human: solicitations, combined synopsis, presolicitation, sources sought.
DEFAULT_PTYPES = ["o", "k", "p", "r"]


def _mmddyyyy(day: date) -> str:
    return day.strftime("%m/%d/%Y")


def _money(value: Any) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _poc(record: Dict[str, Any]) -> str:
    contacts = record.get("pointOfContact") or []
    primary = next((c for c in contacts if (c or {}).get("type") == "primary"), contacts[0] if contacts else {})
    primary = primary or {}
    return clean(" · ".join(x for x in (primary.get("fullName"), primary.get("email"), primary.get("phone")) if x))


def _place(record: Dict[str, Any]) -> str:
    pop = record.get("placeOfPerformance") or {}
    city = (pop.get("city") or {}).get("name", "")
    state = (pop.get("state") or {}).get("code", "")
    return clean(", ".join(x for x in (city, state) if x))


def to_lead(record: Dict[str, Any], source: str = "sam") -> Lead:
    set_aside = record.get("typeOfSetAside") or ""
    agency = (record.get("fullParentPathName") or "").split(".")[0].title()
    award = record.get("award") or {}
    body = " ".join(filter(None, [
        record.get("type"), SET_ASIDE_NAMES.get(set_aside, record.get("typeOfSetAsideDescription") or ""),
        f"NAICS {record.get('naicsCode')}" if record.get("naicsCode") else "",
        f"Sol# {record.get('solicitationNumber')}" if record.get("solicitationNumber") else "",
        agency,
    ]))
    tags = [t for t in (set_aside.lower(), f"naics-{record.get('naicsCode')}", "federal") if t and not t.endswith("None")]
    return Lead(
        source=source,
        external_id=str(record.get("noticeId") or record.get("solicitationNumber") or record.get("title")),
        title=clean(record.get("title"), 200),
        channel="Open Boards",
        medium="Board Scraping",
        body=body,
        url=record.get("uiLink") or "",
        contact=_poc(record) or agency,
        location=_place(record),
        value=_money(award.get("amount")),
        deadline=record.get("responseDeadLine") or "",
        posted_at=record.get("postedDate") or "",
        tags=tags,
        raw={k: record.get(k) for k in ("noticeId", "solicitationNumber", "type", "naicsCode",
                                         "typeOfSetAside", "fullParentPathName", "description")},
    )


class SamListener:
    kind = "sam"

    def __init__(self, name: str, api_key: str, naics: List[str], set_asides: List[str],
                 states: Optional[List[str]] = None, ptypes: Optional[List[str]] = None,
                 lookback_days: int = 3, page_size: int = 100, max_pages: int = 3,
                 fetcher: Optional[Fetch] = None, today: Optional[date] = None):
        if not api_key:
            raise ValueError("SAM listener needs an API key (set SAM_API_KEY)")
        self.name = name
        self.api_key = api_key
        self.naics = naics or [""]
        self.set_asides = set_asides or [""]
        self.states = states or [""]
        self.ptypes = ptypes if ptypes is not None else DEFAULT_PTYPES
        self.lookback_days = lookback_days
        self.page_size = page_size
        self.max_pages = max_pages
        self.fetch = fetcher or default_fetch
        self.today = today

    def in_area(self, record: Dict[str, Any]) -> bool:
        """Local place-of-performance filter. No stated place → keep (a human decides)."""
        wanted = {s.upper() for s in self.states if s}
        state = ((record.get("placeOfPerformance") or {}).get("state") or {}).get("code", "")
        return not wanted or not state or state.upper() in wanted

    def query(self, naics: str, set_aside: str, offset: int) -> str:
        today = self.today or date.today()
        params = {
            "api_key": self.api_key,
            "postedFrom": _mmddyyyy(today - timedelta(days=self.lookback_days)),
            "postedTo": _mmddyyyy(today),
            "limit": str(self.page_size),
            "offset": str(offset),
        }
        if naics:
            params["ncode"] = naics
        if set_aside:
            params["typeOfSetAside"] = set_aside
        if self.ptypes:
            params["ptype"] = ",".join(self.ptypes)
        return ENDPOINT + "?" + urllib.parse.urlencode(params)

    def listen(self) -> Iterator[Lead]:
        seen = set()
        for naics, set_aside in itertools.product(self.naics, self.set_asides):
            for page in range(self.max_pages):
                data = self.fetch(self.query(naics, set_aside, page)).json() or {}
                records = data.get("opportunitiesData") or []
                for record in records:
                    if record.get("active") == "No" or not self.in_area(record):
                        continue
                    lead = to_lead(record, self.name)
                    if lead.external_id not in seen:
                        seen.add(lead.external_id)
                        yield lead
                total = int(data.get("totalRecords") or 0)
                if (page + 1) * self.page_size >= total or not records:
                    break
