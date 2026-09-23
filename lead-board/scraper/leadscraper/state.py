"""JSON state for deduplicating scraped listings."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load(path: str) -> Dict[str, dict]:
    state_path = Path(path)
    if not state_path.exists():
        return {"seen": {}}
    with state_path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("seen"), dict):
        return {"seen": {}}
    return {"seen": dict(value["seen"])}


def save(path: str, state: Dict[str, dict]) -> None:
    cutoff = _now() - timedelta(days=30)
    seen = {}
    for lead_id, timestamp in state.get("seen", {}).items():
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed >= cutoff:
            seen[lead_id] = timestamp
    state["seen"] = seen
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")


def is_seen(state: Dict[str, dict], lead_id: str) -> bool:
    return lead_id in state.get("seen", {})


def mark_seen(state: Dict[str, dict], lead_id: str, timestamp: str = "") -> None:
    state.setdefault("seen", {})[lead_id] = timestamp or _iso(_now())
