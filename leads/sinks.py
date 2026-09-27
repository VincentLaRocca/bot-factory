"""Where a lead goes once it has earned a place.

- :class:`LeadBoardSink`  — the existing Apps Script board (the human triage queue)
- :class:`SlackSink`      — a ping for HIGH/CRITICAL only, so the channel stays signal
- :class:`WebhookSink`    — any other HTTP endpoint (e.g. the Mid-Atlantic Lead Board)
- :class:`JsonlSink`      — an append-only local ledger of everything routed

A sink failing never loses a lead: the pipeline records the failure and the
lead stays in the JSONL ledger for replay.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .http import Fetch, fetch as default_fetch, post_json
from .model import Lead, URGENCY


class Sink:
    name = "sink"

    def send(self, lead: Lead) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LeadBoardSink(Sink):
    """POST to lead-board doPost. text/plain avoids the Apps Script preflight."""

    name = "lead-board"

    def __init__(self, url: str, fetcher: Optional[Fetch] = None):
        self.url = url
        self.fetch = fetcher or default_fetch

    def send(self, lead: Lead) -> None:
        reply = post_json(self.fetch, self.url, lead.to_board(), content_type="text/plain")
        try:
            data = reply.json() or {}
        except ValueError:
            data = {}
        if data.get("status") not in ("SUCCESS", "DUPLICATE"):
            raise RuntimeError(f"lead board refused {lead.lead_id}: {data.get('message') or reply.text()[:200]}")


class SlackSink(Sink):
    name = "slack"

    def __init__(self, webhook_url: str, min_urgency: str = "HIGH", fetcher: Optional[Fetch] = None):
        self.url = webhook_url
        self.threshold = URGENCY.index(min_urgency) if min_urgency in URGENCY else 1
        self.fetch = fetcher or default_fetch

    def wants(self, lead: Lead) -> bool:
        return URGENCY.index(lead.urgency) <= self.threshold

    def send(self, lead: Lead) -> None:
        if not self.wants(lead):
            return
        icon = {"CRITICAL": ":rotating_light:", "HIGH": ":large_orange_circle:"}.get(lead.urgency, ":white_circle:")
        title = f"<{lead.url}|{lead.title}>" if lead.url else lead.title
        lines = [f"{icon} *{lead.urgency}* · score {lead.score} · {lead.source}", title]
        details = " · ".join(x for x in (lead.location, lead.deadline and f"due {lead.deadline}",
                                         lead.value and f"${lead.value:,.0f}", lead.contact) if x)
        if details:
            lines.append(details)
        if lead.reasons:
            lines.append("_" + "; ".join(lead.reasons[:4]) + "_")
        post_json(self.fetch, self.url, {"text": "\n".join(lines)})


class WebhookSink(Sink):
    """POST each lead to another system: bearer auth, and an Idempotency-Key
    equal to the stable lead id, so a retry or a second sweeper is harmless.

    ``shape``: ``"board"`` (the lead-board field names, which most intake
    endpoints understand) or ``"lead"`` (the full Lead record, with score reasons).
    ``min_urgency`` optionally limits what this destination receives.
    """

    def __init__(self, name: str, url: str, token: str = "", shape: str = "board",
                 min_urgency: str = "LOW", fetcher: Optional[Fetch] = None):
        self.name = name
        self.url = url
        self.token = token
        self.shape = shape
        self.threshold = URGENCY.index(min_urgency) if min_urgency in URGENCY else len(URGENCY) - 1
        self.fetch = fetcher or default_fetch

    def send(self, lead: Lead) -> None:
        if URGENCY.index(lead.urgency) > self.threshold:
            return
        payload = lead.to_board() if self.shape == "board" else lead.to_dict()
        headers = {"Content-Type": "application/json", "Idempotency-Key": lead.lead_id}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.fetch(self.url, method="POST", data=json.dumps(payload, default=str).encode("utf-8"), headers=headers)


class JsonlSink(Sink):
    name = "ledger"

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, lead: Lead) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lead.to_dict(), default=str) + "\n")
