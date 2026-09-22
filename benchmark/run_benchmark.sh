#!/usr/bin/env bash
# Full measurement grid: scenarios × concurrency × variants × runs.
# Variants alternate at every point, so drift on the machine hits all three equally.
# Needs: DATABASE_URL (a migrated trading-desk database), hey, and benchmark/requirements.txt.
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)

DURATION=${DURATION:-30}   # seconds measured per point
WARMUP=${WARMUP:-10}       # seconds sent first and discarded
RUNS=${RUNS:-3}
PAUSE=${PAUSE:-2}
CORES=$(nproc 2> /dev/null || sysctl -n hw.ncpu)
# One worker process per variant: every service runs as one process today. Above 1, uvicorn
# --workers leaves TCP_NODELAY off and adds ~40 ms to every keep-alive request. See README.
N=${N:-1}
: "${DATABASE_URL:?set DATABASE_URL to a migrated trading-desk database}"

export PYTHONPATH="$ROOT/libs/desk-runtime/src:$ROOT/libs/desk-domain/src:$ROOT/libs/desk-pricing/src:$ROOT/services/books-service/src:$PWD"

# Servers run on the first N cores; the load generator, stub and monitor on the rest.
if command -v taskset > /dev/null; then
  SERVER="taskset -c 0-$((N - 1))"
  CLIENT="taskset -c $N-$((CORES - 1))"
else
  SERVER=""; CLIENT=""   # macOS has no core pinning, see README
fi

port_of() { case $1 in A) echo 9001 ;; A-threads) echo 9002 ;; B) echo 9003 ;; esac; }
path_of() { case $1 in s1) echo /health ;; s2) echo /io ;; s3) echo /cpu ;; s4) echo /books ;; esac; }
wait_for() { until curl -sf "$1" > /dev/null; do sleep 1; done; }

mkdir -p results logs
trap 'kill $(jobs -p) 2> /dev/null || true' EXIT

# One stub process, not the PDF's two, for the same TCP_NODELAY reason.
$CLIENT uvicorn downstream_stub.app:app --port 9000 --no-access-log > logs/stub.log 2>&1 &
$SERVER gunicorn -w "$N" -b 127.0.0.1:9001 sample_wsgi.app:app > logs/A.log 2>&1 &
PID_A=$!
$SERVER gunicorn -w "$N" --threads 40 -b 127.0.0.1:9002 sample_wsgi.app:app > logs/A-threads.log 2>&1 &
PID_A_threads=$!
$SERVER uvicorn sample_asgi.app:app --port 9003 --workers "$N" --no-access-log > logs/B.log 2>&1 &
PID_B=$!

wait_for http://127.0.0.1:9000/delay/1
for variant in A A-threads B; do wait_for "http://127.0.0.1:$(port_of $variant)/health"; done
python seed_books.py

# The stub must not be the bottleneck: check it alone at the highest concurrency.
$CLIENT hey -z "${DURATION}s" -c 200 -t 10 http://127.0.0.1:9000/delay/50 > results/stub_c200.txt

for run in $(seq 1 "$RUNS"); do
  for scenario in s1 s2 s3 s4; do
    for c in 1 10 50 200; do
      for variant in A A-threads B; do
        pid_var="PID_${variant/-/_}"
        url="http://127.0.0.1:$(port_of $variant)$(path_of $scenario)"
        out="results/${variant}_${scenario}_c${c}_run${run}"
        $CLIENT hey -z "${WARMUP}s" -c "$c" -t 10 "$url" > /dev/null
        $CLIENT python monitor.py "${!pid_var}" "$out.usage.csv" "$DURATION" &
        $CLIENT hey -z "${DURATION}s" -c "$c" -t 10 "$url" > "$out.txt"
        wait $!
        echo "$out"
        sleep "$PAUSE"
      done
    done
  done
done
