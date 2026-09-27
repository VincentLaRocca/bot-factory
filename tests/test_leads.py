"""Lead system: every listener, the pipeline and the sinks — fully offline."""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from email.message import EmailMessage

import pytest

from leads import Lead, Pipeline, RuleSet, SeenStore
from leads import config as config_module
from leads.__main__ import sweep
from leads.http import Response
from leads.listeners import email as email_listener
from leads.listeners.feeds import FeedListener, parse_feed, reddit_url
from leads.listeners.sam import SamListener, to_lead as sam_to_lead
from leads.listeners.webhook import from_json, from_twilio, serve
from leads.sinks import JsonlSink, LeadBoardSink, SlackSink


# --------------------------------------------------------------------- fakes
class FakeWeb:
    """Routes URLs to canned responses and records every request."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def __call__(self, url, method="GET", data=None, headers=None, **_):
        self.calls.append({"url": url, "method": method, "data": data, "headers": headers or {}})
        for prefix, reply in self.routes.items():
            if url.startswith(prefix):
                if isinstance(reply, Exception):
                    raise reply
                body = reply if isinstance(reply, (bytes, str)) else json.dumps(reply)
                return Response(200, body.encode() if isinstance(body, str) else body, {})
        return Response(200, b'{"status": "SUCCESS"}', {})


class RecordingSink:
    name = "recording"

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, lead):
        if self.fail:
            raise RuntimeError("down")
        self.sent.append(lead)


def lead(title="Need a painter for 3 rooms", source="test", ext="1", **kw):
    return Lead(source=source, external_id=ext, title=title, **kw)


# ---------------------------------------------------------------- SAM.gov
SAM_RECORD = {
    "noticeId": "abc123", "title": "Interior Painting - Hampton VAMC Bldg 110",
    "solicitationNumber": "36C24626Q0001", "fullParentPathName": "VETERANS AFFAIRS, DEPARTMENT OF.VETERANS AFFAIRS",
    "postedDate": "2026-09-25", "type": "Combined Synopsis/Solicitation", "responseDeadLine": "2026-10-10T14:00:00-04:00",
    "naicsCode": "238320", "typeOfSetAside": "SDVOSBC", "active": "Yes",
    "placeOfPerformance": {"city": {"name": "Hampton"}, "state": {"code": "VA"}},
    "pointOfContact": [{"type": "primary", "fullName": "Jane Doe", "email": "jane.doe@va.gov", "phone": "757-555-0100"}],
    "uiLink": "https://sam.gov/opp/abc123/view", "award": None,
}


def test_sam_record_becomes_a_lead():
    result = sam_to_lead(SAM_RECORD, "sam-painting")
    assert result.title.startswith("Interior Painting")
    assert result.location == "Hampton, VA"
    assert "jane.doe@va.gov" in result.contact
    assert "SDVOSB set-aside" in result.body and "NAICS 238320" in result.body
    assert result.url == "https://sam.gov/opp/abc123/view"
    assert result.channel == "Open Boards" and result.medium == "Board Scraping"
    assert result.lead_id == sam_to_lead(SAM_RECORD, "sam-painting").lead_id  # stable


def test_sam_listener_queries_filters_area_and_pages():
    texas = dict(SAM_RECORD, noticeId="tx1", placeOfPerformance={"state": {"code": "TX"}})
    closed = dict(SAM_RECORD, noticeId="old", active="No")
    web = FakeWeb({"https://api.sam.gov": {"totalRecords": 3, "opportunitiesData": [SAM_RECORD, texas, closed]}})
    listener = SamListener("sam", "KEY", naics=["238320"], set_asides=["SDVOSBC", "SBA"], states=["VA"],
                           fetcher=web, today=date(2026, 9, 27))
    found = list(listener.listen())
    assert [x.external_id for x in found] == ["abc123"]            # TX and inactive filtered, dup across set-asides removed
    assert len(web.calls) == 2                                      # one request per set-aside, no per-state fan-out
    query = urllib.parse.parse_qs(urllib.parse.urlparse(web.calls[0]["url"]).query)
    assert query["ncode"] == ["238320"] and query["typeOfSetAside"] == ["SDVOSBC"]
    assert query["postedFrom"] == ["09/24/2026"] and query["postedTo"] == ["09/27/2026"]
    assert "state" not in query


def test_sam_listener_requires_a_key():
    with pytest.raises(ValueError):
        SamListener("sam", "", naics=[], set_asides=[])


# ------------------------------------------------------------------- email
def make_email(subject="RFQ: exterior painting, Chesapeake warehouse", uid_body=None):
    message = EmailMessage()
    message["From"] = "Pat Buyer <pat@acme-logistics.com>"
    message["Subject"] = subject
    message["Message-ID"] = "<m1@acme>"
    message["Date"] = "Fri, 25 Sep 2026 10:00:00 -0400"
    message.set_content(uid_body or "Hi, please quote exterior painting. Budget $12,500. Call 757-555-0199.")
    message.add_alternative("<p>Hi, please <b>quote</b> exterior painting.</p>", subtype="html")
    return message


def test_email_becomes_a_lead():
    result = email_listener.to_lead(make_email(), "inbox", "7")
    assert result.title.startswith("RFQ")
    assert "pat@acme-logistics.com" in result.contact and "757-555-0199" in result.contact
    assert result.value == 12500.0
    assert result.medium == "Email" and result.external_id == "<m1@acme>"


class FakeImap:
    def __init__(self, messages):
        self.messages = messages  # {uid: bytes}
        self.searches = []

    def login(self, user, password):
        return "OK", []

    def select(self, folder, readonly=False):
        assert readonly
        return "OK", [b"3"]

    def uid(self, command, *args):
        if command == "SEARCH":
            self.searches.append(args[-1])
            low = int(args[-1].split()[1].split(":")[0])
            hits = [str(u).encode() for u in sorted(self.messages) if u >= low] or [str(max(self.messages)).encode()]
            return "OK", [b" ".join(hits)]
        uid = int(args[0])
        assert args[1] == "(BODY.PEEK[])"  # never marks mail as read
        return "OK", [(b"header", self.messages[uid]), b")"]

    def logout(self):
        return "BYE", []


def test_email_listener_uses_a_uid_cursor():
    store = SeenStore()
    imap = FakeImap({5: bytes(make_email()), 6: bytes(make_email("Lunch?"))})
    listener = email_listener.EmailListener("inbox", "imap", "u", "p", store=store, connect=lambda: imap,
                                            only_from=["acme-logistics.com"])
    assert len(list(listener.listen())) == 2
    assert store.cursor("inbox") == "6"
    assert list(listener.listen()) == []             # IMAP returns the last UID for N:* — must be ignored
    assert imap.searches[-1] == "UID 7:*"


# ------------------------------------------------------------ social / RSS
REDDIT_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <author><name>/u/homeowner804</name></author>
    <content type="html">&lt;p&gt;Looking for a painter for 3 bedrooms in Henrico, need a quote ASAP&lt;/p&gt;</content>
    <id>t3_abc</id>
    <link href="https://www.reddit.com/r/rva/comments/abc/painter/" />
    <updated>2026-09-26T12:00:00+00:00</updated>
    <title>Painter recommendations?</title>
  </entry>
  <entry>
    <author><name>/u/artsy</name></author>
    <content type="html">Went to a painting class downtown</content>
    <id>t3_def</id>
    <link href="https://www.reddit.com/r/rva/comments/def/" />
    <title>Fun weekend in RVA</title>
  </entry>
</feed>"""

