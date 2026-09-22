# Lead bulletin board

## Architecture

Listeners (SMS, email, forms, boards, and webhooks) send JSON to `doPost`. The
Apps Script stores normalized leads in the `LiveQueue` sheet. The static board
reads active leads from `doGet` as JSON or JSONP and sends triage actions back
through `doPost`.

## LiveQueue columns

| Column | Type | Description | Example |
| --- | --- | --- | --- |
| `lead_id` | string | Unique lead identifier | `LEAD-2026-0922-01` |
| `timestamp` | ISO string | Intake time | `2026-09-22T16:20:00.000Z` |
| `listener_channel` | enum | Intake category | `Trade Distress` |
| `source_medium` | enum | Transport or discovery medium | `SMS` |
| `source_contact` | string | Original contact | `Mike · field lead (Baker Bros HVAC)` |
| `origin` | string | Pickup location | `Carrier Enterprise · Midlothian` |
| `destination` | string | Delivery location | `Scott's Addition · Richmond` |
| `cargo_summary` | string | Cargo description | `2 TXV valves + recovery tank` |
| `payout_offered` | number | Offered payout | `75.00` |
| `mileage_est` | number | Estimated miles | `18.0` |
| `rate_per_mile` | number | Payout divided by miles | `4.17` |
| `urgency_level` | enum | Normalized urgency | `CRITICAL` |
| `window_deadline` | string | Pickup or delivery deadline | `Pickup by 12:40 PM` |
| `triage_status` | enum | Current board state | `NEW` |
| `updated_at` | ISO string | Last state update | `2026-09-22T16:20:00.000Z` |

## Trusted-operator prototype deployment

1. Create a Google Sheet and copy its ID from the URL.
2. Paste the ID into `SPREADSHEET_ID` in `apps-script/Code.gs`.
3. Paste `Code.gs` and `appsscript.json` into a project at
   [script.google.com](https://script.google.com), or use `clasp`.
4. Select `setup` in the Apps Script function menu and click **Run**. Approve
   the requested Sheet access. This creates the sheet headers and, when needed,
   generates a 64-character API key in the `LEAD_BOARD_API_KEY` Script Property.
   Copy the key from the execution log and do not commit it.
5. Deploy → **Web app**, execute as **User deploying**, and grant access only
   to the trusted Google accounts or Workspace domain that operate the board.
   Do not select anonymous access.
6. Copy the deployed `/exec` URL. Each operator must sign into an allowed
   Google account before using it.

On first authorized request, the script creates `LiveQueue` and its headers. A
`PREPARE_BID` action creates `BidCalculator` with its own headers.

## Connecting the board

Host `board/index.html` on a trusted HTTPS site. Open it, click **Configure**,
and enter the deployed `/exec` URL and API key. The values are stored in that
browser's local storage, so use only managed, non-shared operator devices.

The board reads a `?api=` query parameter or a `LEAD_BOARD_API_URL` constant as
an optional URL default. JSONP callbacks are restricted to JavaScript identifier
paths. The API key is still required for reads and writes.

Incoming listener values are matched case-insensitively to the supported
enums; unknown channel, medium, or urgency values fall back to
`General Intake`, `Webhook`, or `MEDIUM`. Triage actions are:

- `ACCEPT` → `ACCEPTED` and dispatch notification stub
- `PREPARE_BID` → `BID_PREPARED` and a row in `BidCalculator`
- `WATCH` → `WATCH`
- `DISMISS` → `DISMISSED` and dispatch notification stub
- `RESET` → `NEW`

Every triage action updates `updated_at`. The dispatch notification is
intentionally a logging stub until an email or other channel is configured.

## Tests and curl example

Run the local smoke test before deployment:

```bash
node lead-board/apps-script/test_local.js
```

After deployment, run the end-to-end smoke test from any directory. This test
requires `node` and an authenticated Google session that can reach the web app:

```bash
export LEAD_BOARD_API_URL="https://script.google.com/macros/s/DEPLOYMENT_ID/exec"
export LEAD_BOARD_API_KEY="your-generated-key"
./lead-board/samples/curl.sh
```

The script adds the key at runtime, creates a lead, captures its generated ID,
accepts that same lead, and reads the active queue. The intake and triage
requests use `Content-Type: text/plain` to avoid a browser preflight.

For a prototype, the same key authorizes intake, reads, and triage. Do not give
it to untrusted listener integrations. Split intake into a separately scoped
credential or service before exposing intake outside the operator group.
