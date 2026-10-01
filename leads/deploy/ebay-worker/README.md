# eBay account-deletion endpoint (Cloudflare Worker)

eBay keeps a Production keyset switched off until the app answers Marketplace
Account Deletion notices. This Worker is that endpoint: free tier, always on,
a permanent `https://ebay-deletion.<account>.workers.dev/ebay/account-deletion`.
No domain, no tunnel, no need for the 5090 to be awake.

```powershell
powershell -ExecutionPolicy Bypass -File leads\deploy\ebay-worker\deploy-worker.ps1
```

First run: one browser sign-in to Cloudflare. Then it deploys, sets the secrets,
self-tests eBay's challenge and prints the Endpoint and Verification token to
paste into developer.ebay.com → Alerts & Notifications.

- `GET ?challenge_code=` → `{"challengeResponse": SHA-256(code + token + endpoint)}`
- `POST` (a deletion notice) → 204. The hunter stores no eBay user data (seller
  usernames are dropped when listings are read), so there is nothing to purge.
- Offline test: `node test.mjs`

The 5090 quick-tunnel route (`leads/deploy/5090/ebay-endpoint.ps1`) still works
for a same-day test, but its address changes on every restart. This one doesn't.
