# Build Card: Silver, gold & gem hunt (eBay)

| | |
| --- | --- |
| **Status** | review |
| **Spec origin** | Vinny, 2026-09-27 (pivot from Reddit; he has an eBay developer account) |
| **Judge** | Claude Code |
| **Build** | Claude Code, 2026-09-27, `[architect]` (semi), branch `leads/full-lead-system` |
| **Sessions and reality lens** | Claude desktop: are the flagged deals real deals, and would Vinny actually buy them? |
| **Gates** | Vinny: every bid or buy is his, by hand. Merge after the reality check. |

## Problem

Precious-metal and gem listings on eBay are sometimes priced below what's in
them: sterling sold by the piece instead of by weight, junk silver at face,
gold jewelry listed without karat math, stones hidden by a misspelled title,
and auctions ending with no bids. Finding those by hand means reading thousands
of titles a day. Build a listener that reads them for Vinny and surfaces only
the ones worth a look.

## Done means

1. `python -m leads --config leads/hunts.example.json sweep` searches eBay through the official Browse API (App ID + Cert ID from Vinny's developer account, OAuth client credentials).
2. **Silver and gold:** the title parser finds weight (g, dwt, ozt, oz), purity (sterling/.925, .999, 10–24k, 90% coin) and known coins. It computes melt from the spot price and flags listings whose price plus shipping is under melt by a set margin.
3. **Gems:** certified stones (GIA/AGS/IGI), price per carat under the limits Vinny sets per stone, misspelled titles, and auctions ending within 24h with no bids get flagged.
4. **Fakes and lookalikes are vetoed:** plated, filled, "tone", nickel/German/Tibetan silver, lab-created, simulated, CZ, moissanite, glass, replica.
5. Deals go to their own Slack channel and ledger, never the courier lead board, plus a daily deal digest.
6. Nothing ever bids, buys, offers or messages a seller.
7. Tests run offline against recorded eBay responses.

## Constraints and non-goals

- Stdlib only. Reuses the lead engine (`leads/`): Lead model, rules, dedupe store, sinks, digest.
- Browse API only (search and read). No Trading/Offer APIs, no bidding, no buying, no seller contact.
- Spot prices come from config/env (`SILVER_SPOT_USD`, `GOLD_SPOT_USD`) for v0. A live spot feed is v1.
- Gem price-per-carat limits are Vinny's call. The example values are placeholders, not advice.

## Borrow list

- `leads/` engine: pipeline, rules, store, Slack sink, digest
- 5090 kit: same `.env`, same start script (add `--config leads/hunts.example.json` as a second loop, or a scheduled sweep)

## Log

- 2026-09-27 · Claude web · [cross]: Vinny pivoted from Reddit to eBay (developer account) for a new use case: silver and gem hunting. Gold added a minute later ("gold too").
- 2026-09-27 · Claude Code · [architect]: Built `leads/valuation.py` (coins, junk face, g/dwt/ozt × purity × qty; gem stone/ct/cert; misspellings; fakes vetoed) and `leads/listeners/ebay.py` (Browse API, client-credentials token, evidence points via `Lead.bonus`). `leads/hunts.example.json`, `hunt-sweep.yml` (every 30 min, 7:44am digest), docs/HUNTS.md. Tests: 318 passed.
- 2026-09-27 · Claude Code · open: spot prices are manual for v0. A live spot feed and learning from Vinny's actual buys are v1.
- 2026-09-27 · Claude Code · [cross]: eBay's Production keyset (`prelucky`) arrives disabled until account-deletion compliance is met. Chose the no-persistence path: the hunter now drops seller usernames (it keeps listing + feedback numbers only), so the exemption is truthful. Also built `/ebay/account-deletion` (challenge + purge) on the inbound listener as the fallback. Tests 320 passed.
