"""Memory of what has already been seen, so a sweep can run every 15 minutes
and only new leads move.

SQLite, one file, stdlib. Two keys: the stable ``lead_id`` (same source item
seen again) and the content ``fingerprint`` (same job cross-posted elsewhere).
Dropped leads are remembered too — otherwise a low-scoring post would be
re-scored on every sweep forever.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .model import Lead, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    lead_id     TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT,
    score       INTEGER NOT NULL,
    urgency     TEXT NOT NULL,
    disposition TEXT NOT NULL,          -- ROUTED | DROPPED | DUPLICATE
    first_seen  TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leads_fp ON leads (fingerprint);
CREATE TABLE IF NOT EXISTS cursors (
    source TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


class SeenStore:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    # -- dedupe ------------------------------------------------------------
    def seen(self, lead: Lead) -> Optional[str]:
        """'id' if this exact item was seen, 'fingerprint' if a twin was, else None."""
        if self.db.execute("SELECT 1 FROM leads WHERE lead_id = ?", (lead.lead_id,)).fetchone():
            return "id"
        row = self.db.execute(
            "SELECT 1 FROM leads WHERE fingerprint = ? AND disposition = 'ROUTED'", (lead.fingerprint,)
        ).fetchone()
        return "fingerprint" if row else None

    def record(self, lead: Lead, disposition: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO leads VALUES (?,?,?,?,?,?,?,?,?,?)",
            (lead.lead_id, lead.fingerprint, lead.source, lead.title, lead.url, lead.score,
             lead.urgency, disposition, now_iso(), json.dumps(lead.to_dict(), default=str)),
        )
        self.db.commit()

    # -- per-source cursors (e.g. last IMAP UID, last SAM posted date) ------
    def cursor(self, source: str) -> Optional[str]:
        row = self.db.execute("SELECT value FROM cursors WHERE source = ?", (source,)).fetchone()
        return row[0] if row else None

    def set_cursor(self, source: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO cursors VALUES (?, ?)", (source, str(value)))
        self.db.commit()

    # -- reporting ---------------------------------------------------------
    def recent(self, limit: int = 50, disposition: str = "ROUTED") -> List[Dict]:
        rows = self.db.execute(
            "SELECT lead_id, source, title, url, score, urgency, first_seen FROM leads "
            "WHERE disposition = ? ORDER BY first_seen DESC, score DESC LIMIT ?",
            (disposition, limit),
        ).fetchall()
        keys = ("lead_id", "source", "title", "url", "score", "urgency", "first_seen")
        return [dict(zip(keys, row)) for row in rows]

    def counts(self) -> Dict[str, int]:
        return dict(self.db.execute("SELECT disposition, COUNT(*) FROM leads GROUP BY disposition").fetchall())

    def close(self) -> None:
        self.db.close()
