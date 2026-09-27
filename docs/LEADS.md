# Lead system

Four listeners, one pipeline, humans at the board.

```
 PULL (python -m leads sweep)                 PUSH (python -m leads serve)
 ┌──────────────┐ ┌──────────┐ ┌───────────┐   ┌───────────────────────────┐
 │ Bids         │ │ Email    │ │ Social    │   │ Inbound lead listener     │
 │ SAM.gov v2   │ │ IMAP     │ │ Reddit,   │   │ forms · Zapier · Twilio   │
 │              │ │          │ │ RSS/Atom, │   │ SMS · other bots          │
 │              │ │          │ │ G. Alerts │   │ POST /leads  POST /sms    │
 └──────┬───────┘ └────┬─────┘ └─────┬─────┘   └────────────┬──────────────┘
        └──────────────┴──────┬──────┴──────────────────────┘
                              ▼
                  Lead  (one shape, stable id)
                              ▼
          dedupe  — seen-store: same item, or same job cross-posted
                              ▼
          score   — rules only: gates, veto, boosts, geo, urgency
                              ▼
       ┌──────────────────────┼─────────────────────┐
       ▼                      ▼                     ▼
  lead board             Slack #leads           JSONL ledger
  (human triage:         (HIGH/CRITICAL         (everything routed,
   ACCEPT / BID / …)      only)                  replayable)
```

Stdlib only. Every decision (routed, dropped or duplicate) is written to the store,
so "why didn't I see that?" always has an answer: `python -m leads recent`.

## Quick start

```bash
cp leads/config.example.json leads.config.json     # edit rules, subreddits, folders
export LEAD_BOARD_API_URL=https://script.google.com/macros/s/…/exec
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/…
python -m leads check                # what's ready, what's missing a key
python -m leads sweep --dry-run      # score and print, send nothing, remember nothing
python -m leads sweep                # for real
python -m leads recent               # last routed leads
python -m leads digest --send        # top open leads of the last 24h → Slack
```

## Destinations

- **Lead board** (`LEAD_BOARD_API_URL`): the triage queue. Every sweeper converges here.
- **Slack** (`SLACK_WEBHOOK_URL`): HIGH and CRITICAL only, plus the 7:48am digest.
- **Other systems** (`sinks.webhooks`): e.g. the Mid-Atlantic Lead Board
  (`MIDATLANTIC_WEBHOOK_URL` / `_TOKEN`). Bearer auth, `Idempotency-Key` = lead id,
  optional `min_urgency`.
- **Ledger** (`var/leads.jsonl`): everything routed, for replay.

The digest reads the **board**, not a local store, so it sees leads from every
sweeper: Actions, the 5090 box, Chrome, and inbound forms.

## The listeners

| Listener | Kind | Needs | Notes |
| --- | --- | --- | --- |
| Bids | `sam` | `SAM_API_KEY` — sam.gov → Account Details → Public API Key | Ultra-Thin v0 scope: NAICS 238320, SDVOSB + small-business set-asides, place of performance VA/MD/NC/DC. One request per NAICS × set-aside; state filtered locally. `min_interval_minutes: 480` protects the small daily quota. |
| Email | `email` | `LEADS_IMAP_USER`, `LEADS_IMAP_PASSWORD` (Gmail: an **App Password**) | Read-only (`BODY.PEEK`), UID cursor so each message is seen once. Point it at a **Leads** label fed by a Gmail filter, not the whole inbox. |
| Social | `feed` | nothing (Google Alerts: an RSS URL) | Any RSS/Atom URL, gated on *topic in title* **and** *buying intent*. The Reddit presets are **parked** (see below). |
| Reddit replies | `email` (`reddit-replies`) | same IMAP login | **Reddit is human-first:** Vinny posts as himself, and people reply. Reddit's reply and message notification emails land in the Leads label, and every reply is routed (`min_score: 0`) as feedback to look at. |
| Inbound | `webhook` | `LEADS_WEBHOOK_TOKEN` | `POST /leads` takes one JSON object or an array — common form field names (`name`, `phone`, `service`, `message`, `budget`, `zip`…) are mapped automatically. `POST /sms` takes Twilio's inbound webhook as-is. Auth by `Authorization: Bearer` or `?token=`. |

**Human touch moved to X/Twitter.** Vinny posts on X in his own voice;
replies, mentions, quote-posts and DMs arrive as X's notification emails in the
Human Network inbox, and `x-replies` puts them on the board (every one routes,
minus login/security/digest mail). No X API (reads are paid), and no scraping.
Turn on X's email notifications for replies, mentions and DMs, and add a Gmail
filter: from `x.com OR twitter.com` → label Leads. Claude can draft posts and
threads; Vinny edits and posts them himself.

**Reddit: Vinny posts, the system listens for replies.** Scraping Reddit
from servers gets throttled, and cold-reading strangers' posts is the weaker
channel anyway. Vinny posts in local and tribe subreddits as a real
redditor. Replies and DMs arrive as Reddit notification emails, and the
`reddit-replies` listener puts them on the board. Claude can draft posts;
Vinny publishes them.

