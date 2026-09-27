# Build Card: Silver, gold & gem hunt (eBay, estate sales, surplus auctions)

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
2. **Silver and gold (the value test: "if it were broken into elements, could we get our money back?"):** the title parser finds weight (g, dwt, ozt, oz), purity (sterling/.925, .999, 10–24k, 90% coin) and known coins. It computes melt from the spot price and flags listings whose price plus shipping is under melt by a set margin.
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
- 2026-09-27 · Claude web · [cross]: Vinny: "the bid system is repurposed for estate sales" and "email lead is flexible enough to not need changing." So: `estate-mail` is the unchanged email listener with an Estate label, precious rules and melt reading. New `gsa-auctions` listener (official GSA Auctions API, api.data.gov key). Chrome estate playbook sets up alerts on EstateSales.NET/.org, HiBid, AuctionZip and LiveAuctioneers. SAM.gov listener stays in the code, idle.
- 2026-09-27 · Claude Code · fix: mixed-metal text ("14k jewelry, sterling flatware 1200 grams") read the weight as 14k gold, overvaluing it roughly 30×. Each weight now pairs with the nearest purity mention; `.999` takes its metal from the nearest "gold"/"silver". Regression tests added. Live GSA dry run: 678 lots in VA/MD/NC/DC, 0 precious, all dropped. Tests 325 passed.
- 2026-09-27 · Claude Code: Vinny has a Sandbox keyset too. App IDs containing `-SBX-` now route to api.sandbox.ebay.com automatically (test listings only; proves the wiring while Production waits on the exemption). Keys stay out of the repo.
- 2026-09-27 · Claude Code: Sandbox keyset tested live. OAuth token OK; Browse search returned 200 test listings across two queries; the appraiser read each one (sandbox items are test data, so nothing routed). Wiring proven end to end. Keys were used in memory only and are not stored anywhere.
- 2026-09-27 · Claude web · correction: the "Exempted from Marketplace Account Deletion" line Vinny saw is the toggle's label, not a granted exemption. Exemption not yet applied; the keyset is still disabled.
- 2026-09-27 · Vinny: applied for the eBay Marketplace Account Deletion exemption (not persisting eBay data). Waiting for the Production keyset to show enabled.
- 2026-09-27 · Claude Code · [architect]: Vinny: "on eBay we're looking for mispriced jewelry… and silver." New `jewelry` hunt (metal + gem reading + mispricing clues: fine metal filed under Fashion/Costume, seller-unsure wording, designer/period names tagged verify, platinum). `ebay-jewelry` listener with 14 gold/silver jewelry queries every 20 min is now the main hunt. Tests 328 passed.
- 2026-09-27 · Claude Code · [architect] [cross]: Vinny's value test: "if it were broken into elements, could we get our money back?" Scoring switched from raw melt to break-down value (melt × refiner payout + stones at his per-carat recovery) vs all-in cost (price + ship + tax + fee). Defaults are conservative placeholders (gold 80%, silver 70%, 6% tax). Exception, per Vinny ("except for designer"): designer/period pieces can't be vetoed by the break-down test; they're tagged for sold-comps checks. Tests updated to the stricter test, e.g. a 400 g sterling lot at $265 no longer passes.
- 2026-09-27 · Claude Code · [cross]: Vinny: "not so strict a rule, just the gram weight melted down plus gem value." Defaults now: full-spot melt + gem value (per-carat, his numbers) vs price + shipping, money back at break-even. Refiner payout, tax, fee and cushion remain as optional knobs, off by default.
- 2026-09-27 · Claude Code · [cross]: Vinny: "gram weights can be guesstimated." When karat or sterling is stated without a weight, a low-end typical weight per item type (ring, class ring, chain, bracelet, spoon…) × lot quantity is used. Estimates score lower, are labeled "confirm weight", and never get a penalty. Stated weights win.
- 2026-09-27 · Claude Code · [cross]: Vinny: gem value by carat, quality/color and clarity, authentic vs synthetic. Built `gem_value`: carats × his base $/ct × size × clarity (diamond grades or colored-stone words) × color (D–M or named colors) × treatment × origin (natural ×1, lab ×0.03, unstated ×0.6) × cert. Simulants are worth 0. Gem and jewelry hunts penalize lab (−60) and heavy treatment (−25). Weight guesstimates: low-end typical grams per item type. Fixed: glass-filled rubies were misread as glass; plurals (spoons, bangles). Tests 332 passed.
- 2026-09-27 · Claude web · [cross]: Vinny: "eBay is your domain now." Claude runs the eBay hunting and appraising end to end (queries, appraisers, tuning). Bidding and buying stay Vinny's gate. eBay listener now routes vehicle/equipment/electronics hunts through the appraiser framework; new `ebay-refurb` listener hunts bulk computer lots (his old refurb trade).
- 2026-09-27 · Claude Code: Vinny: add searches for Richmond estate sales. `estate-news` (Google News RSS: Richmond/Henrico/Chesterfield/Hampton Roads estate sales and auctions, deciphered). Live: news is thin for estate sales (first run's only hits were an unrelated auction abroad, now excluded), so the main feed stays the estate-sale sites' email alerts into HMTCHS (`estate-mail`, now deciphered too).
