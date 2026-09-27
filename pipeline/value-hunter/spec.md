# Build Card: Value Hunter (idea stage)

| | |
| --- | --- |
| **Status** | idea, not greenlit |
| **Spec origin** | Vinny, 2026-09-27: "Is that enough to build a value hunter? We can use this for other things too: cars, heavy-duty equipment for businesses, etc." |
| **Gates** | Vinny greenlights scope; every bid or buy is his |

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
