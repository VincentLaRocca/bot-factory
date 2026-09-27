"""Hunt listener: eBay Browse API → silver, gold and gem deals.

Uses Vinny's eBay developer keys (App ID = client id, Cert ID = client secret)
with the OAuth *client credentials* grant: an application token that can
search and read public listings, nothing more. This listener never bids,
buys, makes offers or messages sellers. Spending money is Vinny's gate.

Each query in config names what it's hunting (``silver``, ``gold`` or
``gem``). Every listing that comes back is read by :mod:`leads.valuation`
and gets evidence points (``Lead.bonus``) the rules add up:

- metals: price + shipping vs melt (ozt × spot). Under melt by the margin → big
  points; over melt → negative points
- gems: certified, price per carat under Vinny's limit for that stone
- both: misspelled title, auction ending within 24h with no bids, and a
  penalty for thin-feedback sellers

**No eBay user data is kept.** Seller usernames are read to judge feedback
and then dropped; only the listing (id, title, price, link) and the seller's
feedback numbers are stored. That's what makes the "not persisting eBay user
data" exemption from eBay's account-deletion notifications true. If that ever
changes, run the deletion endpoint in ``listeners/webhook.py`` instead.
"""

from __future__ import annotations

import base64
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

from ..http import Fetch, fetch as default_fetch
from ..model import Lead, clean
from .. import valuation

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"


