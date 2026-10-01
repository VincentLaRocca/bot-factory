"""The morning digest: what's worth a look, in one message.

It reads from the **lead board** when one is configured. The board is the one
place every sweeper (GitHub Actions, the 5090 box, Chrome, inbound forms)
converges, so a digest from there sees everything. Without a board it falls
back to the local store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .http import Fetch, fetch as default_fetch, post_json
from .model import URGENCY
from .store import SeenStore

OPEN = ("NEW", "WATCH", "BID_PREPARED")


def _parse(ts: str) -> Optional[datetime]:
    try:
        value = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def from_board(url: str, fetcher: Optional[Fetch] = None) -> List[Dict]:
    reply = (fetcher or default_fetch)(url + ("&" if "?" in url else "?") + "status=active&limit=500").json() or {}
    if reply.get("status") != "SUCCESS":
        raise RuntimeError(f"lead board: {reply.get('message', 'no data')}")
    return [{
        "title": row.get("cargo_summary", ""), "url": row.get("detail_url", ""),
        "score": int(row.get("lead_score") or 0), "urgency": row.get("urgency_level", "MEDIUM"),
        "source": row.get("source_system") or row.get("source_medium", ""), "status": row.get("triage_status", ""),
        "when": row.get("timestamp", ""), "where": row.get("origin", ""), "deadline": row.get("window_deadline", ""),
    } for row in reply.get("leads", [])]


def from_store(store: SeenStore) -> List[Dict]:
    return [{
        "title": row["title"], "url": row["url"], "score": row["score"], "urgency": row["urgency"],
        "source": row["source"], "status": "NEW", "when": row["first_seen"], "where": "", "deadline": "",
    } for row in store.recent(500)]


def select(rows: List[Dict], hours: int = 24, top: int = 10, now: Optional[datetime] = None) -> List[Dict]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
    fresh = [r for r in rows if r["status"] in OPEN and (_parse(r["when"]) or cutoff) >= cutoff]
    rank = {u: i for i, u in enumerate(URGENCY)}
    return sorted(fresh, key=lambda r: (rank.get(r["urgency"], 9), -r["score"]))[:top]


def render(rows: List[Dict], hours: int, board_link: str = "") -> str:
    if not rows:
        return f"*Lead digest* · nothing new worth a look in the last {hours}h."
    lines = [f"*Lead digest* · top {len(rows)} from the last {hours}h"]
    for i, r in enumerate(rows, 1):
        title = f"<{r['url']}|{r['title']}>" if r["url"] else r["title"]
        extra = " · ".join(x for x in (r["where"], r["deadline"] and f"due {r['deadline']}", r["source"]) if x)
        lines.append(f"{i}. *{r['urgency']}* {r['score'] or ''} {title}" + (f"\n    _{extra}_" if extra else ""))
    if board_link:
        lines.append(f"Triage on the board: {board_link}")
    return "\n".join(lines)


def send(text: str, slack_url: str, fetcher: Optional[Fetch] = None) -> None:
    post_json(fetcher or default_fetch, slack_url, {"text": text})
