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

Vinny's rule: **if it were broken into its elements, would we get our money
back?** Every metal listing is judged that way, not by raw melt:

- **Break-down value** = melt (ozt x spot) x what a refiner or scrap buyer actually pays (`payout`, default gold 80%, silver 70%), plus stones only at *your* per-carat recovery value (`stone_per_ct`, default none).
- **All-in cost** = (price + shipping) x (1 + sales tax, default 6%) + any flat refining/shipping fee.
- Break-down beats all-in by the cushion (default 10%): **+40 plus the %**, "money back". Beats it by less: **+15**, thin cushion. Short by under 15%: no points, noted. Worse: **−30**.

The payout numbers are placeholders. Set them from a real refiner quote in the
`recovery` block of `hunts.example.json` (or `GOLD_PAYOUT` / `SILVER_PAYOUT`).

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
