"""Social / internet listener — RSS and Atom, with Reddit as a first-class preset.

Why feeds instead of scraping: every source here publishes a feed on purpose,
so the listener stays inside each site's terms and doesn't break when a page
layout changes. What it covers:

- **Reddit** — any subreddit, or a keyword search inside one:
  ``{"reddit": {"subreddit": "rva", "query": "painter OR painting"}}``
- **Google Alerts** — create an alert, choose "Deliver to: RSS feed", paste the URL
- **Job/gig boards, city and county bid pages, industry news** — anything with RSS/Atom

Reddit asks for a descriptive User-Agent and a gentle request rate; one
request per feed per sweep is well inside that.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Dict, Iterator, List, Optional

from ..http import Fetch, fetch as default_fetch
from ..model import Lead, clean
from .email import html_to_text

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
log = logging.getLogger("leads.feeds")


def reddit_url(subreddit: str, query: str = "", sort: str = "new") -> str:
    sub = subreddit.strip().removeprefix("r/")
    if query:
        params = urllib.parse.urlencode({"q": query, "restrict_sr": "1", "sort": sort, "t": "week"})
        return f"https://www.reddit.com/r/{sub}/search.rss?{params}"
    return f"https://www.reddit.com/r/{sub}/{sort}/.rss"


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None else ""


def parse_feed(xml: str) -> List[Dict[str, str]]:
    """RSS 2.0 or Atom → list of {id, title, link, summary, author, published}."""
    root = ET.fromstring(xml)
    items: List[Dict[str, str]] = []
    if root.tag == f"{ATOM}feed":
        for entry in root.findall(f"{ATOM}entry"):
            link = entry.find(f"{ATOM}link[@rel='alternate']")
            if link is None:
                link = entry.find(f"{ATOM}link")
            author = entry.find(f"{ATOM}author/{ATOM}name")
            summary = entry.find(f"{ATOM}content")
            if summary is None:
                summary = entry.find(f"{ATOM}summary")
            items.append({
                "id": _text(entry.find(f"{ATOM}id")),
                "title": _text(entry.find(f"{ATOM}title")),
                "link": link.get("href", "") if link is not None else "",
                "summary": _text(summary),
                "author": _text(author),
                "published": _text(entry.find(f"{ATOM}published")) or _text(entry.find(f"{ATOM}updated")),
            })
        return items
    for item in root.iter("item"):
        published = _text(item.find("pubDate"))
        try:
            published = parsedate_to_datetime(published).isoformat() if published else ""
        except (TypeError, ValueError):
            pass
        items.append({
            "id": _text(item.find("guid")) or _text(item.find("link")),
            "title": _text(item.find("title")),
            "link": _text(item.find("link")),
            "summary": _text(item.find("description")),
            "author": _text(item.find("author")) or _text(item.find("{http://purl.org/dc/elements/1.1/}creator")),
            "published": published,
        })
    return items


class FeedListener:
    kind = "feed"

    def __init__(self, name: str, urls: List[str], channel: str = "Local Community",
                 location: str = "", tags: Optional[List[str]] = None, max_items: int = 50,
                 fetcher: Optional[Fetch] = None, pause: float = 2.0):
        self.name = name
        self.urls = urls
        self.channel = channel
        self.location = location
        self.tags = tags or []
        self.max_items = max_items
        self.fetch = fetcher or default_fetch
        self.pause = pause if fetcher is None else 0.0
        self.errors: List[str] = []

    @classmethod
    def from_config(cls, name: str, config: Dict, fetcher: Optional[Fetch] = None) -> "FeedListener":
        urls = [u for u in config.get("urls", []) if u]
        for spec in config.get("reddit", []) if isinstance(config.get("reddit"), list) else \
                ([config["reddit"]] if config.get("reddit") else []):
            urls.append(reddit_url(spec["subreddit"], spec.get("query", ""), spec.get("sort", "new")))
        return cls(name, urls, channel=config.get("channel", "Local Community"),
                   location=config.get("location", ""), tags=config.get("tags"),
                   max_items=int(config.get("max_items", 50)), fetcher=fetcher)

    def listen(self) -> Iterator[Lead]:
        self.errors = []
        for index, url in enumerate(self.urls):
            if index and self.pause:
                time.sleep(self.pause)  # be a polite neighbour; Reddit rate-limits bursts
            try:
                xml = self.fetch(url, headers={"Accept": "application/rss+xml, application/atom+xml, */*"}).text()
                items = parse_feed(xml)
            except Exception as error:  # one dead feed must not silence the rest
                message = f"{url.split('?')[0]}: {error}"
                log.warning("%s: %s", self.name, message)
                self.errors.append(message)
                continue
            host = urllib.parse.urlparse(url).netloc.replace("www.", "")
            for item in items[: self.max_items]:
                body = html_to_text(item["summary"])
                yield Lead(
                    source=self.name,
                    external_id=item["id"] or item["link"] or item["title"],
                    title=clean(item["title"], 200),
                    channel=self.channel,
                    medium="Board Scraping",
                    body=clean(body, 2000),
                    url=item["link"],
                    contact=clean(" · ".join(x for x in (item["author"], host) if x)),
                    location=self.location,
                    posted_at=item["published"],
                    tags=list(self.tags) + [host],
                    raw={"feed": url.split("?")[0]},
                )
