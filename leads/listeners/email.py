"""Email listener — reads an inbox over IMAP and turns messages into leads.

Works with Gmail (imap.gmail.com + an App Password), Outlook/M365
(outlook.office365.com), or any IMAP server. Read-only by default: messages are
fetched with BODY.PEEK so nothing is marked read, and a UID cursor in the seen
store means each message is looked at once.

Point it at a dedicated folder/label (e.g. a Gmail filter that labels
"Leads" anything from bid services, your web form, or thumbtack/angi) rather
than the whole inbox — the rules still gate, but a narrow folder keeps the
noise down.
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import re
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from typing import Callable, Iterator, List, Optional

from ..model import Lead, clean

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")


def html_to_text(html: str) -> str:
    return clean(unescape(_TAGS.sub(" ", html)))


def body_text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    return html_to_text(content) if part.get_content_type() == "text/html" else clean(content)


def to_lead(message: EmailMessage, source: str = "email", uid: str = "",
            channel: str = "Commercial / B2B", tags=("email",)) -> Lead:
    name, address = parseaddr(message.get("From", ""))
    reply_name, reply_to = parseaddr(message.get("Reply-To", ""))
    subject = clean(message.get("Subject", "(no subject)"), 200)
    text = body_text(message)
    phone = _PHONE.search(text)
    money = _MONEY.search(text)
    contact_bits = [reply_name or name, reply_to or address, phone.group(0) if phone else ""]
    try:
        posted = parsedate_to_datetime(message.get("Date")).isoformat() if message.get("Date") else ""
    except (TypeError, ValueError):
        posted = ""
    return Lead(
        source=source,
        external_id=clean(message.get("Message-ID")) or f"uid:{uid}",
        title=subject,
        channel=channel,
        medium="Email",
        body=clean(text, 2000),
        contact=clean(" · ".join(x for x in contact_bits if x)),
        value=float(money.group(1).replace(",", "")) if money else 0.0,
        posted_at=posted,
        tags=list(tags),
        raw={"from": address, "uid": uid},
    )


class EmailListener:
    kind = "email"

    def __init__(self, name: str, host: str, user: str, password: str, folder: str = "INBOX",
                 only_from: Optional[List[str]] = None, max_messages: int = 50, port: int = 993,
                 channel: str = "Commercial / B2B", tags: Optional[List[str]] = None,
                 skip_from: Optional[List[str]] = None, spot: Optional[dict] = None, decipher: bool = False,
                 connect: Optional[Callable[[], imaplib.IMAP4]] = None, store=None):
        if not (user and password):
            raise ValueError("email listener needs LEADS_IMAP_USER and LEADS_IMAP_PASSWORD")
        self.name = name
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.folder = folder
        self.only_from = [x.lower() for x in (only_from or [])]
        self.skip_from = [x.lower() for x in (skip_from or [])]
        self.spot = {k: float(v) for k, v in (spot or {}).items() if str(v).strip()}
        self.decipher = decipher
        self.max_messages = max_messages
        self.connect = connect or (lambda: imaplib.IMAP4_SSL(self.host, self.port))
        self.store = store  # SeenStore, for the UID cursor; optional
        self.channel = channel
        self.tags = tags or ["email"]

    def allowed(self, message: EmailMessage) -> bool:
        sender = parseaddr(message.get("From", ""))[1].lower()
        if any(rule in sender for rule in self.skip_from):
            return False
        return not self.only_from or any(rule in sender for rule in self.only_from)

    def listen(self) -> Iterator[Lead]:
        imap = self.connect()
        try:
            imap.login(self.user, self.password)
            status, _ = imap.select(self._quoted(self.folder), readonly=True)
            if status != "OK":
                raise RuntimeError(f"cannot open folder {self.folder!r}")
            last = int(self.store.cursor(self.name) or 0) if self.store else 0
            status, data = imap.uid("SEARCH", None, f"UID {last + 1}:*")
            uids = [u for u in (data[0] or b"").split() if int(u) > last][-self.max_messages:]
            newest = last
            for uid in uids:
                status, parts = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if status != "OK" or raw is None:
                    continue
                message = email.message_from_bytes(raw, policy=email.policy.default)
                newest = max(newest, int(uid))
                if self.allowed(message):
                    found = to_lead(message, self.name, uid.decode(), self.channel, self.tags)
                    if self.decipher:  # alerts/newsletters: read who, where, how much from the text
                        from ..decipher import by_rules
                        read = by_rules(found.body + ". " + found.title)  # body first: alert subjects just echo the search terms
                        found.location = found.location or read["location"]
                        found.value = found.value or float(read["value"] or 0)
                        found.deadline = found.deadline or read["deadline"]
                        found.url = found.url or read["url"]
                    if self.spot:  # estate/auction mail: read metal content from subject + body
                        from ..valuation import metal_bonus
                        found.bonus, facts = metal_bonus(found.title + " " + found.body, 0, self.spot)
                        if facts:
                            found.body = " · ".join(facts) + " | " + found.body
                    yield found
            if self.store and newest > last:
                self.store.set_cursor(self.name, str(newest))
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    @staticmethod
    def _quoted(folder: str) -> str:
        return folder if folder.startswith('"') or " " not in folder else f'"{folder}"'
