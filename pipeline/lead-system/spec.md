# Build Card — Lead system (bids, email, social, inbound)

| | |
| --- | --- |
| **Status** | review |
| **Spec origin** | Vinny |
| **Judge** | Claude Code |
| **Listener (internet layer)** | Claude in Chrome |
| **Station 1 (Idea Forge)** | Claude web, 2026-09-27 |
| **Build** | Claude Code, 2026-09-27 — branch `leads/full-lead-system` |
| **Sessions and reality lens** | Claude desktop: works with Vinny, tests on his machine (checklist below), and checks the leads against the real world |
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
3. Social posts route only when the topic is in the title **and** there is buying intent. Reddit is human-first: Vinny posts, and replies to his posts route to the board.
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
- [ ] From the 5090: `reddit-threads` reads a thread Vinny joined without 429s, and the routed comments are real asks or replies to him
- [ ] One real SAM.gov sweep: the notices match a manual search on sam.gov with the same filters
- [ ] Email (HMTCHS inbox): a test message to the Leads label shows up once, and not on the next sweep. A Reddit reply notification routes via `reddit-replies`
- [ ] Redeploy the Apps Script. Old sheet gains the 3 headers, links open, and a re-sent lead gets `DUPLICATE`
- [ ] `curl` a form lead and a fake Twilio SMS to `serve`. Both land on the board, and a HIGH lead pings Slack

## Borrow list

Already ours, to fold in instead of rebuilding:

- `lead-board/`: the Apps Script board is the triage queue (in use)
- Mid-Atlantic Lead Board (ChatGPT Apps SDK): has an authenticated `POST /api/webhooks/leads`. It could be a second sink next to the Apps Script board.
- Courier SMS listener on Fly.io and the Courier Alerts Slack app (`#courier-bids`): reuse the Fly app and Slack webhook instead of new ones
- `capabilities/anomaly` and `capabilities/research`: later, to flag unusual leads and research promising ones (v1, not v0)

Ask Gemini (library) what the NotebookLM notebooks already hold on lead
sources, bid hunting, and the listener pattern. Ask Grok to help with sources
and a Breaker pass.

## Chrome as listener

The code listeners cover sources with a feed or API. Claude in Chrome covers
everything else, working in Vinny's own signed-in browser at human pace:
Facebook groups, Nextdoor, local boards, eVA and county bid portals behind
logins. Reddit is Vinny's own (he posts; replies and joined threads are
read by listeners). For each real lead it finds, Chrome posts JSON to the
inbound listener (`/intake` page → `/leads`), so Chrome finds go
through the same dedupe, scoring and board as everything else. Chrome reads
and reports; replying to or bidding on a lead waits for Vinny.

## Open questions (for Vinny)

- Which Slack channel should get pings? `#courier-bids` exists; maybe a new `#leads`.
- Where does it live: Actions + Fly, or the 5090 box?
- Which subreddits and Google Alerts are worth adding beyond the starter set?

## Log

Conventions: pipeline/README.md. Station name on every entry; `[cross]` marks a decision that touches more than one station.


- 2026-09-27 · Claude Code: Built at Station 2. 24 new tests, full suite green (294 passed). Live dry run against Reddit: gates dropped the off-topic posts, and the cloud IP got 429s on some feeds (expected; see docs/LEADS.md).
- 2026-09-27 · Claude web · [cross]: Vinny set the pipeline as all-Claude (web → Code → desktop), loose rather than strict. Stations can work across each other's lanes, and cross-station decisions are logged here.
- 2026-09-27 · Claude web · [cross]: Vinny set the roles: Chrome = listener and worker at the internet layer, desktop = desktop duties, Claude Code = judge, Grok = occasional outside read. Chrome feeds leads through `POST /leads`.
- 2026-09-27 · Claude web · [cross]: Desktop also holds the sessions with Vinny and brings the different lenses that pull reality into focus. For this card: are the routed leads ones Vinny would actually chase?
- 2026-09-27 · Claude web · Session 1: First session of the pipeline, with Vinny. Set the roles and the loose rules (pipeline/README.md), and took the lead system from idea to PR #10. Next: judge verdict (fresh Claude Code session, Grok optional), then desktop's reality check with Vinny.
- 2026-09-27 · Claude web · [cross]: Vinny: borrow from our own work, ask Gemini for theirs, and bring Grok in to assist. Borrow list added.
- 2026-09-27 · Claude web · [5090]: Reddit feeds returned 429 from cloud IPs. Escalated: run `social-*` listeners on the 5090 box (`python -m leads loop --every 1800 --serve`, Cloudflare Tunnel for `/leads`).
- 2026-09-27 · Claude Code · [architect] (semi): Chrome listener. `/leads` accepts CORS; new `/intake?token=` page, same-origin so site CSP can't block it; a post's URL is its id. Playbook in `chrome-listener.md`.
- 2026-09-27 · Claude Code · [architect] [5090]: Windows kit in `leads/deploy/5090/` (start, Cloudflare tunnel, autostart at login). The machine is Windows with cloudflared and Ollama already present. GitHub Actions now sweeps only the inbox and SAM; social feeds run on the 5090.
- 2026-09-27 · Claude Code · [architect]: borrowed the Mid-Atlantic Lead Board as a second destination (`sinks.webhooks`, bearer + Idempotency-Key). Its exact payload shape is unconfirmed: sends lead-board field names by default. Check on the first real post.
- 2026-09-27 · Claude Code · [architect]: morning digest (`python -m leads digest --send`, 7:48am ET in Actions). It reads the board, so it sees every sweeper. Tests 299 passed.
- 2026-09-27 · Claude web · [cross]: Vinny: on Reddit, we rely on him as a redditor, posting and getting feedback. Reddit scraping parked (`social-*` disabled). New `reddit-replies` email listener routes Reddit reply/message notifications to the board. Chrome never posts on Reddit; it can summarize replies on his posts or draft posts for him.
- 2026-09-27 · Claude Code · [architect]: Vinny: "if I join a thread it should interrogate that thread." Built `reddit_threads` listener: follows his comments and posts, and reads each whole thread (post plus all comments), producing thread facts (asks, $ amounts, replies to you) plus a lead per new comment. Re-checks for 7 days. Runs on the 5090 (needs REDDIT_USERNAME).
- 2026-09-27 · Claude Code · [architect] [cross]: Vinny: "we recruit through groups we own." `owned-groups` watches every thread in OWNED_SUBREDDITS with recruiting rules, tagged `recruit`. Board only, no link to the physical guild.
- 2026-09-27 · Claude web · [cross]: Vinny: we cross-pollinate by posting thoughtful threads in human voice (incl. technical groups about our ideas). Vinny writes and posts; Claude can draft for him to edit. Tests 302 passed.
- 2026-09-27 · Chrome · setup: The Human Network inbox (HMTCHS Gmail) is set as the lead inbox. Leads label + Reddit filter + Reddit email notifications done in Vinny's browser. App Password and `.env` are Vinny's step (never through an AI). The address stays out of this public repo.
