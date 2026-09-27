# Hunts: silver, gold and gems (eBay, estate sales, surplus auctions)

Same engine as the lead system (`leads/`), different prey. The eBay listener
searches through the official Browse API with an application token. It reads
every title for what's actually in the item and flags the listings worth a
human look. **It never bids, buys, offers, or messages a seller.**

## Setup

0. **Enable the keyset.** eBay ships new Production keysets *disabled* until you
   either subscribe to Marketplace Account Deletion notifications or claim the
   exemption. The hunter **doesn't store eBay user data**: seller usernames are
   read for the feedback check and dropped, and only the listing and the
   seller's feedback numbers are kept. So the exemption is the honest,
   fast path. developer.ebay.com → Alerts & Notifications (or the keyset
   page) → Marketplace Account Deletion → toggle **"Not persisting eBay
   data"** / apply for exemption.
   If you ever start storing seller identities, use the endpoint instead: the
   inbound listener serves `/ebay/account-deletion` (set
   `EBAY_VERIFICATION_TOKEN` and `EBAY_DELETION_ENDPOINT` to the exact
   public URL, e.g. `https://<tunnel-host>/ebay/account-deletion`). It
   answers eBay's challenge and purges a deleted user's records.
1. developer.ebay.com → **Application Keys** → *Production* keyset: copy the **App ID** (client id) and **Cert ID** (client secret).
2. Put them in `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` (the 5090 `.env` and/or GitHub secrets).
3. Set `SILVER_SPOT_USD` and `GOLD_SPOT_USD` (USD per troy oz). v0 uses the numbers you give it; update them when the market moves.
4. Set your **price-per-carat limits** in `leads/hunts.example.json` → `max_price_per_carat`. The example values are placeholders, not advice.
5. Try it: `python -m leads --config leads/hunts.example.json sweep --dry-run --json`

## The value test: could we get our money back?

Vinny's rule, kept simple: **if it were broken into its elements, would we get
our money back?**

- **Break-down value** = the gram weight melted down at spot (weight x purity x spot) **plus the gems' value** (`stone_per_ct`, per stone type, which you set).
- **Cost** = price + shipping.
- Break-down ≥ cost: **money back**, +40 plus the % it clears by. Short by under 15%: no points, noted. Worse: −30.

**No weight in the title? It gets guesstimated.** Karat or sterling with no weight
gets a low-end typical weight for the item: ring 2.5 g, men's ring 6, class ring 7,
band 3, chain 4 (link chains 10), bracelet 5, bangle 7, cuff 20, earrings 1.5,
pendant 2, brooch 5, spoon 25, fork 35, and so on, times the quantity in the lot.
Estimates score lower (max +40), are labeled "confirm weight in photos/description",
and never get a penalty. Stated weights always win.

Optional knobs in each listener's `recovery` block, all off by default: `payout` (below 1.0 if you want what a refiner actually pays), `tax_rate`, `fee`, and `cushion` (demand a margin above break-even).

**Gem value = carats × your base $/ct × size × clarity × color × treatment × origin × certificate.**
You set one base price per stone type (`stone_per_ct`: a clean, natural, untreated
~1 ct stone of ordinary color). The title then adjusts it:

- **Size:** per-carat price rises with size (under 0.5 ct ×0.6 … over 3 ct ×2.6)
- **Clarity:** diamond grades FL…I3, or "eye clean", "included", "opaque" for colored stones
- **Color:** diamond letters D…M, or "pigeon blood", "royal blue", "cornflower", "vivid", "pale"…
- **Treatment:** unheated/no heat ×1.5 … heated ×1 … dyed/diffused ×0.2 … glass-filled ×0.05
- **Natural vs synthetic:** stated natural ×1; lab/created/synthetic/moissanite ×0.03; not stated ×0.6
- **Certificate** (GIA, AGS, IGI…): ×1.15

Simulants (CZ, glass, crystal, rhinestone) are worth nothing. In gem and jewelry
hunts, lab stones lose 60 points and heavy treatments lose 25, because the hunt is for
natural stones. All multipliers can be overridden in `recovery.gem_factors`.

**Exception: designer pieces.** A Tiffany or Yurman piece can be worth more
whole than broken down. For designer and period pieces, the break-down test
can't veto: negative points are dropped, and the listing is tagged
"value beyond its elements, check sold comps" for a human look.

## Mispriced jewelry (gold and silver): the main hunt

