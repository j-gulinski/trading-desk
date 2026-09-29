#!/usr/bin/env bash
# Part 2: three core flows × three levels × gunicorn / FastAPI, repeated RUNS times.
# Variants alternate at every point; the server container is recreated before each point.
# Smoke test: RUNS=1 WARMUP=3 DURATION=5 INGEST_DURATION=10 RESULTS=results/core-smoke
# One flow again: FLOWS=orders
set -euo pipefail
cd "$(dirname "$0")"
export COMPOSE_FILE=infra/compose.yml COMPOSE_PROFILES=core

RUNS=${RUNS:-3}
WARMUP=${WARMUP:-10}
DURATION=${DURATION:-30}
INGEST_DURATION=${INGEST_DURATION:-60}
PAUSE=${PAUSE:-5}
RESULTS=${RESULTS:-results/core}
FLOWS=${FLOWS:-"market_data orders valuation_stream"}
VARIANTS=${VARIANTS:-"gunicorn fastapi"}
PERIODS=${PERIODS:-"10 5 2"}
ORDER_LEVELS=${ORDER_LEVELS:-"10 50 200"}
SUBSCRIBER_LEVELS=${SUBSCRIBER_LEVELS:-"50 200 500"}
REQUEST_THREADS=40

in_loadgen() { docker compose exec -T loadgen "$@"; }

wanted() { [[ " $FLOWS " == *" $1 "* ]]; }

call() {  # method, url
  in_loadgen python -c 'import sys, urllib.request as u
print(u.urlopen(u.Request(sys.argv[2], method=sys.argv[1])).read().decode())' "$1" "$2"
}

wait_for() {
  until call GET "$1" > /dev/null 2>&1; do sleep 1; done
}

serve() {  # variant, gunicorn threads
  THREADS=$2 docker compose up -d --force-recreate --no-deps "core-$1" 2> /dev/null
  wait_for "http://core-$1:8000/health"
}

monitor() {  # variant, seconds
  local pid
  pid=$(docker inspect -f '{{.State.Pid}}' "$(docker compose ps -q "core-$1")")
  docker compose exec -d loadgen python tools/monitor.py "$pid" /tmp/usage.csv "$2"
}

record() {  # flow, variant, level, run; point result on stdin
  sleep 2
  in_loadgen python core_sample/record.py "$@" /tmp/usage.csv "$RESULTS"
  docker compose stop "core-$2" 2> /dev/null
  sleep "$PAUSE"
}

market_data() {  # variant, period, run; warm-up covers one full refresh cycle
  local url="http://core-$1:8000" before after
  serve "$1" "$REQUEST_THREADS"
  call POST "$url/ingest/$2" > /dev/null
  sleep $((WARMUP + $2))
  before=$(call GET "$url/ingest/stats")
  monitor "$1" "$INGEST_DURATION"
  sleep "$INGEST_DURATION"
  after=$(call GET "$url/ingest/stats")
  echo "{\"before\": $before, \"after\": $after}" | record market_data "$1" "$2" "$3"
}

orders() {  # variant, orders at once, run
  local url="http://core-$1:8000/orders/[0-9]{4}/[0-9]{2}" result
  serve "$1" "$REQUEST_THREADS"
  docker compose exec -T postgres psql -U bench -qc "TRUNCATE orders"
  in_loadgen oha --no-tui --output-format json -z "${WARMUP}s" -c "$2" -t 10s -w -m POST \
    --rand-regex-url "$url" > /dev/null
  monitor "$1" "$DURATION"
  result=$(in_loadgen oha --no-tui --output-format json -z "${DURATION}s" -c "$2" -t 10s -m POST \
    --rand-regex-url "$url")
  echo "$result" | record orders "$1" "$2" "$3"
}

valuation_stream() {  # variant, subscribers, run
  serve "$1" $(($2 + REQUEST_THREADS))
  in_loadgen rm -f /tmp/subscribers.json
  docker compose exec -d loadgen sh -c "python core_sample/subscribers.py \
    http://core-$1:8000/valuations/stream $2 $WARMUP $DURATION > /tmp/subscribers.json"
  sleep "$WARMUP"
  monitor "$1" "$DURATION"
  sleep "$DURATION"
  until in_loadgen test -s /tmp/subscribers.json; do sleep 1; done
  in_loadgen cat /tmp/subscribers.json | record valuation_stream "$1" "$2" "$3"
}

trap 'docker compose stop > /dev/null 2>&1' EXIT
docker compose up -d --build postgres loadgen stub-core
mkdir -p "$RESULTS"
for flow in $FLOWS; do rm -f "$RESULTS/$flow.jsonl"; done
docker compose exec -T postgres sh -c 'until pg_isready -qU bench; do sleep 1; done'
docker compose exec -T postgres psql -U bench -q -f - < core_sample/seed.sql
wait_for http://stub-core:9000/delay/1

if wanted market_data; then
  in_loadgen oha --no-tui --output-format json -z "${DURATION}s" -c 1250 -t 10s \
    http://stub-core:9000/delay/200 > "$RESULTS/stub.json"
fi

rm -f "$RESULTS/revalue.jsonl"
for run in $(seq "$RUNS"); do
  docker compose run --rm --no-deps core-gunicorn python core_sample/revalue.py >> "$RESULTS/revalue.jsonl"
  for flow in market_data orders valuation_stream; do
    wanted "$flow" || continue
    case $flow in
      market_data) levels=$PERIODS ;;
      orders) levels=$ORDER_LEVELS ;;
      valuation_stream) levels=$SUBSCRIBER_LEVELS ;;
    esac
    for level in $levels; do
      for variant in $VARIANTS; do
        "$flow" "$variant" "$level" "$run"
      done
    done
  done
done

in_loadgen python analyze_core.py "$RESULTS"
