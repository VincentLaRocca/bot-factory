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
        notify: str = "all", file: Optional[str] = None, customer: Optional[str] = None,
        discount: Optional[float] = None) -> Dict:
    """Add or replace a watch. The same item name can sit on several customers' wish lists."""
    watch = {"name": name, "q": q, "hunt": hunt, "notify": notify}
    if customer:
        watch["customer"] = customer
    watches = [w for w in load(file) if _key(w) != _key(watch)]
    if max_price:
        watch["max_price"] = max_price
    if near:
        watch["near"] = near
    if discount:
        watch["discount"] = discount if discount <= 1 else discount / 100
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


# -- the matrix ----------------------------------------------------------------
# Vinny keeps a matrix of customers and what they want. Two layouts are read:
#
# WIDE (customers down the side, wants across the top; a cell = max price, or "x"):
#     customer,Mazdaspeed6,Shelby GT500,Gold Rolex
#     Customer A,15000,,9000
#     Customer B,12000,x,
#
# LONG (one row per want; extra columns optional):
#     customer,item,max_price,search,hunt,zip,miles,notify
#     Customer A,Mazdaspeed6,15000,"(mazdaspeed6, mazdaspeed 6)",vehicle,23220,200,all
#
# The source can be a local CSV or a published Google Sheet CSV link
# (File → Share → Publish to web → CSV), so the sheet stays the master.

def _price(cell: str) -> Optional[float]:
    cell = (cell or "").strip().replace("$", "").replace(",", "")
    try:
        return float(cell) if cell and cell.lower() not in ("x", "y", "yes", "✓") else None
    except ValueError:
        return None


def _wanted(cell: str) -> bool:
    return bool((cell or "").strip()) and (cell or "").strip().lower() not in ("0", "no", "n", "-")


def read_matrix(text: str) -> List[Dict]:
    import csv
    import io
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    lower = [h.lower() for h in header]
    wants: List[Dict] = []
    if "item" in lower or "want" in lower:                       # LONG layout
        col = {h: i for i, h in enumerate(lower)}
        item_col = col.get("item", col.get("want"))
        for row in rows[1:]:
            get = lambda name: (row[col[name]].strip() if name in col and col[name] < len(row) else "")
            item = row[item_col].strip() if item_col < len(row) else ""
            if not item:
                continue
            want = {"name": item, "q": get("search") or item, "hunt": get("hunt") or "auto",
                    "notify": get("notify") or "all"}
            if get("customer"):
                want["customer"] = get("customer")
            if _price(get("max_price") or get("max")):
                want["max_price"] = _price(get("max_price") or get("max"))
            if get("zip"):
                want["near"] = {"zip": get("zip"), "miles": int(get("miles") or 150)}
            if get("discount"):
                d = float(get("discount").rstrip("%"))
                want["discount"] = d / 100 if d > 1 else d
            wants.append(want)
        return wants
    for row in rows[1:]:                                           # WIDE layout
        if not row or not row[0].strip():
            continue
        customer = row[0].strip()
        for i, item in enumerate(header[1:], start=1):
            cell = row[i] if i < len(row) else ""
            if item and _wanted(cell):
                want = {"name": item, "q": item, "hunt": "auto", "notify": "all", "customer": customer}
                if cell.strip().endswith("%"):                     # "30%" = discount threshold instead of a price
                    want["discount"] = float(cell.strip().rstrip("%")) / 100
                elif _price(cell):
                    want["max_price"] = _price(cell)
                wants.append(want)
    return wants


def import_matrix(source: str, file: Optional[str] = None, replace_customers: bool = True, fetcher=None) -> List[Dict]:
    """Load the matrix into the watch file. Customers in the matrix get their wish lists replaced by
    what the matrix says now (so the sheet stays the master); Vinny's own watches are kept."""
    if source.startswith(("http://", "https://")):
        from .http import fetch as default_fetch
        text = (fetcher or default_fetch)(source).text()
    else:
        text = Path(source).read_text(encoding="utf-8")
    wants = read_matrix(text)
    in_matrix = {w.get("customer", "").lower() for w in wants if w.get("customer")}
    kept = [w for w in load(file) if not (replace_customers and (w.get("customer") or "").lower() in in_matrix)]
    keys = {_key(w) for w in wants}
    merged = [w for w in kept if _key(w) not in keys] + wants
    save(merged, file)
    return wants