`ebay-jewelry` runs every 20 minutes across rings, chains, class rings, sterling
lots, Navajo silver, estate lots, "unmarked" and "grandma's" lots, and
designer sterling. On top of the melt math and the gem reading, it adds:

| Clue | Points |
| --- | --- |
| Fine metal ("14k", "sterling", "925", "platinum") filed under **Fashion/Costume** jewelry | **+25** |
| Seller unsure ("unmarked", "untested", "not sure if real", "tests as gold", "grandma's", "junk drawer", "unsearched") | **+20**, tagged *steal or fake, check photos* |
| Designer or period name (Tiffany, Cartier, Yurman, Georg Jensen, Spratling, Navajo, Art Deco…) | **+10**, tagged *verify, fakes are common* |
| Platinum mentioned | **+10** |

Plated, filled, "tone", "style", "inspired", "dupe", replica, lab and simulant
listings are vetoed outright.

## How a listing is read

| Hunt | What it reads from the title | Points |
| --- | --- | --- |
| Silver / gold | known coins (Morgan, Peace, ASE, Walkers, 1964 & 40% Kennedys, war nickels, Eagles, Krugerrands, Sovereigns, $20/$10/$5/$2.50 gold); junk silver by face value; weight (g, dwt, ozt, bullion oz) × purity (sterling/.925, .999, coin silver, 800, 10–24k) × quantity ("lot of 10") | price + shipping under melt by the margin (default 10%): **+40 plus the % under**. Over melt: **−30** |
| Gems | stone, carats, certificate (GIA, AGS, IGI…) | certified **+15**; $/ct under your limit **+30** |
| Both | misspellings (sterlng, sliver, saphire, emrald…) | **+20** misspelled; **+20** auction ending within 24h with no bids; **−10** thin seller feedback |

Vetoed: plated, filled, "tone", vermeil, nickel/German/Tibetan silver, weighted,
clad, replica; lab-created, simulated, synthetic, CZ, moissanite, glass. If the
title doesn't state a weight and a purity, there's **no melt reading**. It
says so instead of guessing.

A title is a claim, not a test. Weighted sterling, stones in gold rings, and
seller mistakes all move the real number. Check photos and the description
before you buy.

## Estate sales and auctions: the bid system, repurposed

| Listener | Source | Needs |
| --- | --- | --- |
| `estate-mail` | Estate-sale and auction **email alerts** (EstateSales.NET, EstateSales.org, HiBid, AuctionZip, LiveAuctioneers, local houses) in the Human Network inbox, label **Estate** | same IMAP login. The email listener is unchanged; it just gets a folder and precious-metal rules. Stated weights in an alert get a melt reading |
| `gsa-auctions` | Federal surplus through the official **GSA Auctions API** (VA/MD/NC/DC by default) | `DATA_GOV_API_KEY` from api.data.gov (`DEMO_KEY` works for a trial) |
| Chrome | Sets up the alerts, then looks closer at promising sales on request | `pipeline/silver-gem-hunt/chrome-estate.md` |

A live trial run against GSA returned 678 lots in the four states, none of them precious that day. So the gate works.

## Where deals go

`var/hunts.jsonl` (ledger) and `HUNT_SLACK_WEBHOOK_URL` (HIGH and CRITICAL
only), never the courier lead board. `python -m leads --config
leads/hunts.example.json digest --send` gives the top deals of the last 24h.
In GitHub Actions: `.github/workflows/hunt-sweep.yml` runs every 30 minutes,
7am–7pm ET, with a 7:44am digest.

## Appraisers: the heart of the opportunity finder

`leads/appraisers/` holds one appraiser per domain, auto-picked from the listing text:

| Appraiser | Floor (money back if broken down) | Estimate (whole) |
| --- | --- | --- |
| jewelry | gram weight melted at spot + gem value | designer/period flagged for comps |
| vehicle | curb weight × scrap yield × $/ton + catalytic converter | price-sheet comp × condition (runs … parts only) × mileage |
| equipment | typical weight × scrap yield × $/ton | comp × condition × hours |
| electronics | per-unit parts/e-scrap × count | comp per unit × count × condition ("no hard drives", untested…) |

Scoring is the same everywhere: money back on the floor scores high; upside on the
estimate scores by how sure the appraisal is; a working machine is never marked down
for being worth more than its scrap. Your numbers: `SCRAP_PER_TON`,
`CAT_CONVERTER_VALUE`, and a price sheet CSV (`VALUE_COMPS_CSV`, same columns as
`leads/appraisers/comps.example.csv`; every example value there is a PLACEHOLDER).
