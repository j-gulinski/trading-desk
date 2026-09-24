#!/usr/bin/env bash
# Full grid: S1–S4 × c = 1, 10, 50, 200 × four variants, then S5, repeated RUNS times.
# Variants alternate at every point. Smoke test: DURATION=3 WARMUP=1 RUNS=1 PAUSE=1 RESULTS=smoke
# One scenario again: SCENARIOS=s4
# Stage-2 check, today's server vs 256 threads vs async: RUNS=1 RESULTS=results/threads-check \
#   VARIANTS="bottle-wsgiref bottle-threads-256 fastapi-async" \
#   STREAM_VARIANTS="bottle-wsgiref bottle-threads-256 fastapi-async"
set -euo pipefail
cd "$(dirname "$0")"
export COMPOSE_FILE=infra/compose.yml

DURATION=${DURATION:-30}
WARMUP=${WARMUP:-10}
RUNS=${RUNS:-3}
PAUSE=${PAUSE:-5}
RESULTS=${RESULTS:-results}
SCENARIOS=${SCENARIOS:-"s1 s2 s3 s4 s5"}
VARIANTS=${VARIANTS:-"bottle-sync bottle-threads fastapi-async fastapi-sync"}
STREAM_VARIANTS=${STREAM_VARIANTS:-"bottle-threads fastapi-async"}

in_loadgen() { docker compose exec -T loadgen "$@"; }

wanted() { [[ " $SCENARIOS " == *" $1 "* ]]; }

load() {  # seconds, concurrency, url, extra oha arguments
  in_loadgen oha --no-tui --output-format json -z "$1s" -c "$2" -t 10s "${@:4}" "$3"
}

wait_for() {
  until in_loadgen python -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1])" "$1" 2> /dev/null; do
    sleep 1
  done
}

measure() {  # name, variant, concurrency, path, extra oha arguments
  local name=$1 variant=$2 c=$3 url="http://$2:8000$4" pid
  load "$WARMUP" "$c" "$url" -w "${@:5}" > /dev/null
  pid=$(docker inspect -f '{{.State.Pid}}' "$(docker compose ps -q "$variant")")
  docker compose exec -d loadgen python tools/monitor.py "$pid" "$RESULTS/$name.usage.csv" "$DURATION"
  load "$DURATION" "$c" "$url" "${@:5}" > "$RESULTS/$name.json"
  echo "$name"
}

docker compose up -d --build
mkdir -p "$RESULTS"
wait_for http://stub:9000/delay/1
for variant in $VARIANTS; do wait_for "http://$variant:8000/health"; done

if wanted s2; then
  load "$DURATION" 200 http://stub:9000/delay/50 > "$RESULTS/stub_c200.json"
fi

for run in $(seq "$RUNS"); do
  for scenario in s1 s2 s3 s4; do
    wanted "$scenario" || continue
    for c in 1 10 50 200; do
      for variant in $VARIANTS; do
        case $scenario in
          s1) set -- /health ;;
          s2) set -- /io ;;
          s3) set -- /cpu ;;
          s4) set -- /db -m POST
              docker compose exec -T postgres psql -U bench -qc "TRUNCATE audit_logs, books, trades, valuations" ;;
        esac
        measure "${variant}_${scenario}_c${c}_run${run}" "$variant" "$c" "$@"
        sleep "$PAUSE"
      done
    done
  done
  for streams in 10 50 200; do
    wanted s5 || break
    for variant in $STREAM_VARIANTS; do
      name="${variant}_s5_streams${streams}_run${run}"
      docker compose exec -d loadgen python tools/hold_streams.py "http://$variant:8000/stream" "$streams" "$RESULTS/$name.streams"
      sleep 3
      measure "$name" "$variant" 10 /health
      in_loadgen pkill -f hold_streams.py
      sleep "$PAUSE"
    done
  done
done

in_loadgen python analyze.py "$RESULTS"
