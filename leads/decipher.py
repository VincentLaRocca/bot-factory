"""Paste a clip, get a lead. The same move as Vinny's ChatGPT RSS-leads window.

Take any pasted text (a news clip, a forwarded email, a post, a bid notice)
and pull out a lead: title, contact, phone, email, location, money, deadline,
link. Two engines:

- **rules** (always available): regexes and a Virginia/Mid-Atlantic place list.
- **local model** (the 5090 level): if ``OLLAMA_URL`` is set (e.g.
  ``http://localhost:11434``), a local model on the 5090 extracts the same
  fields as JSON, and rules fill whatever it leaves blank. No paid API, and
  nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict

from .http import fetch as default_fetch
from .model import clean

# Cities before counties/regions, so "Glen Allen" wins over "Henrico" when both appear.
PLACES = ["Richmond", "Midlothian", "Glen Allen", "Mechanicsville", "Petersburg",
          "Hopewell", "Colonial Heights", "Ashland", "Short Pump", "Williamsburg", "Norfolk", "Virginia Beach",
          "Chesapeake", "Portsmouth", "Suffolk", "Hampton", "Newport News", "Yorktown", "Smithfield",
          "Fredericksburg", "Charlottesville", "Alexandria", "Arlington", "Fairfax", "Quantico", "Lynchburg",
          "Roanoke", "Henrico", "Chesterfield", "Hampton Roads", "Baltimore", "Annapolis", "Raleigh", "Durham", "Washington, DC"]
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?(?:\s?(?:k|m|million|thousand))?", re.I)
_URL = re.compile(r"https?://\S+")
_DATE = re.compile(r"\b(?:due|deadline|by|closes?|closing|bids? due|responses? due|before|until)\b[^.\n]{0,40}?"
                   r"(?:\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|today|tomorrow|friday|monday|tuesday|wednesday|thursday|saturday|sunday)", re.I)
_NAME = re.compile(r"\b(?i:contact|call|email|reach|ask for|attn:?)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})")
FIELDS = ("title", "body", "contact", "location", "value", "deadline", "url")


def _money(text: str) -> float:
    m = _MONEY.search(text)
    if not m:
        return 0.0
    raw = m.group(0).lower().replace("$", "").replace(",", "").strip()
    mult = 1.0
    for word, factor in (("million", 1e6), ("thousand", 1e3), ("m", 1e6), ("k", 1e3)):
        if raw.endswith(word):
            raw, mult = raw[: -len(word)].strip(), factor
            break
    try:
        return float(raw) * mult
    except ValueError:
        return 0.0


def by_rules(clip: str) -> Dict:
    text = clip.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[0] if lines else text
    title = re.split(r"(?<=[.!?])\s", first, maxsplit=1)[0]
    name = _NAME.search(text)
    phone = _PHONE.search(text)
    email = _EMAIL.search(text)
    contact = " · ".join(x for x in (name.group(1) if name else "", email.group(0) if email else "",
                                      phone.group(0) if phone else "") if x)
    place = next((p for p in PLACES if re.search(r"\b" + re.escape(p) + r"\b", text, re.I)), "")
    state = re.search(r",\s*(VA|MD|NC|DC|Virginia|Maryland|North Carolina)\b", text)
    location = place + (f", {state.group(1)}" if place and state else ", VA" if place and place not in ("Baltimore", "Annapolis", "Raleigh", "Durham", "Washington, DC") else "")
    deadline = _DATE.search(text)
    url = _URL.search(text)
    return {"title": clean(title, 200), "body": clean(text, 2000), "contact": contact, "location": location,
            "value": _money(text), "deadline": clean(deadline.group(0), 80) if deadline else "",
            "url": url.group(0).rstrip(").,") if url else ""}


def by_local_model(clip: str, base_url: str, model: str = "llama3.1", fetcher=None) -> Dict:
    prompt = ("Extract a sales lead from this text. Reply with JSON only, keys: title (what the job/opportunity is, "
              "short), contact (name, email, phone), location (city, state), value (number in USD or 0), "
              "deadline (text), url. Use empty strings when unknown.\n\nTEXT:\n" + clip[:6000])
    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode()
    reply = (fetcher or default_fetch)(base_url.rstrip("/") + "/api/generate", method="POST", data=body,
                                       headers={"Content-Type": "application/json"}, timeout=120).json() or {}
    data = json.loads(reply.get("response") or "{}")
    return {k: data.get(k) for k in FIELDS if data.get(k) not in (None, "")}


def decipher(clip: str, fetcher=None) -> Dict:
    """Best lead we can read from a pasted clip. Rules always run; a local model, if configured, goes first."""
    lead = by_rules(clip)
    base = os.environ.get("OLLAMA_URL", "").strip()
    if base:
        try:
            smart = by_local_model(clip, base, os.environ.get("OLLAMA_MODEL", "llama3.1"), fetcher)
            if smart.get("value"):
                try:
                    smart["value"] = float(str(smart["value"]).replace("$", "").replace(",", ""))
                except ValueError:
                    smart.pop("value")
            lead.update({k: v for k, v in smart.items() if v})
            lead["via"] = "local-model"
        except Exception as error:  # the model is a bonus; rules are the floor
            lead["decipher_note"] = f"local model unavailable ({error}); rules only"
    lead["body"] = clean(clip, 2000)
    return lead