def _money(block: Any) -> float:
    try:
        return float((block or {}).get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


def _when(text: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


class EbayHuntListener:
    kind = "ebay"

    def __init__(self, name: str, client_id: str, client_secret: str, queries: List[Dict[str, Any]],
                 spot: Optional[Dict[str, float]] = None, margin: float = 0.10,
                 max_ppc: Optional[Dict[str, float]] = None, marketplace: str = "EBAY_US",
                 limit: int = 100, fetcher: Optional[Fetch] = None, now: Optional[datetime] = None):
        if not (client_id and client_secret):
            raise ValueError("eBay hunt needs EBAY_CLIENT_ID and EBAY_CLIENT_SECRET (App ID / Cert ID)")
        self.name = name
        self.client_id, self.client_secret = client_id, client_secret
        self.queries = queries
        self.spot = {k: float(v) for k, v in (spot or {}).items() if str(v).strip()}
        self.margin = margin
        self.max_ppc = {k.lower(): float(v) for k, v in (max_ppc or {}).items()}
        self.marketplace = marketplace
        self.limit = limit
        self.fetch = fetcher or default_fetch
        self.now = now
        self.errors: List[str] = []
        self._token: Optional[str] = None

    # -- eBay plumbing ------------------------------------------------------
    def token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
        reply = self.fetch(TOKEN_URL, method="POST", data=body, headers={
            "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"}).json() or {}
        if not reply.get("access_token"):
            raise RuntimeError(f"eBay token refused: {reply.get('error_description') or reply}")
        self._token = reply["access_token"]
        return self._token

    def search_url(self, query: Dict[str, Any]) -> str:
        filters = ["priceCurrency:USD", "itemLocationCountry:US"]
        if query.get("max_price"):
            filters.append(f"price:[..{query['max_price']}]")
        buying = query.get("buying", "")
        if buying:
            filters.append("buyingOptions:{" + "|".join(b.strip().upper() for b in buying.split("|")) + "}")
        params = {"q": query["q"], "limit": str(query.get("limit", self.limit)),
                  "filter": ",".join(filters),
                  "sort": "endingSoonest" if buying.upper() == "AUCTION" else "newlyListed"}
        if query.get("category_ids"):
            params["category_ids"] = str(query["category_ids"])
        return SEARCH_URL + "?" + urllib.parse.urlencode(params)

    def listen(self) -> Iterator[Lead]:
        self.errors = []
        try:
            token = self.token()
        except Exception as error:
            self.errors.append(f"token: {error}")
            return
        seen = set()
        for query in self.queries:
            try:
                data = self.fetch(self.search_url(query), headers={
                    "Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": self.marketplace}).json() or {}
            except Exception as error:  # one bad query must not stop the rest
                self.errors.append(f"{query.get('q')}: {error}")
                continue
            for item in data.get("itemSummaries") or []:
                if item.get("itemId") in seen:
                    continue
                seen.add(item.get("itemId"))
                yield self.appraise(item, query.get("hunt", "silver"))

    # -- the reading ---------------------------------------------------------
    def appraise(self, item: Dict[str, Any], hunt: str) -> Lead:
        title = clean(item.get("title"), 200)
        auction = "AUCTION" in (item.get("buyingOptions") or [])
        price = _money(item.get("currentBidPrice")) if auction and item.get("currentBidPrice") else _money(item.get("price"))
        ship_opts = item.get("shippingOptions") or []
        shipping = _money((ship_opts[0] or {}).get("shippingCost")) if ship_opts else 0.0
        cost = round(price + shipping, 2)
        seller = item.get("seller") or {}
        bonus, facts, tags = [], [], ["ebay", hunt]

        if hunt in ("silver", "gold"):
            metal = valuation.read_metal(title)
            if metal:
                melt = metal.melt(self.spot)
                facts.append(f"{metal.ozt:g} ozt {metal.metal} ({metal.basis})")
                if melt:
                    under = (melt - cost) / melt
                    facts.append(f"melt ${melt:,.2f} vs cost ${cost:,.2f} ({under:+.0%})")
                    if under >= self.margin:
                        bonus.append((40 + min(40, int(under * 100)), f"{under:.0%} under melt"))
                    elif under < 0:
                        bonus.append((-30, f"{-under:.0%} over melt"))
                else:
                    facts.append(f"no {metal.metal} spot price set")
                tags.append(metal.metal)
            else:
                facts.append("weight/purity not in title")
        else:
            gem = valuation.read_gem(title)
            if "fake" in gem.signals:
                bonus.append((-100, "lab/simulant/glass"))
            if gem.certified:
                bonus.append((15, f"certified ({gem.certified})"))
            if gem.stone and gem.carats:
                ppc = cost / gem.carats if gem.carats else 0
                facts.append(f"{gem.carats:g} ct {gem.stone} · ${ppc:,.0f}/ct")
                limit = self.max_ppc.get(gem.stone)
                if limit and ppc <= limit:
                    bonus.append((30, f"${ppc:,.0f}/ct under your ${limit:,.0f}/ct {gem.stone} limit"))
            if gem.stone:
                tags.append(gem.stone)

        wrong = valuation.misspelled(title)
        if wrong:
            bonus.append((20, "misspelled title (" + ", ".join(wrong) + ")"))
        ends = _when(item.get("itemEndDate", ""))
        now = self.now or datetime.now(timezone.utc)
        if auction and ends and ends - now <= timedelta(hours=24) and int(item.get("bidCount") or 0) == 0:
            bonus.append((20, "auction ends <24h with no bids"))
            tags.append("ending-soon")
        try:
            feedback = float(seller.get("feedbackPercentage") or 100)
            count = int(seller.get("feedbackScore") or 0)
        except (TypeError, ValueError):
            feedback, count = 100.0, 0
        if feedback < 97 or count < 10:
            bonus.append((-10, f"thin seller feedback ({feedback:g}%, {count})"))

        where = (item.get("itemLocation") or {})
        return Lead(
            source=self.name, external_id=str(item.get("itemId")), title=title,
            channel="Open Boards", medium="Board Scraping",
            body=" · ".join(facts + [f"{'auction' if auction else 'buy it now'} ${price:,.2f} + ${shipping:,.2f} ship",
                                     item.get("condition", "")]),
            url=item.get("itemWebUrl", ""),
            # Deliberately no username: see the module docstring (eBay user-data exemption).
            contact=f"eBay seller ({seller.get('feedbackPercentage', '?')}%, {seller.get('feedbackScore', '?')} feedback)",
            location=", ".join(x for x in (where.get("postalCode"), where.get("country")) if x),
            value=cost, deadline=item.get("itemEndDate", "") if auction else "",
            posted_at=item.get("itemCreationDate", ""), tags=tags, bonus=bonus,
            raw={"itemId": item.get("itemId"), "price": price, "shipping": shipping, "auction": auction,
                 "bids": item.get("bidCount"), "image": (item.get("image") or {}).get("imageUrl")},
        )