RSS = """<rss version="2.0"><channel><item><title>Bid: County courthouse repaint</title>
<link>https://county.example.gov/bids/42</link><guid>bid-42</guid>
<description>Invitation to bid, painting services.</description>
<pubDate>Fri, 25 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


def test_parse_atom_and_rss():
    atom = parse_feed(REDDIT_ATOM)
    assert atom[0]["title"] == "Painter recommendations?" and atom[0]["author"] == "/u/homeowner804"
    assert atom[0]["link"].startswith("https://www.reddit.com/r/rva/")
    rss = parse_feed(RSS)
    assert rss[0]["id"] == "bid-42" and rss[0]["published"].startswith("2026-09-25")


def test_reddit_url():
    assert reddit_url("r/rva", "painter OR painting").startswith("https://www.reddit.com/r/rva/search.rss?q=painter")
    assert reddit_url("norfolk") == "https://www.reddit.com/r/norfolk/new/.rss"


def test_feed_listener_survives_a_dead_feed():
    web = FakeWeb({"https://dead.example": RuntimeError("HTTP 429"), "https://www.reddit.com": REDDIT_ATOM})
    listener = FeedListener("social", ["https://dead.example/rss", reddit_url("rva")], fetcher=web)
    found = list(listener.listen())
    assert len(found) == 2 and listener.errors and "dead.example" in listener.errors[0]
    assert "Looking for a painter" in found[0].body and "<p>" not in found[0].body


# -------------------------------------------------------------------- rules
SOCIAL_RULES = RuleSet.from_config({
    "require_title_any": ["painter", "painting"], "intent_any": ["looking for", "need a", "recommend"],
    "exclude_any": ["[for hire]"], "geo_any": ["henrico", "richmond"], "urgent_any": ["asap"],
    "boost": {"looking for": 15, "quote": 10}, "min_score": 35,
})


def test_rules_gate_on_title_and_intent():
    good = lead("Painter recommendations?", body="Looking for a painter in Henrico, need a quote ASAP")
    score, urgency, reasons = SOCIAL_RULES.score(good)
    assert score == 20 + 15 + 10 + 15 + 15 and urgency == "CRITICAL"
    assert any("in area" in r for r in reasons)
    assert SOCIAL_RULES.score(lead("Fun weekend", body="painting class, looking for fun"))[0] == 0
    assert SOCIAL_RULES.score(lead("Painting is relaxing", body="just a thought"))[2] == ["no buying intent"]
    assert SOCIAL_RULES.score(lead("[For Hire] Painter available", body="need a job"))[0] == 0


def test_rules_merge_boosts():
    merged = RuleSet.from_config({"boost": {"a": 1}}).merged({"boost": {"b": 2}, "min_score": 5})
    assert merged.boost == {"a": 1, "b": 2} and merged.min_score == 5


# ----------------------------------------------------------------- pipeline
def test_pipeline_routes_drops_and_remembers(tmp_path):
    store, sink = SeenStore(str(tmp_path / "s.db")), RecordingSink()
    pipeline = Pipeline(store, RuleSet.from_config({"require_any": ["painter"], "min_score": 20}), [sink])
    report = pipeline.process([lead(ext="1"), lead("Lunch plans", ext="2")])
    assert [x.external_id for x in report.routed] == ["1"] and len(report.dropped) == 1
    again = pipeline.process([lead(ext="1"), lead("Lunch plans", ext="2")])
    assert again.duplicates == 2 and not again.routed          # dropped leads aren't re-scored forever
    assert len(sink.sent) == 1 and store.counts() == {"ROUTED": 1, "DROPPED": 1}


def test_pipeline_catches_cross_posts():
    pipeline = Pipeline(SeenStore(), RuleSet(), [RecordingSink()])
    pipeline.process([lead(source="reddit", ext="a", contact="bob")])
    assert pipeline.process([lead(source="google-alert", ext="zzz", contact="bob")]).duplicates == 1


def test_sink_failure_does_not_lose_the_lead(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    pipeline = Pipeline(SeenStore(), RuleSet(), [RecordingSink(fail=True), JsonlSink(str(ledger))])
    report = pipeline.process([lead()])
    assert report.errors and "down" in report.errors[0]
    assert json.loads(ledger.read_text())["title"] == "Need a painter for 3 rooms"


def test_dry_run_sends_and_remembers_nothing():
    store, sink = SeenStore(), RecordingSink()
    Pipeline(store, RuleSet(), [sink], dry_run=True).process([lead()])
    assert not sink.sent and store.counts() == {}


def test_per_source_rules():
    pipeline = Pipeline(SeenStore(), RuleSet.from_config({"min_score": 90}), [],
                        source_rules={"inbound": {"min_score": 0}})
    assert pipeline.process([lead(source="inbound")]).routed
    assert not pipeline.process([lead(source="elsewhere")]).routed


# -------------------------------------------------------------------- sinks
def test_board_payload_matches_apps_script():
    payload = sam_to_lead(SAM_RECORD, "sam-painting").to_board()
    assert payload["action"] == "intake" and payload["lead_id"].startswith("LD-SAMPAI-")
    for key in ("listener_channel", "source_medium", "source_contact", "origin", "cargo_summary",
                "payout_offered", "urgency_level", "window_deadline", "detail_url", "lead_score"):
        assert key in payload


def test_lead_board_sink_accepts_duplicate_and_rejects_error():
    LeadBoardSink("https://board", FakeWeb({"https://board": {"status": "DUPLICATE"}})).send(lead())
    with pytest.raises(RuntimeError):
        LeadBoardSink("https://board", FakeWeb({"https://board": {"status": "ERROR", "message": "x"}})).send(lead())


def test_slack_only_pings_high_and_above():
    web = FakeWeb()
    slack = SlackSink("https://hooks.slack", "HIGH", web)
    slack.send(lead(urgency="MEDIUM"))
    slack.send(lead(urgency="CRITICAL", url="https://x.example", score=88))
    assert len(web.calls) == 1
    assert "<https://x.example|Need a painter" in json.loads(web.calls[0]["data"])["text"]


# ------------------------------------------------------------------ webhook
def test_form_and_sms_mapping():
    form = from_json({"name": "Sam K", "phone": "804-555-0101", "service": "Cabinet painting",
                      "message": "Kitchen cabinets", "budget": "$2,400", "zip": "23226"}, "inbound")
    assert form.title == "Cabinet painting" and form.value == 2400 and form.location == "23226"
    assert form.medium == "Direct Form" and "804-555-0101" in form.contact
    sms = from_twilio({"Body": "Need hot shot run Ashland to Petersburg $150", "From": "+18045550123",
                       "MessageSid": "SM1", "FromState": "VA"}, "inbound")
    assert sms.medium == "SMS" and sms.value == 150 and sms.external_id == "SM1"


@pytest.fixture
def live_server():
    sink = RecordingSink()
    pipeline = Pipeline(SeenStore(), RuleSet(), [sink])
    server = serve(pipeline, "s3cret", "127.0.0.1", 0, "inbound")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", sink
    server.shutdown()


def _post(url, body, content_type="application/json", token=None):
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=5) as reply:
        return reply.status, reply.read().decode()


def test_webhook_end_to_end(live_server):
    base, sink = live_server
    with pytest.raises(urllib.error.HTTPError) as denied:
        _post(base + "/leads", "{}")
    assert denied.value.code == 401
    status, body = _post(base + "/leads", json.dumps([{"id": "f1", "title": "Paint my porch"},
                                                      {"id": "f2", "title": "Deck stain"}]), token="s3cret")
    assert status == 200 and len(json.loads(body)["routed"]) == 2
    status, body = _post(base + "/sms?token=s3cret", "Body=Need+courier+now&From=%2B18045550100&MessageSid=SM9",
                         "application/x-www-form-urlencoded")
    assert status == 200 and "<Response/>" in body
    assert [x.medium for x in sink.sent] == ["Direct Form", "Direct Form", "SMS"]
    with urllib.request.urlopen(base + "/health", timeout=5) as reply:
        assert json.loads(reply.read())["status"] == "ok"


def test_webhook_refuses_to_start_without_token():
    with pytest.raises(ValueError):
        serve(Pipeline(SeenStore(), RuleSet()), "", "127.0.0.1", 0)


# ------------------------------------------------------------ config & CLI
def test_example_config_builds_and_skips_missing_keys(monkeypatch, tmp_path):
    for var in ("SAM_API_KEY", "LEADS_IMAP_USER", "LEADS_IMAP_PASSWORD", "LEAD_BOARD_API_URL", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LEADS_WEBHOOK_TOKEN", "t")
    config = config_module.load(config_module.__file__.replace("config.py", "config.example.json"))
    system = config_module.build(config, store_path=str(tmp_path / "s.db"))
    assert {n for n, _ in system.skipped} == {"sam-painting", "inbox", "reddit-replies"}
    assert system.listeners == []               # Reddit scraping is parked: Vinny posts, replies come by email
    assert system.webhook["token"] == "t"
    assert [s.name for s in system.pipeline.sinks] == ["ledger"]    # no board/slack without URLs


def test_env_expansion(monkeypatch):
    monkeypatch.setenv("X_KEY", "abc")
    assert config_module.expand({"a": ["${X_KEY}", "${MISSING:-dflt}", "${MISSING}"]}) == {"a": ["abc", "dflt", ""]}


def test_sweep_honours_min_interval(tmp_path):
    web = FakeWeb({"https://api.sam.gov": {"totalRecords": 1, "opportunitiesData": [SAM_RECORD]}})
    config = {"store": str(tmp_path / "s.db"), "listeners": [
        {"name": "sam", "kind": "sam", "api_key": "K", "naics": ["238320"], "set_asides": ["SDVOSBC"],
         "min_interval_minutes": 60}]}
    system = config_module.build(config, fetcher=web)
    assert len(sweep(system).routed) == 1
    sweep(system)
    assert len(web.calls) == 1                                      # second sweep skipped: not due
    sweep(system, force=True)
    assert len(web.calls) == 2


# ------------------------------------------- Session 1, semi-architect run
def test_chrome_find_uses_its_url_as_id():
    find = from_json({"title": "Need painter", "url": "https://fb.example/posts/1", "via": "chrome"}, "inbound")
    assert find.external_id == "https://fb.example/posts/1" and "chrome" in find.tags


def test_intake_page_and_cors(live_server):
    base, _ = live_server
    with pytest.raises(urllib.error.HTTPError) as denied:
        urllib.request.urlopen(base + "/intake", timeout=5)
    assert denied.value.code == 401
    with urllib.request.urlopen(base + "/intake?token=s3cret", timeout=5) as reply:
        page = reply.read().decode()
        assert reply.headers["Content-Type"].startswith("text/html") and 'fetch("/leads"' in page
    preflight = urllib.request.Request(base + "/leads", method="OPTIONS")
    with urllib.request.urlopen(preflight, timeout=5) as reply:
        assert reply.status == 204 and "Authorization" in reply.headers["Access-Control-Allow-Headers"]


def test_webhook_sink_sends_idempotent_authenticated_posts():
    from leads.sinks import WebhookSink
    web = FakeWeb()
    sink = WebhookSink("mid-atlantic", "https://mab.example/api/webhooks/leads", "tok", "board", "HIGH", web)
    sink.send(lead(urgency="LOW"))
    sink.send(lead(urgency="CRITICAL"))
    assert len(web.calls) == 1
    call = web.calls[0]
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["headers"]["Idempotency-Key"] == lead().lead_id
    assert json.loads(call["data"])["cargo_summary"] == "Need a painter for 3 rooms"


def test_webhook_sinks_come_from_config(tmp_path):
    config = {"store": str(tmp_path / "s.db"), "sinks": {"webhooks": [
        {"name": "mab", "url": "https://mab.example"}, {"name": "off", "url": ""}]}}
    assert [s.name for s in config_module.build(config).pipeline.sinks] == ["mab"]


def test_digest_reads_board_and_ranks():
    from datetime import datetime, timezone
    from leads import digest
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    board = {"status": "SUCCESS", "leads": [
        {"cargo_summary": "Old one", "timestamp": "2026-09-25T10:00:00Z", "urgency_level": "CRITICAL",
         "triage_status": "NEW", "lead_score": 99},
        {"cargo_summary": "Medium job", "timestamp": "2026-09-27T09:00:00Z", "urgency_level": "MEDIUM",
         "triage_status": "NEW", "lead_score": 50},
        {"cargo_summary": "Hot job", "timestamp": "2026-09-27T08:00:00Z", "urgency_level": "HIGH",
         "triage_status": "WATCH", "lead_score": 72, "detail_url": "https://sam.gov/x"},
        {"cargo_summary": "Taken", "timestamp": "2026-09-27T08:00:00Z", "urgency_level": "CRITICAL",
         "triage_status": "ACCEPTED", "lead_score": 90},
    ]}
    rows = digest.from_board("https://board/exec", FakeWeb({"https://board": board}))
    picked = digest.select(rows, hours=24, top=5, now=now)
    assert [r["title"] for r in picked] == ["Hot job", "Medium job"]
    text = digest.render(picked, 24, "https://board.view")
    assert "<https://sam.gov/x|Hot job>" in text and text.endswith("https://board.view")
    assert "nothing new" in digest.render([], 24)


def test_reddit_replies_route_by_sender_and_channel():
    reply = EmailMessage()
    reply["From"] = "Reddit <noreply@redditmail.com>"
    reply["Subject"] = "u/rva_homeowner replied to your post in r/rva"
    reply["Message-ID"] = "<r1@reddit>"
    reply.set_content("Are you available next week? Can you give me a quote for two rooms?")
    imap = FakeImap({3: bytes(reply), 4: bytes(make_email())})
    replies = email_listener.EmailListener("reddit-replies", "imap", "u", "p", connect=lambda: imap,
                                           only_from=["redditmail.com"], channel="Local Community",
                                           tags=["reddit", "reply"])
    found = list(replies.listen())
    assert [x.title for x in found] == ["u/rva_homeowner replied to your post in r/rva"]
    assert found[0].channel == "Local Community" and found[0].tags == ["reddit", "reply"]
    inbox = email_listener.EmailListener("inbox", "imap", "u", "p", connect=lambda: FakeImap({3: bytes(reply), 4: bytes(make_email())}),
                                         skip_from=["redditmail.com"])
    assert [x.title for x in inbox.listen()] == ["RFQ: exterior painting, Chesapeake warehouse"]


# ------------------------------------------------- Reddit thread interrogation
def _listing(*children):
    return {"data": {"children": list(children)}}


def _thread_json():
    post = {"kind": "t3", "data": {"id": "abc", "title": "Best way to find a painter in RVA?", "author": "vinny_rva",
                                   "subreddit": "rva", "selftext": "Thoughts from a vet-owned shop.",
                                   "permalink": "/r/rva/comments/abc/best_way/", "created_utc": 1790500000}}
    reply_to_me = {"kind": "t1", "data": {"name": "t1_c2", "id": "c2", "author": "homeowner", "parent_id": "t1_c1",
                                          "body": "Are you available next week? Need a quote for 3 rooms, budget $1,800",
                                          "permalink": "/r/rva/comments/abc/best_way/c2/", "created_utc": 1790501000}}
    mine = {"kind": "t1", "data": {"name": "t1_c1", "id": "c1", "author": "vinny_rva", "parent_id": "t3_abc",
                                   "body": "We do this.", "permalink": "/r/rva/comments/abc/best_way/c1/",
                                   "created_utc": 1790500500,
                                   "replies": {"data": {"children": [reply_to_me]}}}}
    chatter = {"kind": "t1", "data": {"name": "t1_c3", "id": "c3", "author": "lurker", "parent_id": "t3_abc",
                                      "body": "Nice weather today.", "permalink": "/r/rva/comments/abc/best_way/c3/",
                                      "created_utc": 1790502000}}
    more = {"kind": "more", "data": {}}
    return [_listing(post), _listing(mine, chatter, more)]


def test_thread_listener_interrogates_threads_i_joined():
    from datetime import datetime, timezone
    from leads.listeners.reddit_threads import RedditThreadListener
    joined = {"kind": "t1", "data": {"name": "t1_c1", "link_id": "t3_abc", "created_utc": 1790500500,
                                     "permalink": "/r/rva/comments/abc/best_way/c1/"}}
    web = FakeWeb({
        "https://www.reddit.com/user/vinny_rva/comments.json": _listing(joined),
        "https://www.reddit.com/user/vinny_rva/submitted.json": _listing(),
        "https://www.reddit.com/r/rva/comments/abc/best_way.json": _thread_json(),
    })
    store = SeenStore()
    listener = RedditThreadListener("reddit-threads", "u/vinny_rva", fetcher=web, store=store,
                                    now=datetime(2026, 9, 27, tzinfo=timezone.utc))
    found = {x.external_id: x for x in listener.listen()}
    assert set(found) == {"t3_abc", "t1_c2", "t1_c3"}                 # thread + other people's comments, not mine
    assert "1 replies to you" in found["t3_abc"].body and "$1,800" in found["t3_abc"].body
    assert "you-started-it" in found["t3_abc"].tags
    assert "reply-to-you" in found["t1_c2"].tags and found["t1_c2"].url.endswith("/c2/")
    assert list(listener.listen()) == []                              # re-check: nothing new, nothing repeated

    rules = RuleSet.from_config({"boost": {"reddit-thread": 20, "reply-to-you": 20, "quote": 15}, "min_score": 35})
    report = Pipeline(SeenStore(), rules, []).process(found.values())
    assert {x.external_id for x in report.routed} == {"t3_abc", "t1_c2"}   # chatter dropped


def test_owned_groups_watch_every_thread():
    from datetime import datetime, timezone
    from leads.listeners.reddit_threads import RedditThreadListener
    post = {"kind": "t3", "data": {"id": "abc", "created_utc": 1790500000, "permalink": "/r/rva/comments/abc/best_way/"}}
    web = FakeWeb({"https://www.reddit.com/r/mytribe/new.json": _listing(post),
                   "https://www.reddit.com/r/rva/comments/abc/best_way.json": _thread_json()})
    listener = RedditThreadListener("owned-groups", "vinny_rva", fetcher=web, subreddits=["r/mytribe"],
                                    follow_user=False, tags=["owned", "recruit"],
                                    now=datetime(2026, 9, 27, tzinfo=timezone.utc))
    found = list(listener.listen())
    assert len(found) == 3 and all("recruit" in x.tags for x in found)
    assert not any("/user/" in call["url"] for call in web.calls)


# --------------------------------------------------------- eBay metal & gem hunt
from leads import valuation  # noqa: E402


@pytest.mark.parametrize("title, metal, ozt", [
    ("Sterling Silver Scrap Lot 125 grams", "silver", 3.7174),
    ("LOT OF 10 Morgan Silver Dollars", "silver", 7.734),
    ("$10 FACE 90% Junk Silver Dimes", "silver", 7.15),
    ("14K Yellow Gold Chain 12.4 grams", "gold", 0.2332),
    ("10k gold ring 3.2 dwt", "gold", 0.0667),
    ("1/10 oz Gold American Eagle 2021", "gold", 0.1),
    ("Vintage sterlng silver spoon 40g", "silver", 1.1896),
    (".999 fine gold bar 1 oz", "gold", 0.999),
    ("1 oz .999 Fine Silver Round", "silver", 0.999),
    ("Estate: 14k jewelry, sterling flatware service 1200 grams", "silver", 35.6873),
])
def test_read_metal(title, metal, ozt):
    reading = valuation.read_metal(title)
    assert reading.metal == metal and reading.ozt == pytest.approx(ozt, abs=1e-3)


@pytest.mark.parametrize("title", ["Silver plated tray 500g", "Gold filled 14k 1/20 bracelet 10g",
                                   "Silver tone necklace", "Weighted sterling candlesticks 900g",
                                   "Sterling silver ring (no weight)"])
def test_read_metal_refuses_fakes_and_guesses(title):
    assert valuation.read_metal(title) is None


def test_read_gem():
    gem = valuation.read_gem("GIA Certified 1.52 ct Natural Blue Saphire")
    assert (gem.stone, gem.carats, gem.certified) == ("sapphire", 1.52, "GIA")
    assert gem.signals and "saphire" in gem.signals[0]
    assert valuation.read_gem("Lab Created Ruby 5ct").signals == ["fake"]


def _ebay_item(item_id, title, price, ship=0.0, auction=False, bids=0, ends="2026-09-27T20:00:00.000Z",
               feedback="99.8", score=1500):
    item = {"itemId": item_id, "title": title, "price": {"value": str(price), "currency": "USD"},
            "shippingOptions": [{"shippingCost": {"value": str(ship)}}],
            "buyingOptions": ["AUCTION"] if auction else ["FIXED_PRICE"], "bidCount": bids,
            "itemWebUrl": f"https://www.ebay.com/itm/{item_id}", "condition": "Pre-owned",
            "seller": {"username": "estate_seller", "feedbackPercentage": feedback, "feedbackScore": score},
            "itemLocation": {"postalCode": "232**", "country": "US"}}
    if auction:
        item["currentBidPrice"] = {"value": str(price)}
        item["itemEndDate"] = ends
    return item


def test_ebay_hunt_end_to_end():
    from datetime import datetime, timezone
    from leads.listeners.ebay import EbayHuntListener
    search = {"itemSummaries": [
        _ebay_item("1", "Sterling Silver Flatware Lot 400 grams", 250, ship=15),        # melt 356.8 → 26% under
        _ebay_item("2", "Sterling Silver Bracelet 20g", 60, ship=5),                    # melt 17.8 → way over
        _ebay_item("3", "Silver plated tray 900g", 20),                                  # plated → no reading
        _ebay_item("4", "14k gold ring 5 grams", 150, auction=True, bids=0),            # melt 235 → 36% under, ends soon
    ]}
    gems = {"itemSummaries": [
        _ebay_item("5", "Natural Blue Saphire 2.0 ct loose", 120),                      # $60/ct, misspelled
        _ebay_item("6", "Lab Created Sapphire 10 ct", 20),
    ]}
    web = FakeWeb({"https://api.ebay.com/identity": {"access_token": "T", "expires_in": 7200},
                   "https://api.ebay.com/buy/browse/v1/item_summary/search?q=sterling": search,
                   "https://api.ebay.com/buy/browse/v1/item_summary/search?q=saphire": gems})
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    metals = EbayHuntListener("ebay-metals", "id", "secret", [{"hunt": "silver", "q": "sterling", "max_price": 500}],
                              spot={"silver": "30", "gold": "2500"}, fetcher=web, now=now)
    stones = EbayHuntListener("ebay-gems", "id", "secret", [{"hunt": "gem", "q": "saphire"}],
                              max_ppc={"sapphire": 100}, fetcher=web, now=now)
    found = {x.external_id: x for x in list(metals.listen()) + list(stones.listen())}

    token_call = web.calls[0]
    assert token_call["method"] == "POST" and token_call["headers"]["Authorization"].startswith("Basic ")
    assert b"client_credentials" in token_call["data"]
    search_call = web.calls[1]
    assert search_call["headers"]["Authorization"] == "Bearer T"
    assert "price%3A%5B..500%5D" in search_call["url"]

    assert "26% under melt" in " ".join(r for _, r in found["1"].bonus)
    assert found["1"].value == 265.0 and "melt $356" in found["1"].body
    assert any(p < 0 for p, _ in found["2"].bonus)
    assert "weight/purity not in title" in found["3"].body

    pipeline = Pipeline(SeenStore(), RuleSet.from_config({"min_score": 45}), [])
    routed = {x.external_id for x in pipeline.process(found.values()).routed}
    assert routed == {"1", "4", "5"}   # the metal reader spots gold even when it turns up in a silver search
    assert any("misspelled" in r for _, r in found["5"].bonus)
    assert any("$60/ct" in r for _, r in found["5"].bonus)


def test_ebay_gold_auction_ending_soon():
    from datetime import datetime, timezone
    from leads.listeners.ebay import EbayHuntListener
    web = FakeWeb({"https://api.ebay.com/identity": {"access_token": "T"},
                   "https://api.ebay.com/buy/browse": {"itemSummaries": [
                       _ebay_item("4", "14k gold ring 5 grams", 150, auction=True, bids=0)]}})
    hunt = EbayHuntListener("ebay-metals", "id", "secret", [{"hunt": "gold", "q": "14k", "buying": "AUCTION"}],
                            spot={"gold": 2500}, fetcher=web, now=datetime(2026, 9, 27, 12, tzinfo=timezone.utc))
    lead_ = next(hunt.listen())
    reasons = " ".join(r for _, r in lead_.bonus)
    assert "under melt" in reasons and "no bids" in reasons and "ending-soon" in lead_.tags
    assert "sort=endingSoonest" in web.calls[1]["url"]
    score, urgency, _ = RuleSet.from_config({"min_score": 45}).score(lead_)
    assert score >= 70 and urgency in ("HIGH", "CRITICAL")


def test_ebay_needs_keys_and_hunt_config_loads(monkeypatch, tmp_path):
    from leads.listeners.ebay import EbayHuntListener
    with pytest.raises(ValueError):
        EbayHuntListener("x", "", "", [])
    monkeypatch.setenv("EBAY_CLIENT_ID", "a")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "b")
    config = config_module.load(config_module.__file__.replace("config.py", "hunts.example.json"))
    system = config_module.build(config, store_path=str(tmp_path / "h.db"))
    assert {x.name for x in system.listeners} == {"ebay-metals", "ebay-gems", "gsa-auctions"}
    assert "estate-mail" in {n for n, _ in system.skipped}      # needs the inbox login


def test_ebay_hunt_keeps_no_seller_username():
    from datetime import datetime, timezone
    from leads.listeners.ebay import EbayHuntListener
    web = FakeWeb({"https://api.ebay.com/identity": {"access_token": "T"},
                   "https://api.ebay.com/buy/browse": {"itemSummaries": [
                       _ebay_item("9", "Sterling Silver Lot 400 grams", 200)]}})
    hunt = EbayHuntListener("ebay-metals", "id", "secret", [{"hunt": "silver", "q": "x"}], spot={"silver": 30},
                            fetcher=web, now=datetime(2026, 9, 27, tzinfo=timezone.utc))
    record = json.dumps(next(hunt.listen()).to_dict())
    assert "estate_seller" not in record and "99.8%" in record


def test_ebay_deletion_challenge_and_purge(monkeypatch):
    import hashlib
    from leads.listeners.webhook import ebay_challenge
    token, endpoint = "t" * 40, "https://leads.example.com/ebay/account-deletion"
    assert ebay_challenge("abc", token, endpoint) == hashlib.sha256(("abc" + token + endpoint).encode()).hexdigest()
    assert ebay_challenge("abc", "", endpoint) == ""

    monkeypatch.setenv("EBAY_VERIFICATION_TOKEN", token)
    monkeypatch.setenv("EBAY_DELETION_ENDPOINT", endpoint)
    store = SeenStore()
    store.record(lead(ext="k", contact="bob_the_seller"), "ROUTED")
    store.record(lead(ext="j", title="Other", contact="alice"), "ROUTED")
    server = serve(Pipeline(store, RuleSet()), "s3cret", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/ebay/account-deletion"
    try:
        with urllib.request.urlopen(base + "?challenge_code=xyz", timeout=5) as reply:
            assert json.loads(reply.read())["challengeResponse"] == ebay_challenge("xyz", token, endpoint)
        body = json.dumps({"metadata": {"topic": "MARKETPLACE_ACCOUNT_DELETION"},
                           "notification": {"data": {"username": "bob_the_seller", "userId": "u1"}}})
        request = urllib.request.Request(base, data=body.encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as reply:
            assert reply.status == 204
        assert store.counts() == {"ROUTED": 1}
    finally:
        server.shutdown()


def test_gsa_auctions_listener_reads_lots_and_melt():
    from leads.listeners.gsa_auctions import GsaAuctionsListener
    rows = {"Results": [
        {"SaleNo": "31QSCI26", "LotNo": "101", "ItemName": "14K Gold Rings 20 grams", "LotDescript": "Seized jewelry",
         "PropertyCity": "Norfolk", "PropertyState": "VA", "AuctionStatus": "A", "HighBidAmount": "400.00",
         "BiddersCount": 3, "AucEndDt": "2026-10-02 15:00", "ItemDescURL": "https://gsaauctions.gov/lot/101",
         "AgencyName": "Treasury"},
        {"SaleNo": "31QSCI26", "LotNo": "102", "ItemName": "Sterling silver flatware", "PropertyState": "TX",
         "AuctionStatus": "A", "HighBidAmount": "0"},
        {"SaleNo": "31QSCI26", "LotNo": "103", "ItemName": "Office chairs", "PropertyState": "VA", "AuctionStatus": "A"},
    ]}
    web = FakeWeb({"https://api.gsa.gov/assets/gsaauctions": rows})
    listener = GsaAuctionsListener("gsa-auctions", "", states=["VA"], spot={"gold": "2500"}, fetcher=web)
    found = {x.external_id: x for x in listener.listen()}
    assert set(found) == {"31QSCI26-101", "31QSCI26-103"}          # TX lot filtered by state
    assert "DEMO_KEY" in web.calls[0]["url"] and "format=JSON" in web.calls[0]["url"]
    ring = found["31QSCI26-101"]
    assert ring.location == "Norfolk, VA" and ring.value == 400.0
    assert any("under melt" in r for _, r in ring.bonus)           # 20g 14k ~ $940 melt vs $400
    rules = RuleSet.from_config({"require_any": ["gold", "silver", "jewelry"], "min_score": 35})
    routed = {x.external_id for x in Pipeline(SeenStore(), rules, []).process(found.values()).routed}
    assert routed == {"31QSCI26-101"}


def test_estate_mail_reads_metal_from_alerts():
    alert = EmailMessage()
    alert["From"] = "EstateSales.NET <alerts@estatesales.net>"
    alert["Subject"] = "New sale near you: Henrico estate - sterling flatware, 14k jewelry"
    alert["Message-ID"] = "<e1@esn>"
    alert.set_content("Sterling silver flatware service 1200 grams. Online only, no reserve.")
    listener = email_listener.EmailListener("estate-mail", "imap", "u", "p", connect=lambda: FakeImap({8: bytes(alert)}),
                                            channel="Local Community", tags=["estate"], spot={"silver": "30"})
    found = next(listener.listen())
    assert "ozt silver" in found.body and any("melt" in r for _, r in found.bonus)
