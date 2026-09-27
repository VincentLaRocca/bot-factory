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
    GET  /intake?token=…     a small same-origin page for posting leads by hand
                             or from Claude in Chrome (sites' CSP often blocks
                             cross-origin fetch, so Chrome posts from here)

eBay Marketplace Account Deletion (only needed if eBay user data is ever
stored; the hunter doesn't, so the exemption applies):

    GET  /ebay/account-deletion?challenge_code=…   answers eBay's challenge
    POST /ebay/account-deletion                   purges that user, replies 204

Set ``EBAY_VERIFICATION_TOKEN`` (32–80 chars, letters/digits/_/-) and
``EBAY_DELETION_ENDPOINT`` (the exact public URL registered with eBay).

CORS is open on ``/leads`` (the token still guards it), so a browser script
can also post directly when the page it's on allows it.

Auth is a shared secret (``LEADS_WEBHOOK_TOKEN``) as ``Authorization: Bearer``
or ``?token=`` (Twilio and most form tools can't set headers). Always run it
behind HTTPS — Fly.io, Railway, or a Cloudflare Tunnel from the 5090 box.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
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
                        or _pick(data, "url")  # a post's URL is a stable id for Chrome finds
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
             + [str(data[k]) for k in ("source", "via") if data.get(k)],
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


INTAKE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lead intake</title>
<style>
 :root{--bg:#f7f7f5;--fg:#1d1d1b;--mut:#6b6b66;--line:#d9d9d4;--acc:#2b5fd9}
 @media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecece8;--mut:#9a9a94;--line:#33332f;--acc:#7aa2ff}}
 body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
 main{max-width:640px;margin:0 auto;padding:20px 16px}
 h1{font-size:20px;margin:0 0 4px} p{color:var(--mut);margin:0 0 16px}
 label{display:block;font-size:13px;color:var(--mut);margin:12px 0 4px}
 input,textarea,select{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid var(--line);
  border-radius:8px;background:transparent;color:inherit;font:inherit}
 textarea{min-height:90px} .row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
 button{margin-top:16px;padding:10px 16px;border:0;border-radius:8px;background:var(--acc);color:#fff;font:inherit;cursor:pointer}
 pre{white-space:pre-wrap;font-size:13px;color:var(--mut)}
</style></head><body><main>
<h1>Lead intake</h1><p>Adds a lead to the pipeline: dedupe, score, board. Paste a clip, fill the form, or paste JSON.</p>
<label for="clip">Paste a clip (news story, email, post, bid notice) and it deciphers the lead</label>
<textarea id="clip" style="min-height:140px"></textarea><button id="sendClip" type="button">Decipher &amp; send</button>
<hr style="border:0;border-top:1px solid var(--line);margin:20px 0">
<form id="f">
 <label for="title">What's the job</label><input id="title" name="title" required>
 <label for="url">Link to the post / notice</label><input id="url" name="url" type="url">
 <div class="row"><div><label for="contact">Contact</label><input id="contact" name="contact"></div>
 <div><label for="location">Location</label><input id="location" name="location"></div></div>
 <div class="row"><div><label for="value">Budget / payout ($)</label><input id="value" name="value" inputmode="decimal"></div>
 <div><label for="deadline">Deadline</label><input id="deadline" name="deadline"></div></div>
 <label for="channel">Channel</label><select id="channel" name="listener_channel">
  <option>Local Community</option><option>Open Boards</option><option>Commercial / B2B</option>
  <option>Trade Distress</option><option>General Intake</option></select>
 <label for="body">Details</label><textarea id="body" name="body"></textarea>
 <button>Send lead</button>
</form>
<label for="json">…or paste JSON</label><textarea id="json"></textarea><button id="sendJson" type="button">Send JSON</button>
<pre id="out" aria-live="polite"></pre>
<script>
const token = new URLSearchParams(location.search).get("token") || "";
const out = document.getElementById("out");
async function send(payload) {
  out.textContent = "Sending…";
  try {
    const r = await fetch("/leads", {method: "POST", headers: {"Content-Type": "application/json",
      "Authorization": "Bearer " + token}, body: JSON.stringify(payload)});
    out.textContent = JSON.stringify(await r.json(), null, 2);
  } catch (e) { out.textContent = "Failed: " + e; }
}
document.getElementById("f").addEventListener("submit", e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  data.via = "intake-page"; send(data); e.target.reset();
});
document.getElementById("sendClip").addEventListener("click", () => {
  const clip = document.getElementById("clip").value.trim();
  if (clip) send({clip: clip, via: "clip"});
});
document.getElementById("sendJson").addEventListener("click", () => {
  try { send(JSON.parse(document.getElementById("json").value)); }
  catch (e) { out.textContent = "That isn't valid JSON: " + e.message; }
});
</script></main></body></html>"""


EBAY_PATH = "/ebay/account-deletion"


def ebay_challenge(code: str, token: str = None, endpoint: str = None) -> str:
    """eBay's challenge: hex(SHA-256(challengeCode + verificationToken + endpoint))."""
    token = token if token is not None else os.environ.get("EBAY_VERIFICATION_TOKEN", "")
    endpoint = endpoint if endpoint is not None else os.environ.get("EBAY_DELETION_ENDPOINT", "")
    if not (code and token and endpoint):
        return ""
    return hashlib.sha256((code + token + endpoint).encode("utf-8")).hexdigest()


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
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _authorized(self, query: Dict[str, List[str]]) -> bool:
            if not token:
                return False
            header = self.headers.get("Authorization", "")
            supplied = header[7:] if header.startswith("Bearer ") else (query.get("token") or [""])[0]
            return hmac.compare_digest(supplied, token)

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == EBAY_PATH:
                code = (query.get("challenge_code") or [""])[0]
                answer = ebay_challenge(code)
                if not answer:
                    return self._reply(400, {"status": "ERROR", "message": "not configured or no challenge_code"})
                return self._reply(200, {"challengeResponse": answer})
            if url.path == "/health":
                return self._reply(200, {"status": "ok"})
            if url.path == "/recent":
                if not self._authorized(query):
                    return self._reply(401, {"status": "ERROR", "message": "unauthorized"})
                return self._reply(200, {"status": "SUCCESS", "leads": pipeline.store.recent(50)})
            if url.path == "/intake":
                if not self._authorized(query):
                    return self._reply(401, {"status": "ERROR", "message": "unauthorized"})
                return self._reply(200, INTAKE_PAGE.encode(), "text/html; charset=utf-8")
            return self._reply(404, {"status": "ERROR", "message": "not found"})

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == EBAY_PATH:  # eBay can't send our token; it signs its own requests
                length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._reply(400, {"status": "ERROR", "message": "body is not JSON"})
                who = ((data.get("notification") or {}).get("data") or {})
                purged = sum(pipeline.store.purge_text(str(who.get(k) or "")) for k in ("username", "userId"))
                log.info("eBay account deletion: purged %s record(s)", purged)
                self.send_response(204)
                self._cors()
                self.end_headers()
                return None
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
                    from ..decipher import decipher
                    items = [{**decipher(item["clip"]), **{k: v for k, v in item.items() if k != "clip"}}
                             if isinstance(item, dict) and item.get("clip") else item for item in items]
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
