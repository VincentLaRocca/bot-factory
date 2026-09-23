"""Craigslist static fallback parser.

The markup was inferred from Craigslist's static fallback page and should be
re-verified against a saved fixture if Craigslist changes its markup.
"""

import json
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urljoin

from leadscraper.models import Listing


def _price(value: object) -> float:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _classes(attrs: List[tuple]) -> List[str]:
    for key, value in attrs:
        if key == "class":
            return str(value or "").split()
    return []


class _StaticParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: List[Listing] = []
        self.current: Optional[Dict[str, str]] = None
        self.field: Optional[str] = None
        self.script_data: List[str] = []
        self.in_jsonld = False

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)
        classes = _classes(attrs)
        if tag == "li" and "cl-static-search-result" in classes:
            self.current = {
                "url": "",
                "title": str(attrs_dict.get("title") or ""),
                "price": "",
                "location": "",
            }
            self.field = None
            return
        if tag == "a" and self.current is not None and attrs_dict.get("href"):
            self.current["url"] = urljoin(self.base_url, attrs_dict["href"])
        if tag == "div" and self.current is not None:
            for name in ("title", "price", "location"):
                if name in classes:
                    if name == "title":
                        self.current["title"] = ""
                    self.field = name
                    break
        if tag == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self.in_jsonld = True
            self.script_data = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.field is not None:
            self.field = None
        if tag == "li" and self.current is not None:
            if self.current["url"]:
                self.items.append(
                    Listing(
                        url=self.current["url"],
                        title=self.current["title"].strip(),
                        price=_price(self.current["price"]),
                        location=self.current["location"].strip(),
                        posted_at="",
                    )
                )
            self.current = None
            self.field = None
        if tag == "script" and self.in_jsonld:
            self.in_jsonld = False

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self.script_data.append(data)
        if self.current is not None and self.field is not None:
            self.current[self.field] += data

    def jsonld(self) -> List[dict]:
        raw = "".join(self.script_data).strip()
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return []
        values = value if isinstance(value, list) else [value]
        items = []
        for block in values:
            if not isinstance(block, dict) or block.get("@type") != "ItemList":
                continue
            for element in block.get("itemListElement", []):
                item = element.get("item", element) if isinstance(element, dict) else {}
                if isinstance(item, dict):
                    items.append(item)
        return items


def _jsonld_listing(item: dict, base_url: str) -> Optional[Listing]:
    raw_url = item.get("url")
    if not raw_url:
        return None
    offers = item.get("offers") or {}
    available = offers.get("availableAtOrFrom") or {}
    address = available.get("address") if isinstance(available, dict) else {}
    location = address.get("addressLocality", "") if isinstance(address, dict) else ""
    return Listing(
        url=urljoin(base_url, str(raw_url)),
        title=str(item.get("name") or ""),
        price=_price(offers.get("price")),
        location=str(location or ""),
        posted_at="",
    )


def parse(html: str, base_url: str) -> List[Listing]:
    parser = _StaticParser(base_url)
    parser.feed(html)
    by_url: Dict[str, Listing] = {}
    for listing in parser.items:
        if listing.url not in by_url:
            by_url[listing.url] = listing
    for item in parser.jsonld():
        listing = _jsonld_listing(item, base_url)
        if listing is None:
            continue
        existing = by_url.get(listing.url)
        if existing is None:
            by_url[listing.url] = listing
        else:
            if listing.title:
                existing.title = listing.title
            if listing.price:
                existing.price = listing.price
            if listing.location:
                existing.location = listing.location
    return list(by_url.values())
