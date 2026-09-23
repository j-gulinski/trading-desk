#!/usr/bin/env bash
# Full measurement grid: scenarios × concurrency × variants × runs.
# Variants alternate at every point, so drift on the machine hits all of them equally.
# Needs: DATABASE_URL (a migrated trading-desk database), hey, and benchmark/requirements.txt.
#
#   ./run_benchmark.sh                                                Stage 1: A, A-threads, B
#   VARIANTS="before after B-std" RESULTS=results-4b ./run_benchmark.sh   Stage 4B, see README
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)

VARIANTS=${VARIANTS:-"A A-threads B"}
RESULTS=${RESULTS:-results}
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

port_of() {
  case $1 in
    A) echo 9001 ;; A-threads) echo 9002 ;; B) echo 9003 ;;
    before) echo 9004 ;; after) echo 9005 ;; B-std) echo 9006 ;;
  esac
}
path_of() { case $1 in s1) echo /health ;; s2) echo /io ;; s3) echo /cpu ;; s4) echo /books ;; esac; }
wait_for() { until curl -sf "$1" > /dev/null; do sleep 1; done; }

start_variant() {
  local port cmd
  port=$(port_of "$1")
  case $1 in
    A) cmd="gunicorn -w $N -b 127.0.0.1:$port sample_wsgi.app:app" ;;
    A-threads) cmd="gunicorn -w $N --threads 40 -b 127.0.0.1:$port sample_wsgi.app:app" ;;
    # B is the plain install measured in Stage 1: pure-Python event loop and HTTP parser.
    B) cmd="uvicorn sample_asgi.app:app --port $port --workers $N --no-access-log --loop asyncio --http h11" ;;
    B-std) cmd="uvicorn sample_asgi.app:app --port $port --workers $N --no-access-log --loop uvloop --http httptools" ;;
    before) cmd="python -m sample_wsgi.serve_wsgiref $port" ;;
    after) cmd="python -m sample_wsgi.serve_runtime $port" ;;
  esac
  $SERVER $cmd > "logs/$1.log" 2>&1 &
  eval "PID_${1//-/_}=$!"
}

mkdir -p "$RESULTS" logs
trap 'kill $(jobs -p) 2> /dev/null || true' EXIT

# One stub process, not the PDF's two, for the same TCP_NODELAY reason.
$CLIENT uvicorn downstream_stub.app:app --port 9000 --no-access-log > logs/stub.log 2>&1 &
for variant in $VARIANTS; do start_variant "$variant"; done

wait_for http://127.0.0.1:9000/delay/1
for variant in $VARIANTS; do wait_for "http://127.0.0.1:$(port_of "$variant")/health"; done
python seed_books.py

# The stub must not be the bottleneck: check it alone at the highest concurrency.
$CLIENT hey -z "${DURATION}s" -c 200 -t 10 http://127.0.0.1:9000/delay/50 > "$RESULTS/stub_c200.txt"

for run in $(seq 1 "$RUNS"); do
  for scenario in s1 s2 s3 s4; do
    for c in 1 10 50 200; do
      for variant in $VARIANTS; do
        pid_var="PID_${variant//-/_}"
        url="http://127.0.0.1:$(port_of "$variant")$(path_of $scenario)"
        out="$RESULTS/${variant}_${scenario}_c${c}_run${run}"
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
