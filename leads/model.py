"""The one shape every listener speaks.

A bid notice, an email, a Reddit post and a web-form submission look nothing
alike on the way in. The first thing each listener does is translate its
native record into a :class:`Lead`, so that everything downstream — dedupe,
scoring, routing, the board — is written once and knows no source.

A lead's id is derived from where it came from, not from when it was seen:
the same SAM.gov notice pulled on Monday and again on Tuesday gets the same
id, which is what makes re-running a sweep harmless.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Enumerations shared with lead-board/apps-script/Code.gs. Keep in step.
CHANNELS = ("Trade Distress", "Commercial / B2B", "Open Boards", "Local Community", "General Intake")
MEDIUMS = ("SMS", "Email", "Direct Form", "Board Scraping", "Webhook")
URGENCY = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

_WS = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(text: Any, limit: Optional[int] = None) -> str:
    """Collapse whitespace; optionally truncate on a word boundary."""
    value = _WS.sub(" ", str(text or "")).strip()
    if limit and len(value) > limit:
        cut = value[: limit - 1].rsplit(" ", 1)[0]
        value = (cut or value[: limit - 1]) + "…"
    return value


def make_lead_id(source: str, external_id: str) -> str:
    """Stable id: same source + same native id → same lead, every run."""
    digest = hashlib.sha256(f"{source}\x1f{external_id}".encode("utf-8")).hexdigest()[:12].upper()
    prefix = re.sub(r"[^A-Z0-9]", "", source.upper())[:6] or "LEAD"
    return f"LD-{prefix}-{digest}"


@dataclass
class Lead:
    source: str                      # listener instance name, e.g. "sam-painting"
    external_id: str                 # the source's own id (noticeId, Message-ID, post guid…)
    title: str
    channel: str = "General Intake"  # one of CHANNELS
    medium: str = "Webhook"          # one of MEDIUMS
    body: str = ""
    url: str = ""
    contact: str = ""
    location: str = ""
    destination: str = ""
    value: float = 0.0               # payout / contract value, if known
    mileage: float = 0.0
    deadline: str = ""               # free text or ISO, as the source gives it
    posted_at: str = ""
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    # Filled in by the pipeline, never by a listener:
    score: int = 0
    urgency: str = "MEDIUM"
    reasons: List[str] = field(default_factory=list)
    seen_at: str = field(default_factory=now_iso)

    @property
    def lead_id(self) -> str:
        return make_lead_id(self.source, self.external_id)

    @property
    def fingerprint(self) -> str:
        """Content fingerprint — catches the same job cross-posted in two places."""
        basis = "|".join(clean(x).lower() for x in (self.title, self.contact, self.body[:200]))
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def text(self) -> str:
        """Everything a rule is allowed to read, lower-cased."""
        return " ".join([self.title, self.body, self.location, self.contact, " ".join(self.tags)]).lower()

    def to_board(self) -> Dict[str, Any]:
        """Payload for lead-board/apps-script doPost (action=intake)."""
        return {
            "action": "intake",
            "lead_id": self.lead_id,
            "listener_channel": self.channel,
            "source_medium": self.medium,
            "source_contact": clean(self.contact, 120),
            "origin": clean(self.location, 120),
            "destination": clean(self.destination, 120),
            "cargo_summary": clean(self.title, 200),
            "payout_offered": round(float(self.value or 0), 2),
            "mileage_est": round(float(self.mileage or 0), 1),
            "urgency_level": self.urgency,
            "window_deadline": clean(self.deadline, 80),
            "detail_url": self.url,
            "lead_score": self.score,
            "source_system": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["lead_id"] = self.lead_id
        data["fingerprint"] = self.fingerprint
        return data
