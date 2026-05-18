#!/bin/bash
# Manual smoke test — run after starting uvicorn:
#   cd apps && source inference/.venv/bin/activate
#   cd api && uvicorn app:app --port 8000
#   bash apps/api/smoke.sh
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8000}"

echo "=== GET / ==="
curl -s "$BASE/" | jq .

echo "=== GET /health ==="
curl -s "$BASE/health" | jq .

echo "=== POST /chat/conversations ==="
CONV_JSON=$(curl -s -X POST "$BASE/chat/conversations" \
  -H "Content-Type: application/json" \
  -d '{"title":"smoke test"}')
echo "$CONV_JSON" | jq .
CONV_ID=$(echo "$CONV_JSON" | jq -r '.id')

echo "=== POST /chat/conversations/$CONV_ID/messages ==="
curl -s -X POST "$BASE/chat/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -d '{"text":"hey regis, quick smoke ping"}' | jq .

echo "=== GET /chat/conversations/$CONV_ID/messages ==="
curl -s "$BASE/chat/conversations/$CONV_ID/messages?limit=10" | jq .

echo "=== POST /recall ==="
DREAM_JSON=$(curl -s -X POST "$BASE/recall" \
  -H "Content-Type: application/json" \
  -d '{"text":"Smoke dream: floating in a quiet library where the books all hummed.","ack":false}')
echo "$DREAM_JSON" | jq .
DREAM_ID=$(echo "$DREAM_JSON" | jq -r '.dream_recall_id')

echo "=== GET /dreams?limit=5 ==="
curl -s "$BASE/dreams?limit=5" | jq .

echo "=== GET /dreams/$DREAM_ID ==="
curl -s "$BASE/dreams/$DREAM_ID" | jq .

echo "=== GET /sessions?limit=3 ==="
curl -s "$BASE/sessions?limit=3" | jq .

echo "=== GET /observations?limit=5 ==="
curl -s "$BASE/observations?limit=5" | jq .

echo "=== GET /persona (first 240 chars) ==="
curl -s "$BASE/persona" | jq '{ modified_at, content: (.content[:240] + "...") }'

echo "=== POST /compose ==="
curl -s -X POST "$BASE/compose" \
  -H "Content-Type: application/json" \
  -d '{"moment_kind":"morning_recall_prompt","explicit_context":"Smoke test."}' | jq .

echo "=== DONE ==="
