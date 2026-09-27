# Build Card — Lead system (bids, email, social, inbound)

| | |
| --- | --- |
| **Status** | review |
| **Spec origin** | Vinny |
| **Build owner** | Claude Code |
| **Station 1 (Idea Forge)** | Claude web, 2026-09-27 |
| **Station 2 (Build Bay)** | Claude Code, 2026-09-27 — branch `leads/full-lead-system` |
| **Station 3 (Proving Ground)** | Claude desktop — checklist below |
| **Gates** | Vinny: greenlight after Station 1, merge after Station 3 |

## Problem

Leads arrive in four places (federal bid notices, the inbox, local social
posts, and direct inbound like forms and texts), and each one is checked by
hand, or not at all. Build a single system that listens to all four, throws
out noise with readable rules, and puts what's left on the existing lead board
for a human to triage.

## Done means

1. `python -m leads sweep` pulls SAM.gov (NAICS 238320, SDVOSB/SB set-asides, VA-area place of performance), a mail folder, and configured Reddit/RSS feeds, then routes passing leads to the lead board.
2. Re-running a sweep never duplicates a lead: not in the store, and not on the board.
3. Social posts route only when the topic is in the title **and** there is buying intent.
4. `POST /leads` (JSON) and `POST /sms` (Twilio) put an inbound lead on the board within seconds, and both require the token.
5. HIGH/CRITICAL leads ping Slack; lower-urgency leads don't.
6. A listener without credentials is skipped with a message; it doesn't crash the sweep. A single dead feed doesn't silence the others.
7. Tests run offline and cover every listener, the pipeline, the sinks and the webhook.

## Constraints and non-goals

- Stdlib only, Python 3.9+ (matches the rest of bot-factory)
- Rules-based scoring only: no LLM calls in v0
- No scraping of sites without a feed or API. No outreach or auto-reply.
- No link to the physical trade guild

## Interfaces

- **In:** SAM.gov Opportunities v2 · IMAP · RSS/Atom · HTTP POST
- **Out:** `lead-board/apps-script` `doPost` (action `intake`) · Slack incoming webhook · `var/leads.jsonl`
- **Touches:** `lead-board/apps-script/Code.gs` (dedupe + 3 columns) and `lead-board/board/index.html` (link + score)

## Station 3 checklist (Claude desktop, on Vinny's machine)

- [ ] `python -m leads check` shows each listener as ready once keys are set
- [ ] `sweep --dry-run` from the home IP: Reddit feeds return with no 429s, and the routed posts are real hiring intent
- [ ] One real SAM.gov sweep: the notices match a manual search on sam.gov with the same filters
- [ ] Email: a test message to the Leads label shows up once, and not on the next sweep
- [ ] Redeploy the Apps Script. Old sheet gains the 3 headers, links open, and a re-sent lead gets `DUPLICATE`
- [ ] `curl` a form lead and a fake Twilio SMS to `serve`. Both land on the board, and a HIGH lead pings Slack

## Open questions (for Vinny)

- Which Slack channel should get pings? `#courier-bids` exists; maybe a new `#leads`.
- Where does it live: Actions + Fly, or the 5090 box?
- Which subreddits and Google Alerts are worth adding beyond the starter set?

## Log

Conventions: pipeline/README.md. Station name on every entry; `[cross]` marks a decision that touches more than one station.


- 2026-09-27 · Claude Code: Built at Station 2. 24 new tests, full suite green (294 passed). Live dry run against Reddit: gates dropped the off-topic posts, and the cloud IP got 429s on some feeds (expected; see docs/LEADS.md).
- 2026-09-27 · Claude web · [cross]: Vinny set the pipeline as all-Claude (web → Code → desktop), loose rather than strict. Stations can work across each other's lanes, and cross-station decisions are logged here.