**Threads Vinny joins get interrogated** (`reddit-threads`, on the 5090).
Every thread he comments in or starts is read in full: the post plus every
comment, re-checked for 7 days. You get one thread lead (asks, amounts,
replies to you) and a lead per new comment. The rules route the ones with
intent, and anything `reply-to-you`.

**Groups we own** (`owned-groups`, `OWNED_SUBREDDITS`). Recruiting runs
through Vinny's own subreddits, so every thread in them is watched, with
recruiting rules ("interested", "I drive", "I paint", "looking for work").
These are tagged `recruit` and kept on the lead board only. Nothing is wired
to the physical guild.

**Cross-pollination.** Vinny posts thoughtful threads in his own voice:
local subs, technical groups, the groups we own. The thread listener reads
what comes back. Claude can help draft; Vinny edits, owns and posts. Follow
each subreddit's rules on self-promotion and AI-assisted posts.

**Keyword-pair news searches.** `news-distributors` runs Vinny's hand searches
("Richmond" distributors, "Virginia" distributors, distribution center,
warehouse opening…) as Google News RSS every sweep, and deciphers each story.
The same pairs can be **Google Alerts in the Human Network (HMTCHS) account**,
delivered to its inbox. The `google-alerts` listener reads and deciphers those
(Gmail filter: from `googlealerts-noreply@google.com` → Leads).

**Paste a clip, get a lead.** Same move as the ChatGPT RSS-leads window: paste a
news clip, email, post or bid notice into the **Paste a clip** box on
`/intake?token=…`, or send `{"clip": "..."}` to `/leads`, and `leads/decipher.py`
pulls out the title, contact (name, email, phone), location, dollar amount,
deadline and link. Then it goes through scoring and onto the board. Rules
always run. On the 5090, set `OLLAMA_URL=http://localhost:11434` (and
optionally `OLLAMA_MODEL`) and a local model reads the clip first, with the
rules filling any blanks. No paid API, and nothing leaves the machine.

**Claude in Chrome as a listener.** For sources with no feed or API (Facebook
groups, Nextdoor, eVA and portals behind a login), Claude in Chrome works them
in the real browser and posts each find from the listener's own
`/intake?token=…` page, following `pipeline/lead-system/chrome-listener.md`. The finds get the same
dedupe, scoring and board as everything else.

Adding a source is usually config, not code: another subreddit, another RSS
URL, another NAICS code. A new *kind* of source is one file in
`leads/listeners/` that yields `Lead` objects.

## Tuning the rules

Global rules sit under `"rules"`; each listener can layer its own on top
(`boost` merges, everything else replaces). Gates: `require_any`,
`require_title_any`, `intent_any`. Veto: `exclude_any`. Points: base 20,
`boost` terms, `geo_any` (+`geo_points`), stated value (+5), `urgent_any` (+15).
Urgency: CRITICAL = urgent and ≥60 · HIGH = ≥70 or urgent · MEDIUM ≥40 · else LOW.

Tune with `sweep --dry-run`: each routed lead prints its score, and
`--json` shows the reasons behind it.

## Where it runs

| Option | Good for | Setup |
| --- | --- | --- |
| **GitHub Actions** (`.github/workflows/lead-sweep.yml`) | Bids + email, zero servers | Add the secrets; it runs every 30 min 7am–7pm ET, SAM twice a day. Seen-store persists in the Actions cache. |
| **Fly.io** (`leads/deploy/`) | The always-on inbound listener, plus a sweep loop | `fly launch`, a 1 GB volume, secrets, deploy — commands are in `fly.toml`. |
| **The 5090 box** (`leads/deploy/5090/`) | Social feeds, inbound listener, Chrome intake | Windows kit: `.env`, `start-leads.ps1`, `start-tunnel.ps1` (Cloudflare), `install-autostart.ps1`. Reddit throttles datacenter IPs (Actions, Fly) with HTTP 429; a home connection isn't. |

Run **one** scheduler per store. If two run anyway, the board rejects the
repeat (`DUPLICATE`), but Slack could ping twice.

## Lead board changes

`lead-board/apps-script/Code.gs` now:

- rejects a re-sent `lead_id` with `{"status": "DUPLICATE"}` instead of adding a second row
- stores three new columns: `detail_url` (http/https only), `lead_score`, `source_system`
- fills in missing header cells on sheets created before those columns existed

The board shows the score as a ★ badge and links the summary to the source.
**Redeploy the Apps Script** after merging (Deploy → Manage deployments → Edit → New version).

## Deliberately not in v0

- AI/LLM scoring — rules first, per the Maker/Breaker review; the Anomaly Listener / Researcher can consume routed leads later
- eVA, GSA eBuy and local bid boards — each will be its own listener
- Outreach, CRM and auto-replies — a human decides at the board
- Any link to the physical trade guild — kept separate by design
- Scraping sites without a feed or API — breaks site terms and breaks on layout changes
