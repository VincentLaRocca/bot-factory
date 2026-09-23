#!/usr/bin/env bash
set -euo pipefail

API_URL="${LEAD_BOARD_API_URL:-https://script.google.com/macros/s/DEPLOYMENT_ID/exec}"

curl -sL -X POST \
  --data-urlencode "From=+18045550123" \
  --data-urlencode "Body=PICKUP Carrier Enterprise Midlothian TO Scott's Addition Richmond: 2 TXV valves + recovery tank \$75 18mi by 12:40pm URGENT" \
  "$API_URL"
