# Playbook: Claude in Chrome on estate sales

The bid system, repurposed: find estate sales and auctions with silver, gold,
jewelry and coins before the crowd does. Most of it arrives by **email
alerts** into the Human Network inbox, where the `estate-mail` listener reads
them. Chrome's job is to set those alerts up, and then to look closer at the
sales the alerts surface.

## 1. One-time: set up the alerts (with Vinny, in his browser)

For each site, create a free account with the Human Network Gmail and turn on
alerts for sales within ~50 miles of Richmond and of Norfolk, with keywords
**sterling, silver, gold, jewelry, coins, estate jewelry, bullion**:

- EstateSales.NET (saved searches / email alerts)
- EstateSales.org
- HiBid (saved searches, auctioneer follows)
- AuctionZip
- LiveAuctioneers (saved searches)
- Local auction houses Vinny names (newsletter sign-ups)

In Gmail, add a filter: mail from those senders → label **Estate**.
Don't enter payment details, register to bid, or accept terms beyond a basic
account without Vinny.

## 2. When a sale looks promising (on request)

Open the sale, read the description and photos, and write it up for the
intake page (`/intake?token=…`):

```json
{
  "id": "https://www.estatesales.net/VA/Richmond/.../123",
  "title": "Henrico estate sale: sterling flatware (Gorham), 14k rings, coin albums",
  "url": "https://www.estatesales.net/VA/Richmond/.../123",
  "location": "Henrico, VA",
  "deadline": "Fri–Sat 9am–3pm; numbers at 8am",
  "listener_channel": "Local Community",
  "body": "What's visible in photos: pattern, hallmarks, approximate pieces. Online bidding or in person?",
  "via": "chrome",
  "tags": ["estate", "silver", "gold"]
}
```

## Rules

- Read and report only. No bidding, buying, offers or messages to sellers or auctioneers.
- Human pace: open sales one at a time. Stop on captchas or warnings and log it.
- Photos are claims too. Note hallmarks you can see ("STERLING", "14K", "925"), but don't guess weights.
