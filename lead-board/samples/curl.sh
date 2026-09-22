#!/usr/bin/env bash
set -euo pipefail

API_URL="${LEAD_BOARD_API_URL:-https://script.google.com/macros/s/DEPLOYMENT_ID/exec}"

curl -sS "$API_URL" \
  -H "Content-Type: text/plain" \
  --data-binary @intake_trade_distress.json

curl -sS "$API_URL" \
  -H "Content-Type: text/plain" \
  --data-binary @triage_accept.json

curl -sS "$API_URL?status=active"
