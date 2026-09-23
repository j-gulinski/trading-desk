#!/usr/bin/env bash
# One blocking call inside async def stalls every request in the process (PDF appendix A,
# last note; risk 1 in 5.4). FastAPI serves /health to one client while ten others load:
#   none       nothing                                    — the baseline
#   cpu        /cpu, declared def, runs in the thread pool
#   cpu-async  the same work declared async def, so it runs on the event loop
# Output: results/demo_<load>_run<n>.txt, hey summaries of /health.
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)
RESULTS=${RESULTS:-results}
CORES=$(nproc 2> /dev/null || sysctl -n hw.ncpu)
export PYTHONPATH="$ROOT/libs/desk-runtime/src:$ROOT/libs/desk-domain/src:$ROOT/libs/desk-pricing/src:$ROOT/services/books-service/src:$PWD"
: "${DATABASE_URL:?set DATABASE_URL to a migrated trading-desk database}"
if command -v taskset > /dev/null; then
  SERVER="taskset -c 0"; CLIENT="taskset -c 1-$((CORES - 1))"
else
  SERVER=""; CLIENT=""
fi

mkdir -p "$RESULTS" logs
trap 'kill $(jobs -p) 2> /dev/null || true' EXIT
$SERVER uvicorn sample_asgi.app:app --port 9003 --no-access-log > logs/demo.log 2>&1 &
until curl -sf http://127.0.0.1:9003/health > /dev/null; do sleep 1; done

for run in 1 2 3; do
  for load in none cpu cpu-async; do
    if [ "$load" != none ]; then
      $CLIENT hey -z 40s -c 10 -t 10 "http://127.0.0.1:9003/$load" > /dev/null &
      load_pid=$!
      sleep 5
    fi
    $CLIENT hey -z 30s -c 1 -t 10 http://127.0.0.1:9003/health > "$RESULTS/demo_${load}_run$run.txt"
    [ "$load" = none ] || wait "$load_pid"
    echo "$RESULTS/demo_${load}_run$run"
  done
done
