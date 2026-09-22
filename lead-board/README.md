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

## Deployment

1. Create a Google Sheet and copy its ID from the URL.
2. Paste the ID into `SPREADSHEET_ID` in `apps-script/Code.gs`.
3. Paste `Code.gs` and `appsscript.json` into a project at
   [script.google.com](https://script.google.com), or use `clasp`.
4. Deploy → **Web app**, execute as **User deploying**, and grant access to
   **Anyone**.
5. Copy the deployed `/exec` URL.

On first request, the script creates `LiveQueue` and its headers. A
`PREPARE_BID` action creates `BidCalculator` with its own headers.

## Connecting the board

The board reads a `?api=` query parameter, or a `LEAD_BOARD_API_URL` constant
in `board/index.html`. Set either to the deployed `/exec` URL. JSONP is
available by adding `callback=someFunction` to a GET request.

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

## Curl examples

Run from `lead-board/samples/` after setting `LEAD_BOARD_API_URL`:

```bash
export LEAD_BOARD_API_URL="https://script.google.com/macros/s/DEPLOYMENT_ID/exec"
./curl.sh
```

The intake and triage requests use `Content-Type: text/plain` to avoid a
browser preflight. The final request is `GET ?status=active`, which includes
`NEW`, `WATCH`, and `BID_PREPARED` leads. Individual requests can also be run
with `curl -H "Content-Type: text/plain" --data-binary @file.json "$API_URL"`.
