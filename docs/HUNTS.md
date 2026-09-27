# Hunts: silver, gold and gems on eBay

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

## Where deals go

`var/hunts.jsonl` (ledger) and `HUNT_SLACK_WEBHOOK_URL` (HIGH and CRITICAL
only), never the courier lead board. `python -m leads --config
leads/hunts.example.json digest --send` gives the top deals of the last 24h.
In GitHub Actions: `.github/workflows/hunt-sweep.yml` runs every 30 minutes,
7am–7pm ET, with a 7:44am digest.
