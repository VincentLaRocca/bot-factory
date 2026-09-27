# Customer cards API: for a ChatGPT-built site

The division of labor, per Vinny: **each AI works where it's strongest.** Claude
builds the engine: listeners, appraisers, value tests, wish-list matching.
ChatGPT's site skills build the polished front end. The inbound listener already
serves a plain working page at `/customers?token=…`; this API lets a ChatGPT
site replace it without touching the engine.

Base URL: the 5090 tunnel, e.g. `https://leads.<domain>`. Auth: `Authorization: Bearer <LEADS_WEBHOOK_TOKEN>`.
CORS is open, so a site on another domain can call it.

## Read everything

`GET /api/customers` →

```json
{"status": "SUCCESS", "customers": [{
  "name": "Customer A", "phone": "804-555-0101", "email": "", "zip": "23220", "miles": 150,
  "discount": 0.30, "budget": 20000, "notes": "cash buyer, weekends",
  "wants": [{"name": "Mazdaspeed6", "q": "(mazdaspeed6, mazdaspeed 6)", "hunt": "vehicle",
             "max_price": 15000, "discount": 0.25, "notify": "all", "customer": "Customer A"}],
  "matches": [{"lead_id": "LD-EBAYWA-…", "title": "2007 Mazdaspeed6 GT, 90k, runs great", "url": "https://www.ebay.com/itm/…",
               "value": 6000, "score": 92, "urgency": "HIGH", "fits": true, "decision": "",
               "body": "… · Customer A: 40% under value, meets 25% threshold", "seen_at": "…"}]
}]}
```

## Change things

`POST /api/customers` with one of:

| action | body | does |
| --- | --- | --- |
| `save_card` | `{"card": {"name", "phone", "email", "zip", "miles", "discount": "30%", "budget": "$20,000", "notes"}}` | create/update a card |
| `delete_card` | `{"name"}` | remove a card and its wants |
| `add_want` | `{"customer", "want": {"name", "q", "hunt", "max_price", "discount", "zip", "miles", "notify": "all"\|"deals"}}` | start a standing eBay watch for them |
| `remove_want` | `{"customer", "name"}` | stop that watch |
| `decide` | `{"customer", "lead_id", "decision": "approved"\|"passed"}` | Vinny's call on a match |

Every reply is `{"status": "SUCCESS" | "ERROR", …}`.

## Brief to paste into ChatGPT

> Build a mobile-first "Customer Cards" web app for a small reseller (The Human Network). It talks to an existing JSON API (spec below). Screens: (1) customer list with search, showing each card's wants as chips and a badge with the count of matches waiting; (2) a customer card to view/edit contact, ZIP + miles, discount threshold (%), budget and notes, and add/remove wants (item, optional eBay search words, kind, max price, discount, "tell me: every match / deals only"); (3) a matches inbox across all customers: title links to the listing, price, "fits their terms" badge, the reason line, and big Approve / Pass buttons. Store the API base URL and token in settings (never hard-code them). Keep it plain and fast; no login beyond the token. [paste the API section above]
