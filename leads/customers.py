"""Customer cards: who they are, what they want, and what counts as a deal *for them*.

A card holds the person (name, phone, email, area) and their terms: a default
**discount threshold** (e.g. 0.30 = "only show me things 30% under book/melt"),
an optional budget, and notes. Their wants live on the same card; each want can
carry its own max price and discount that override the card's defaults.

    python -m leads customer add "Customer A" --phone 804-555-0101 --zip 23220 --miles 150 --discount 0.30 \\
        --notes "cash buyer, weekends"
    python -m leads watch add "Mazdaspeed6" --q "(mazdaspeed6, mazdaspeed 6)" --for "Customer A" --max 15000 --discount 0.25
    python -m leads customer show "Customer A"
    python -m leads customer list

Or on a phone: the inbound listener serves the cards at ``/customers?token=…``.

Cards live in ``var/customers.json`` (``CUSTOMERS_FILE``) on Vinny's machine only.
Wants are stored with the watches (``var/watches.json``) so every hunter sees them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from . import watches

DEFAULT_FILE = "var/customers.json"
FIELDS = ("name", "phone", "email", "zip", "miles", "discount", "budget", "notes")


def path(file: Optional[str] = None) -> Path:
    return Path(file or os.environ.get("CUSTOMERS_FILE") or DEFAULT_FILE)


def load(file: Optional[str] = None) -> Dict[str, Dict]:
    p = path(file)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def save(cards: Dict[str, Dict], file: Optional[str] = None) -> None:
    p = path(file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cards, indent=2, sort_keys=True), encoding="utf-8")


def _clean(fields: Dict) -> Dict:
    out = {}
    for key in FIELDS:
        value = fields.get(key)
        if value in (None, ""):
            continue
        if key in ("discount",):
            value = float(str(value).strip().rstrip("%")) / (100 if str(value).strip().endswith("%") or float(str(value).strip().rstrip("%")) > 1 else 1)
        elif key in ("budget",):
            value = float(str(value).replace("$", "").replace(",", ""))
        elif key == "miles":
            value = int(value)
        out[key] = value
    return out


def upsert(name: str, file: Optional[str] = None, **fields) -> Dict:
    cards = load(file)
    card = cards.get(name, {"name": name})
    card.update(_clean({**fields, "name": name}))
    cards[name] = card
    save(cards, file)
    return card


def delete(name: str, file: Optional[str] = None, watch_file: Optional[str] = None) -> bool:
    cards = load(file)
    gone = cards.pop(name, None) is not None
    save(cards, file)
    for want in watches.customers(watch_file).get(name, []):
        watches.remove(want["name"], watch_file, customer=name)
    return gone


def card(name: str, file: Optional[str] = None, watch_file: Optional[str] = None) -> Dict:
    """The full card: the person, their terms, and their wants."""
    base = load(file).get(name, {"name": name})
    return {**base, "wants": watches.customers(watch_file).get(name, [])}


def all_cards(file: Optional[str] = None, watch_file: Optional[str] = None) -> List[Dict]:
    names = set(load(file)) | {n for n in watches.customers(watch_file) if n}
    return [card(n, file, watch_file) for n in sorted(names, key=str.lower)]


def fits(want: Dict, customer: Dict, cost: float, reference: float) -> tuple:
    """(fits?, reason). Does this listing meet this customer's terms for this want?

    ``reference`` is the appraisers' yardstick: book value for vehicles, melt + gems for
    jewelry, comp estimate for equipment and electronics (0 = none)."""
    ceiling = want.get("max_price") or customer.get("budget")
    if ceiling and cost > ceiling:
        return False, f"over {customer.get('name', 'their')} max ${ceiling:,.0f}"
    discount = want.get("discount", customer.get("discount"))
    if discount:
        if not reference:
            return False, f"no book/melt value to test {discount:.0%} threshold"
        under = 1 - cost / reference
        if under < discount:
            return False, f"{under:.0%} under value, short of {discount:.0%} threshold"
        return True, f"{under:.0%} under value, meets {discount:.0%} threshold" + (f", under ${ceiling:,.0f} max" if ceiling else "")
    return True, f"under ${ceiling:,.0f} max" if ceiling else "matches"


def decide(name: str, lead_id: str, decision: str, file: Optional[str] = None) -> Dict:
    """Vinny's call on a match for a customer: approved (reach out) or passed."""
    cards = load(file)
    card_ = cards.setdefault(name, {"name": name})
    card_.setdefault("decisions", {})[lead_id] = decision
    save(cards, file)
    return card_


def api(action: Dict, store=None, file: Optional[str] = None, watch_file: Optional[str] = None) -> Dict:
    """One entry point for the customer-cards page (no code needed on Vinny's side)."""
    kind = action.get("action")
    if kind == "list":
        cards = all_cards(file, watch_file)
        for c in cards:
            decisions = load(file).get(c["name"], {}).get("decisions", {})
            matches = store.tagged(f"for:{c['name']}") if store else []
            for m in matches:
                m["fits"] = f"fits:{c['name']}" in (m.get("tags") or [])
                m["decision"] = decisions.get(m["lead_id"], "")
            c["matches"] = matches
        return {"status": "SUCCESS", "customers": cards}
    if kind == "save_card":
        data = action.get("card") or {}
        if not data.get("name"):
            return {"status": "ERROR", "message": "a card needs a name"}
        return {"status": "SUCCESS", "card": upsert(data["name"], file, **{k: v for k, v in data.items() if k != "name"})}
    if kind == "delete_card":
        return {"status": "SUCCESS" if delete(action.get("name", ""), file, watch_file) else "ERROR"}
    if kind == "add_want":
        w, who = action.get("want") or {}, action.get("customer")
        if not (who and w.get("name")):
            return {"status": "ERROR", "message": "a want needs a customer and an item"}
        near = {"zip": w["zip"], "miles": int(w.get("miles") or 150)} if w.get("zip") else None
        max_price = float(str(w["max_price"]).replace("$", "").replace(",", "")) if w.get("max_price") else None
        discount = float(str(w["discount"]).rstrip("%")) if w.get("discount") else None
        want = watches.add(w["name"], w.get("q") or w["name"], w.get("hunt") or "auto", max_price, near,
                           w.get("notify") or "all", watch_file, customer=who, discount=discount)
        upsert(who, file)
        return {"status": "SUCCESS", "want": want}
    if kind == "remove_want":
        ok = watches.remove(action.get("name", ""), watch_file, customer=action.get("customer"))
        return {"status": "SUCCESS" if ok else "ERROR"}
    if kind == "decide":
        decide(action["customer"], action["lead_id"], action.get("decision", "approved"), file)
        return {"status": "SUCCESS"}
    return {"status": "ERROR", "message": f"unknown action {kind!r}"}
