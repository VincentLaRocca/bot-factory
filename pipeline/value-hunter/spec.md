# Build Card: Value Hunter (idea stage)

| | |
| --- | --- |
| **Status** | building (v0): appraiser framework live on GSA surplus |
| **Spec origin** | Vinny, 2026-09-27: "Is that enough to build a value hunter? We can use this for other things too: cars, heavy-duty equipment for businesses, etc." |
| **Gates** | Vinny greenlights scope; every bid or buy is his |

## Our arena

Vinny: "asymmetrical opportunities created by constraints being removed by AI and me: that's our arena."
The constraint here: nobody can read and appraise every lot, listing and alert
by hand. The appraisers remove that constraint. Vinny supplies the judgment,
the price sheet, and the buy. bot-factory's Asymmetry Analyst (`agents/asymmetry/`)
is the natural next reader of what the appraisers find.

## The idea

The silver, gold and gem hunt is one instance of a general machine:

```
listing sources ──→ appraiser (what's it worth, and how sure are we) ──→ value test ──→ board
 (eBay, GSA,          metals & gems today; vehicles and equipment next      "money back?"
  estate alerts,…)
```

Everything except the **appraiser** is already built and domain-neutral:
listeners, the dedupe store, rule scoring with evidence points (`Lead.bonus`),
Slack, the digest, the 5090 kit, and Chrome playbooks.

## Vinny's value test, generalized

"If it were broken into its elements, could we get our money back?"

| Domain | Elements (the floor) | Above the floor |
| --- | --- | --- |
| Jewelry & bullion | metal melt + gem value | designer or period premium (checked against comps) |
| Cars & trucks | scrap weight (curb weight × $/ton) + key parts (catalytic converter, engine/transmission, wheels) | running value vs sold comps (NADA/KBB-style, auction results) |
| Heavy equipment | scrap weight + attachments/parts | hours, condition, auction comps (Ritchie Bros, IronPlanet, GSA results) |

## Sources already in reach

- **GSA Auctions API** (built, live): federal surplus includes vehicles, trucks, generators, forklifts and construction equipment, with lot descriptions and locations.
- **eBay Browse API** (built; waiting on keyset approval): eBay Motors and Business & Industrial categories.
- Estate and auction email alerts (built): many estate auctions include vehicles and tools.

## Open questions (for Vinny)

1. Which first: vehicles or equipment? And for resale, parts, or for use in the businesses?
2. Area: VA/Mid-Atlantic pickup only, or ship anything?
3. Where do comps come from? Sold listings (eBay sold data needs a different API), auction results, or your own price sheets to start.

## Log

- 2026-09-27 · Claude web · [cross]: Vinny: "the appraiser is the heart of the opportunity finder." Framing: this is an **opportunity finder**. Sources feed listings in, **appraisers** (one per domain) say what each is worth and how sure they are, and the value test decides. Borrow note: bot-factory already has `Opportunity` objects and the Asymmetry Analyst (`agents/asymmetry/`). An appraised listing could become an AIOP Opportunity with its evidence and provenance attached (v1).
- 2026-09-27 · Claude Code · [architect]: Built `leads/appraisers/` with one `Appraisal` shape and one `score()` for every domain (money back on the floor, upside on the estimate, weighted by confidence). Appraisers: **jewelry** (melt + gems, designer exception), **vehicle** (curb-weight scrap + converter floor; price-sheet comp × condition × mileage), **equipment** (typical-weight scrap floor; comp × condition × hours), **electronics** (Vinny's old refurb trade: per-unit parts floor × count; comp × count × condition, e.g. "no hard drives"). Price sheet is `leads/appraisers/comps.example.csv` (PLACEHOLDER values; set `VALUE_COMPS_CSV` to his own). GSA listener now auto-appraises every lot.
- 2026-09-27 · Claude Code · fix (found on live data): the GSA API answers in camelCase (`itemName`) with statuses "Active"/"Preview", not the documented `ItemName` and A/P, so every lot had been silently skipped. Fixed; regression test added. Rule keywords are now whole-word ("silver" no longer fires on "Silverado").
- 2026-09-27 · Claude Code · first live run (VA/MD/NC/DC, 29 lots, placeholder comps): 5 flagged. 2003 Dodge van at a $250 bid (under its ~$404 scrap + converter floor); generator in Richmond at $175; 6,000 lb forklift at $700 in Hillsborough NC; trailer in Richmond at $1,000; 2023 F-150 4x4 in Chatham VA at $1,100 (bidding still early). Office furniture and toner were correctly dropped. Tests 337 passed.
- 2026-09-27 · Claude Code · [cross]: Vinny: "reference Blue Book vs price on vehicles, and flag 40% discounts if all else looks normal in the ad." Built the book test: book = his price-sheet value (KBB/NADA lookups) × mileage; 40%+ under with no red flags (salvage, flood, title, won't run, engine/trans, frame/rust, as-is, TMU) and no scam tells → +45. Flawed-and-cheap is noted, not flagged. Scam tells −40 and upside suppressed. No free KBB API exists and scraping is off-limits, so book values are his numbers (a paid pricing API is a spending-gate option). New `ebay-vehicles` local-pickup search near Richmond/Norfolk. Tests pass.
- 2026-09-27 · Claude Code · [cross]: Vinny: "hold on to special listens set up on eBay, like Shelby or Mazdaspeed Mazda6" and "hold wish lists for numerous customers." Built `leads/watches.py` (standing watches in local var/watches.json, seeded with Mazdaspeed6 + Shelby), `python -m leads watch add/list/remove [--for CUSTOMER]`, and the `ebay-watches` listener (one search per watch, +50 special listen, tags watch:/for:, one lead per listing even when several customers want it, still appraised). Customer names never enter the repo. Tests 349 passed.
- 2026-09-27 · Claude Code: Vinny: "we keep a matrix." `python -m leads watch import` reads the customer matrix: wide (customers × wants, cell = max price or x) or long (one row per want, with search/hunt/zip). It reads a local CSV or a published Google Sheet link; with WISHLIST_MATRIX set, the watch listener re-reads it every sweep (sheet is master for the customers it lists). Tests 351 passed.
- 2026-09-27 · Claude Code · [cross]: Vinny: "log a customer, their wish, their discount threshold… on customer cards"; "I can approve there"; "look at each AI's strengths… leverage Chat's site skills." Built customer cards (`leads/customers.py`: contact, ZIP/miles, discount threshold, budget, notes, wants with per-want max/discount, approve/pass decisions), terms checked on every watch match (reference value: book for vehicles, melt+gems for jewelry, comp for others), `python -m leads customer …`, a working phone page at `/customers?token=`, and a JSON API documented in docs/CUSTOMER_API.md with a ready brief so ChatGPT's site skills can build the polished front end. Browser-checked: card renders, Approve records the decision. Tests 354 passed.
