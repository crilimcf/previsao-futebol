#!/usr/bin/env bash
# scripts/trigger_render_deploy.sh
# Trigger a Render deploy via API v1 and poll until terminal state.
# Usage: RENDER_API_KEY=xxx RENDER_SERVICE_ID=srv-abc ./scripts/trigger_render_deploy.sh
set -euo pipefail
RENDER_API_KEY=${RENDER_API_KEY:-}
RENDER_SERVICE_ID=${RENDER_SERVICE_ID:-}
if [ -z "$RENDER_API_KEY" ] || [ -z "$RENDER_SERVICE_ID" ]; then
  echo "Provide RENDER_API_KEY and RENDER_SERVICE_ID environment variables." >&2
  exit 2
fi

echo "Triggering deploy for service $RENDER_SERVICE_ID"
resp_code=$(curl -sS -o /tmp/render_deploy_resp.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache": true}' \
  "https://api.render.com/v1/services/${RENDER_SERVICE_ID}/deploys")

if [ "$resp_code" -ge 400 ]; then
  echo "Deploy request failed (HTTP $resp_code)" >&2
  cat /tmp/render_deploy_resp.json || true
  exit 1
fi

deploy_id=$(jq -r '.id' /tmp/render_deploy_resp.json 2>/dev/null || echo "")
if [ -z "$deploy_id" ] || [ "$deploy_id" = "null" ]; then
  echo "No deploy id found in response:" >&2
  cat /tmp/render_deploy_resp.json
  exit 1
fi

echo "Deploy created: $deploy_id"

# Poll deploy status until finished
while true; do
  sleep 5
  curl -sS -H "Authorization: Bearer $RENDER_API_KEY" "https://api.render.com/v1/services/${RENDER_SERVICE_ID}/deploys?limit=5" -o /tmp/render_deploy_list.json
  jq -r '.[] | "id:\(.id) state:\(.state) createdAt:\(.createdAt) startedAt:\(.startedAt) finishedAt:\(.finishedAt)"' /tmp/render_deploy_list.json || true
  state=$(jq -r --arg id "$deploy_id" '.[] | select(.id == $id) | .state' /tmp/render_deploy_list.json 2>/dev/null || echo "")
  if [ -z "$state" ]; then
    echo "Could not find deploy in list; sleeping..."
    continue
  fi
  echo "Deploy $deploy_id state: $state"
  if [[ "$state" == "live" || "$state" == "failed" || "$state" == "cancelled" ]]; then
    echo "Final state: $state"
    jq -r --arg id "$deploy_id" '.[] | select(.id == $id)' /tmp/render_deploy_list.json || true
    exit 0
  fi
done
