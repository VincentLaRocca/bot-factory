"""Special listens: standing watches for specific things Vinny wants to hear about.

A watch is a named eBay search that never expires: "Shelby", "Mazdaspeed6",
"Syclone", "Georg Jensen"… Every new listing that matches gets flagged,
tagged ``watch:<name>``, and still runs through the appraisers (book test for
vehicles, melt and gems for jewelry). A great price on a watched item scores
higher still.

Watches live in a small JSON file (``WATCHES_FILE``, default ``var/watches.json``)
so they survive restarts and can be edited by hand or from the command line:

    python -m leads watch add "Mazdaspeed6" --q "(mazdaspeed6, mazdaspeed 6, mazdaspeed mazda6)" --max 15000
    python -m leads watch add "Shelby" --q "(shelby gt350, shelby gt500, shelby cobra)" --hunt vehicle
    python -m leads watch list
    python -m leads watch remove "Shelby"

**Wish lists for customers.** Any watch can belong to a customer:

    python -m leads watch add "Gold Rolex" --q "rolex 18k" --for "Mike R." --max 9000
    python -m leads watch list --for "Mike R."

Matches are tagged ``for:<customer>`` and say whose wish list they're on, so
the board and the digest show who to call. Customer names stay in the local
watch file (``var/``), never in the repo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_FILE = "var/watches.json"
EXAMPLES = [
    {"name": "Mazdaspeed6", "q": "(mazdaspeed6, mazdaspeed 6, mazdaspeed mazda6, mazdaspeed mazda 6)",
     "hunt": "vehicle", "max_price": 20000, "notify": "all"},
    {"name": "Shelby", "q": "(shelby gt350, shelby gt500, shelby cobra, shelby mustang)",
     "hunt": "vehicle", "notify": "all"},
]


def path(file: Optional[str] = None) -> Path:
    return Path(file or os.environ.get("WATCHES_FILE") or DEFAULT_FILE)


def load(file: Optional[str] = None) -> List[Dict]:
    p = path(file)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "[]")
    except ValueError:
        return []
    return [w for w in data if isinstance(w, dict) and w.get("name") and w.get("q")]


def save(watches: List[Dict], file: Optional[str] = None) -> None:
    p = path(file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(watches, indent=2), encoding="utf-8")


def _key(watch: Dict) -> tuple:
    return (watch["name"].lower(), (watch.get("customer") or "").lower())


def add(name: str, q: str, hunt: str = "auto", max_price: Optional[float] = None, near: Optional[Dict] = None,
        notify: str = "all", file: Optional[str] = None, customer: Optional[str] = None) -> Dict:
    """Add or replace a watch. The same item name can sit on several customers' wish lists."""
    watch = {"name": name, "q": q, "hunt": hunt, "notify": notify}
    if customer:
        watch["customer"] = customer
    watches = [w for w in load(file) if _key(w) != _key(watch)]
    if max_price:
        watch["max_price"] = max_price
    if near:
        watch["near"] = near
    watches.append(watch)
    save(watches, file)
    return watch


def remove(name: str, file: Optional[str] = None, customer: Optional[str] = None) -> bool:
    watches = load(file)
    target = ({"name": name, "customer": customer} if customer else None)
    kept = [w for w in watches if (_key(w) != _key(target) if target else w["name"].lower() != name.lower())]
    save(kept, file)
    return len(kept) != len(watches)


def seed_examples(file: Optional[str] = None) -> List[Dict]:
    """First run: start with Vinny's two named examples if there's no watch file yet."""
    if not path(file).exists():
        save(EXAMPLES, file)
    return load(file)


def customers(file: Optional[str] = None) -> Dict[str, List[Dict]]:
    """Wish lists grouped by customer ("" = Vinny's own watches)."""
    grouped: Dict[str, List[Dict]] = {}
    for w in load(file):
        grouped.setdefault(w.get("customer", ""), []).append(w)
    return grouped
