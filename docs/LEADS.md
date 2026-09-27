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
```

## The listeners

| Listener | Kind | Needs | Notes |
| --- | --- | --- | --- |
| Bids | `sam` | `SAM_API_KEY` — sam.gov → Account Details → Public API Key | Ultra-Thin v0 scope: NAICS 238320, SDVOSB + small-business set-asides, place of performance VA/MD/NC/DC. One request per NAICS × set-aside; state filtered locally. `min_interval_minutes: 480` protects the small daily quota. |
| Email | `email` | `LEADS_IMAP_USER`, `LEADS_IMAP_PASSWORD` (Gmail: an **App Password**) | Read-only (`BODY.PEEK`), UID cursor so each message is seen once. Point it at a **Leads** label fed by a Gmail filter, not the whole inbox. |
| Social | `feed` | nothing (Google Alerts: an RSS URL) | Reddit search per subreddit + any RSS/Atom URL. Gated on *topic in title* **and** *buying intent* ("looking for", "need a", "recommend", "[hiring]") so chatter doesn't route. |
| Inbound | `webhook` | `LEADS_WEBHOOK_TOKEN` | `POST /leads` takes one JSON object or an array — common form field names (`name`, `phone`, `service`, `message`, `budget`, `zip`…) are mapped automatically. `POST /sms` takes Twilio's inbound webhook as-is. Auth by `Authorization: Bearer` or `?token=`. |

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
| **The 5090 box / any home machine** | Social feeds | `python -m leads loop --every 1800 --serve`, exposed with a Cloudflare Tunnel. Reddit throttles datacenter IPs (Actions, Fly) with HTTP 429; a residential IP is rarely throttled. |

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
