"""Inbound lead listener — an HTTP endpoint anything can push a lead into.

Push sources (unlike the pull listeners, these arrive on their own time):

- **Web forms** — your site's contact/quote form, Typeform, Jotform, Google Forms
  via Apps Script, Tally… POST JSON
- **Zapier / Make / n8n** — any trigger they support (Facebook Lead Ads,
  Thumbtack, Angi, a new Sheet row) → "Webhook POST" → here
- **SMS** — point a Twilio number's "A message comes in" webhook here; the
  form-encoded Twilio body is understood natively
- **Other bots** — the courier SMS listener, Grok's away team, anything

Routes::

    POST /leads?token=…      one lead (JSON object) or many (JSON array)
    POST /sms?token=…        Twilio inbound SMS (form-encoded)
    GET  /health             liveness
    GET  /recent?token=…     last routed leads, JSON

Auth is a shared secret (``LEADS_WEBHOOK_TOKEN``) as ``Authorization: Bearer``
or ``?token=`` (Twilio and most form tools can't set headers). Always run it
behind HTTPS — Fly.io, Railway, or a Cloudflare Tunnel from the 5090 box.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

from ..model import CHANNELS, Lead, MEDIUMS, clean, now_iso

log = logging.getLogger("leads.webhook")
MAX_BODY = 256 * 1024

# Common field names from form builders, Zapier, and CRMs → Lead fields.
ALIASES = {
    "title": ("title", "subject", "summary", "service", "job", "cargo_summary", "project", "request"),
    "body": ("body", "message", "description", "details", "notes", "comments", "text"),
    "contact": ("contact", "source_contact", "name", "full_name", "email", "phone", "from"),
    "location": ("location", "origin", "address", "city", "zip", "zipcode", "service_area"),
    "destination": ("destination", "dropoff", "delivery"),
    "value": ("value", "payout_offered", "budget", "amount", "price"),
    "mileage": ("mileage", "mileage_est", "miles"),
    "deadline": ("deadline", "window_deadline", "due", "needed_by", "date_needed"),
    "url": ("url", "link", "detail_url"),
}


def _pick(data: Dict[str, Any], field: str) -> Any:
    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in ALIASES[field]:
        if lowered.get(key) not in (None, ""):
            return lowered[key]
    return ""


def _number(value: Any) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _enum(value: Any, allowed, fallback: str) -> str:
    wanted = str(value or "").strip().lower()
    return next((item for item in allowed if item.lower() == wanted), fallback)


def from_json(data: Dict[str, Any], source: str = "webhook") -> Lead:
    contact_parts = [data.get(k) for k in ("name", "full_name", "email", "phone") if data.get(k)]
    contact = " · ".join(str(x) for x in contact_parts) or _pick(data, "contact")
    title = _pick(data, "title") or clean(_pick(data, "body"), 80) or "Inbound lead"
    return Lead(
        source=source,
        external_id=str(data.get("id") or data.get("lead_id") or data.get("submission_id")
                        or f"{clean(title)}|{clean(contact)}|{data.get('timestamp') or now_iso()}"),
        title=clean(title, 200),
        channel=_enum(data.get("listener_channel") or data.get("channel"), CHANNELS, "General Intake"),
        medium=_enum(data.get("source_medium") or data.get("medium"), MEDIUMS, "Direct Form"),
        body=clean(_pick(data, "body"), 2000),
        url=str(_pick(data, "url")),
        contact=clean(contact, 200),
        location=clean(_pick(data, "location"), 200),
        destination=clean(_pick(data, "destination"), 200),
        value=_number(_pick(data, "value")),
        mileage=_number(_pick(data, "mileage")),
        deadline=clean(_pick(data, "deadline"), 80),
        posted_at=str(data.get("timestamp") or now_iso()),
        tags=([str(t) for t in data.get("tags", [])] if isinstance(data.get("tags"), list) else [])
             + ([str(data["source"])] if data.get("source") else []),
        raw={k: v for k, v in data.items() if k not in ("token",)},
    )


def from_twilio(form: Dict[str, str], source: str = "sms") -> Lead:
    text = clean(form.get("Body", ""))
    sender = form.get("From", "")
    where = ", ".join(x for x in (form.get("FromCity"), form.get("FromState")) if x)
    return Lead(
        source=source,
        external_id=form.get("MessageSid") or f"{sender}|{text}",
        title=clean(text, 120) or "(empty SMS)",
        channel="Trade Distress",
        medium="SMS",
        body=text,
        contact=sender,
        location=where,
        value=_number(next(iter(re.findall(r"\$\s?([\d,]+)", text)), 0)),
        tags=["sms"],
        raw={"to": form.get("To", "")},
    )


def make_handler(pipeline, token: str, source: str = "webhook"):
    class Handler(BaseHTTPRequestHandler):
        server_version = "bot-factory-leads/0.1"

        def log_message(self, fmt, *args):  # route to logging, not stderr
            log.info("%s %s", self.address_string(), fmt % args)

        def _reply(self, status: int, payload, content_type: str = "application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self, query: Dict[str, List[str]]) -> bool:
            if not token:
                return False
            header = self.headers.get("Authorization", "")
            supplied = header[7:] if header.startswith("Bearer ") else (query.get("token") or [""])[0]
            return hmac.compare_digest(supplied, token)

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == "/health":
                return self._reply(200, {"status": "ok"})
            if url.path == "/recent":
                if not self._authorized(query):
                    return self._reply(401, {"status": "ERROR", "message": "unauthorized"})
                return self._reply(200, {"status": "SUCCESS", "leads": pipeline.store.recent(50)})
            return self._reply(404, {"status": "ERROR", "message": "not found"})

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if not self._authorized(query):
                return self._reply(401, {"status": "ERROR", "message": "unauthorized"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._reply(413, {"status": "ERROR", "message": "too large"})
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                if url.path == "/sms":
                    form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
                    pipeline.process([from_twilio(form, source)])
                    # Empty TwiML: acknowledge without texting the sender back.
                    return self._reply(200, b'<?xml version="1.0" encoding="UTF-8"?><Response/>', "text/xml")
                if url.path == "/leads":
                    data = json.loads(raw or "{}")
                    items = data if isinstance(data, list) else [data]
                    report = pipeline.process([from_json(item, source) for item in items if isinstance(item, dict)])
                    return self._reply(200, {
                        "status": "SUCCESS",
                        "routed": [lead.lead_id for lead in report.routed],
                        "dropped": [lead.lead_id for lead in report.dropped],
                        "duplicates": report.duplicates,
                        "errors": report.errors,
                    })
            except json.JSONDecodeError:
                return self._reply(400, {"status": "ERROR", "message": "body is not JSON"})
            return self._reply(404, {"status": "ERROR", "message": "not found"})

    return Handler


def serve(pipeline, token: str, host: str = "0.0.0.0", port: int = 8080, source: str = "webhook"):
    if not token:
        raise ValueError("refusing to serve without LEADS_WEBHOOK_TOKEN")
    server = ThreadingHTTPServer((host, port), make_handler(pipeline, token, source))
    log.info("lead listener on http://%s:%s", host, server.server_port)
    return server
