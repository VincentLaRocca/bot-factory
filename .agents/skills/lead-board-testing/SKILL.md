---
name: lead-board-runtime-testing
description: Run the standalone lead board in demo mode and distinguish UI coverage from deployed Google Sheets integration.
---

# Lead board runtime testing

## Setup
- From `<repo>/lead-board/board`, run `python3 -m http.server 8765`.
- Open `http://localhost:8765/index.html`. No frontend dependency installation is required.
- For the local backend harness, run `source ~/.nvm/nvm.sh && node lead-board/apps-script/test_local.js` from the repo root. The harness stubs Apps Script; it does not establish deployed Sheet connectivity.

## Demo state and configuration
- No configured API means six demo leads, initially four active.
- Use Configure → Use demo data to clear `localStorage.leadBoardApi` and remove URL query configuration.
- Page reload resets demo edits; the Refresh button preserves current in-memory demo edits.
- A nonempty `?api=` value persists to localStorage and remains effective on subsequent plain-URL loads.
- A nonexistent local API path can exercise JSONP script-load failure without external credentials.

## Meaningful runtime assertions
- Check card IDs as well as counts after triage. Removing one card may shift another actionable card into the same pointer position.
- Test native rapid double-clicks in a filtered view, then confirm only the intended ID changed.
- If action cooldown exists, verify controls become usable again after it, including when switching status tabs.
- Distinguish demo triage from live POST, BidCalculator append, dispatch, and in-flight request protection.

## Devin Secrets Needed
- None for demo or the local harness.
- Live integration requires an authorized deployed Apps Script `/exec` endpoint connected to a test spreadsheet; a demo pass does not replace that access.
