#!/usr/bin/env bash
set -euo pipefail

: "${LEAD_BOARD_API_URL:?Set LEAD_BOARD_API_URL to the deployed /exec URL}"
: "${LEAD_BOARD_API_KEY:?Set LEAD_BOARD_API_KEY to the configured script property}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="$LEAD_BOARD_API_URL"

INTAKE_PAYLOAD="$(node -e '
  const fs = require("fs");
  const payload = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  payload.api_key = process.env.LEAD_BOARD_API_KEY;
  process.stdout.write(JSON.stringify(payload));
' "$SCRIPT_DIR/intake_trade_distress.json")"
INTAKE_RESPONSE="$(curl -fsS "$API_URL" -H "Content-Type: text/plain" --data-binary "$INTAKE_PAYLOAD")"
echo "$INTAKE_RESPONSE"

LEAD_ID="$(node -e '
  const response = JSON.parse(process.argv[1]);
  if (response.status !== "SUCCESS" || !response.lead_id) process.exit(1);
  process.stdout.write(response.lead_id);
' "$INTAKE_RESPONSE")"
TRIAGE_PAYLOAD="$(node -e '
  process.stdout.write(JSON.stringify({action: "triage", lead_id: process.argv[1],
    triage_action: "ACCEPT", api_key: process.env.LEAD_BOARD_API_KEY}));
' "$LEAD_ID")"
curl -fsS "$API_URL" -H "Content-Type: text/plain" --data-binary "$TRIAGE_PAYLOAD"
echo

curl -fsS --get "$API_URL" \
  --data-urlencode "status=active" \
  --data-urlencode "api_key=$LEAD_BOARD_API_KEY"
echo
