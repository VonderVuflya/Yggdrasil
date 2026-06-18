#!/usr/bin/env bash
# Reproducible end-to-end check for Yggdrasil on its OWN memory engine.
#
# Starts ygg_memory_server.py (stdlib SQLite+FTS5, zero heavy deps) on a fresh
# DB, seeds the demo fixtures, runs every gate, prints a summary, and tears the
# server down. No external backend required.
#
# Usage:  scripts/run_gates.sh
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${YGG_MEMORY_PORT:-42069}"
export YGG_ENGINE_URL="http://127.0.0.1:${PORT}"
export YGG_ENGINE_TOKEN="${YGG_ENGINE_TOKEN:-yggdrasil-demo-token}"
DB="$(mktemp -t ygg-gates-XXXX.sqlite)"

lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null; sleep 0.3
echo "==> starting own engine on :${PORT} (db=${DB})"
python3 yggdrasil/ygg_memory_server.py --reset --db "$DB" --port "$PORT" --token "$YGG_ENGINE_TOKEN" &
SERVER_PID=$!
trap 'kill -9 "$SERVER_PID" 2>/dev/null; rm -f "$DB" "$DB"-wal "$DB"-shm' EXIT

# wait for health
for _ in $(seq 1 40); do
  if python3 -c "import urllib.request;urllib.request.urlopen('${YGG_ENGINE_URL}/health',timeout=2)" 2>/dev/null; then break; fi
  sleep 0.25
done

echo "==> seeding demo fixtures (test-a / test-b)"
YGG_NAMESPACE=yggdrasil-demo YGG_USER_ID=demo-user python3 yggdrasil/ygg_seed_demo.py >/dev/null || { echo "SEED FAILED"; exit 1; }

declare -a GATES=(
  "ygg_quality_gate.py"
  "ygg_dense_gate.py"
  "ygg_review_apply_gate.py"
  "ygg_governance_gate.py"
)

rc=0
for gate in "${GATES[@]}"; do
  echo ""
  echo "==> ${gate}"
  if python3 "yggdrasil/${gate}" >/tmp/ygg-gate.out 2>&1; then
    echo "    PASS"
  else
    echo "    FAIL"
    tail -20 /tmp/ygg-gate.out
    rc=1
  fi
done

echo ""
if [ "$rc" -eq 0 ]; then
  echo "==> ALL GATES PASS on Yggdrasil's own engine"
else
  echo "==> SOME GATES FAILED"
fi
exit "$rc"
