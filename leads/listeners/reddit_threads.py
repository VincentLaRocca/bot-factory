"""Thread listener: when Vinny joins a Reddit thread, interrogate the whole thread.

Reddit is human-first. Vinny posts and comments as himself. This listener
follows him: every thread he has **commented in or started** in the last
``watch_days`` gets read in full (the post plus every comment), and re-read on
later sweeps for anything new.

From each thread it pulls out:

- **the thread itself**: one lead with the post, who started it, dollar
  amounts mentioned, how many people are asking for help, and how many
  replies are aimed at Vinny
- **each new comment from someone else**, as its own lead, tagged
  ``reply-to-you`` when it answers one of Vinny's comments. The pipeline's
  rules decide which of those are worth the board: buying intent, topic, area.

**Groups we own.** Recruiting runs through subreddits Vinny owns. Give the
listener ``subreddits`` and it watches *every* thread in those, not just the
ones he joined: new members, "how do I get in", "I'm a painter / I drive",
and buyers too. Use a separate listener instance with recruiting rules.

Reads Reddit's public JSON (no login, no posting, ever). Run it from the 5090
box: Reddit throttles cloud IPs, not home ones. One request for his comments,
one for his posts, then one per watched thread with a pause between.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, List, Optional

from ..http import Fetch, fetch as default_fetch
from ..model import Lead, clean

log = logging.getLogger("leads.reddit_threads")
BASE = "https://www.reddit.com"
_MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?(?:\s?[kK])?")
_ASKING = re.compile(r"\b(looking for|need (?:a|someone|help)|recommend|anyone know|who do you use|"
                     r"how much|quote|can you|are you available|dm me|pm me)\b", re.I)


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(float(ts or 0), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def walk(children: List[Dict]) -> Iterator[Dict]:
    """Every comment in a Reddit comment tree, depth-first (skips 'load more' stubs)."""
    for child in children or []:
        if child.get("kind") != "t1":
            continue
        data = child.get("data") or {}
        yield data
        replies = data.get("replies")
        if isinstance(replies, dict):
            yield from walk((replies.get("data") or {}).get("children") or [])


class RedditThreadListener:
    kind = "reddit_threads"

    def __init__(self, name: str, username: str, watch_days: int = 7, max_threads: int = 10,
                 location: str = "", fetcher: Optional[Fetch] = None, store=None,
                 pause: float = 2.0, now: Optional[datetime] = None,
                 subreddits: Optional[List[str]] = None, follow_user: bool = True, tags: Optional[List[str]] = None):
        if not username:
            raise ValueError("thread listener needs REDDIT_USERNAME")
        self.name = name
        self.username = username.removeprefix("u/")
        self.subreddits = [s.strip().removeprefix("r/") for s in (subreddits or []) if s and s.strip()]
        self.follow_user = follow_user
        self.extra_tags = tags or []
        self.watch_days = watch_days
        self.max_threads = max_threads
        self.location = location
        self.fetch = fetcher or default_fetch
        self.pause = pause if fetcher is None else 0.0
        self.store = store
        self.now = now
        self.errors: List[str] = []

    # -- watch list (kept in the seen-store's cursor table) -----------------
    def _watch_key(self, thread_id: str) -> str:
        return f"{self.name}:thread:{thread_id}"

    def _load(self, thread_id: str) -> Dict:
        raw = self.store.cursor(self._watch_key(thread_id)) if self.store else None
        return json.loads(raw) if raw else {}

    def _save(self, thread_id: str, state: Dict) -> None:
        if self.store:
            self.store.set_cursor(self._watch_key(thread_id), json.dumps(state))

    def _get(self, url: str):
        return self.fetch(url, headers={"Accept": "application/json"}).json()

    def joined_threads(self) -> Dict[str, Dict]:
        """Threads Vinny commented in or started inside the watch window: id → info."""
        cutoff = (self.now or datetime.now(timezone.utc)) - timedelta(days=self.watch_days)
        threads: Dict[str, Dict] = {}
        sources = [f"{BASE}/user/{self.username}/{kind}.json?limit=50&raw_json=1"
                   for kind in (("comments", "submitted") if self.follow_user else ())]
        sources += [f"{BASE}/r/{sub}/new.json?limit=50&raw_json=1" for sub in self.subreddits]
        for source in sources:
            listing = self._get(source) or {}
            for child in (listing.get("data") or {}).get("children") or []:
                data = child.get("data") or {}
                if datetime.fromtimestamp(float(data.get("created_utc") or 0), timezone.utc) < cutoff:
                    continue
                if child.get("kind") == "t1":   # a comment → its thread
                    thread_id = str(data.get("link_id", "")).removeprefix("t3_")
                    permalink = data.get("permalink", "").rsplit("/", 2)[0] + "/"
                    mine = data.get("name")
                else:                           # a post he made
                    thread_id, permalink, mine = data.get("id"), data.get("permalink"), None  # his post, or any post in a group he owns
                if not thread_id or not permalink:
                    continue
                entry = threads.setdefault(thread_id, {"permalink": permalink, "my_comments": set()})
                if mine:
                    entry["my_comments"].add(mine)
        return dict(list(threads.items())[: self.max_threads])

    # -- interrogation ---------------------------------------------------
    def listen(self) -> Iterator[Lead]:
        self.errors = []
        try:
            threads = self.joined_threads()
        except Exception as error:
            self.errors.append(f"reading u/{self.username}: {error}")
            return
        for index, (thread_id, info) in enumerate(threads.items()):
            if index and self.pause:
                time.sleep(self.pause)
            try:
                yield from self.interrogate(thread_id, info)
            except Exception as error:  # one bad thread must not stop the rest
                self.errors.append(f"thread {thread_id}: {error}")

    def interrogate(self, thread_id: str, info: Dict) -> Iterator[Lead]:
        data = self._get(f"{BASE}{info['permalink'].rstrip('/')}.json?limit=500&sort=new&raw_json=1")
        post = ((data[0].get("data") or {}).get("children") or [{}])[0].get("data") or {}
        comments = list(walk((data[1].get("data") or {}).get("children") or []))
        me = self.username.lower()
        my_names = set(info.get("my_comments") or ()) | {c.get("name") for c in comments
                                                          if str(c.get("author", "")).lower() == me}
        state = self._load(thread_id)
        seen = set(state.get("seen", []))
        subreddit = post.get("subreddit", "")
        thread_title = clean(post.get("title"), 200)
        others = [c for c in comments if str(c.get("author", "")).lower() not in (me, "[deleted]", "automoderator")]
        everything = " ".join([post.get("selftext", "")] + [c.get("body", "") for c in comments])
        money = sorted(set(m.strip() for m in _MONEY.findall(everything)))[:6]
        asking = [c for c in others if _ASKING.search(c.get("body", ""))]
        to_you = [c for c in others if c.get("parent_id") in my_names]

        # 1. The thread, once, as context for everything under it.
        if f"t3_{thread_id}" not in seen:
            facts = [f"{len(comments)} comments", f"{len(asking)} asking for help or a price",
                     f"{len(to_you)} replies to you"]
            if money:
                facts.append("amounts mentioned: " + ", ".join(money))
            yield Lead(
                source=self.name, external_id=f"t3_{thread_id}",
                title=f"r/{subreddit} thread: {thread_title}", channel="Local Community", medium="Board Scraping",
                body=clean(post.get("selftext", ""), 1200) + " | " + " · ".join(facts),
                url=BASE + post.get("permalink", info["permalink"]),
                contact=f"u/{post.get('author', '?')} · r/{subreddit}", location=self.location,
                posted_at=_utc(post.get("created_utc")),
                tags=["reddit", "reddit-thread", f"r/{subreddit}"] + self.extra_tags
                     + (["you-started-it"] if str(post.get("author", "")).lower() == me else []),
                raw={"thread": thread_id, "comments": len(comments), "asking": len(asking), "to_you": len(to_you),
                     "money": money},
            )
            seen.add(f"t3_{thread_id}")

        # 2. Each comment from someone else that we haven't looked at yet.
        for comment in others:
            name = comment.get("name") or f"t1_{comment.get('id')}"
            if name in seen:
                continue
            seen.add(name)
            text = clean(comment.get("body", ""), 1500)
            replying = comment.get("parent_id") in my_names
            yield Lead(
                source=self.name, external_id=name,
                title=clean(f"r/{subreddit} · u/{comment.get('author')}: {text}", 160),
                channel="Local Community", medium="Board Scraping",
                body=f"{text} | Under the post: {thread_title}",
                url=BASE + comment.get("permalink", info["permalink"]),
                contact=f"u/{comment.get('author', '?')} · r/{subreddit}", location=self.location,
                posted_at=_utc(comment.get("created_utc")),
                tags=["reddit", "comment", f"r/{subreddit}"] + self.extra_tags + (["reply-to-you"] if replying else []),
                raw={"thread": thread_id, "parent": comment.get("parent_id")},
            )
        state.update({"permalink": info["permalink"], "seen": sorted(seen),
                      "checked": _utc((self.now or datetime.now(timezone.utc)).timestamp())})
        self._save(thread_id, state)
