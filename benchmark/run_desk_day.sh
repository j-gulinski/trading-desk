#!/usr/bin/env bash
# Part 2, the desk core: K watching clients against each serving variant, RUNS times (smoke: KS=10 VARIANTS=gunicorn RUNS=1).
# Part 2b, many traders: RESULTS=results/desk_day_trading KS=50 TRADERS="5 20".
set -euo pipefail
cd "$(dirname "$0")"
export COMPOSE_FILE=infra/desk.compose.yml

KS=${KS:-"10 50 100 200"}
VARIANTS=${VARIANTS:-"wsgiref gunicorn fastapi"}
RUNS=${RUNS:-3}
TRADERS=${TRADERS:-"0"}
RESULTS=${RESULTS:-results/desk_day}
WARMUP=${WARMUP:-90}
SERVICES="market-data-service pricing-service trade-action-service blotter-service books-service monitoring-service"
MEASURED="$SERVICES postgres stub client"

caffeinate -dimsu -w $$ &
mkdir -p "$RESULTS"
host_sampler() {  # epoch and busy cores of the whole laptop, every 10 s
  while true; do
    echo "$(date +%s) $(top -l 2 -s 1 -n 0 | awk -v cores="$(sysctl -n hw.ncpu)" '/^CPU usage/ {idle = $7}
      END {sub("%", "", idle); printf "%.2f", (100 - idle) / 100 * cores}')" >> "$RESULTS/host_cpu.txt"
    sleep 9
  done
}
host_sampler &
sampler=$!
trap 'kill $sampler 2> /dev/null; docker compose stop > /dev/null 2>&1' EXIT

sql() { docker compose exec -T postgres psql -U desk -d postgres -qc "$1"; }

rotated() {  # the variants, starting at position run - 1
  local variants=($VARIANTS) i
  for ((i = 0; i < ${#variants[@]}; i++)); do
    echo "${variants[(i + $1 - 1) % ${#variants[@]}]}"
  done
}

wait_marker() {  # dir, load pid, marker; fails when the load exits without writing it
  until [[ -e $1/$3 ]]; do
    kill -0 "$2" 2> /dev/null || [[ -e $1/$3 ]] || return 1
    sleep 1
  done
}

cgroup_sample() {  # epoch, then "container usage_usec" per measured container
  python3 -c 'import time; print(time.time())'
  for name in $MEASURED; do
    echo "$name $(docker compose exec -T "$name" cat /sys/fs/cgroup/cpu.stat | awk '/^usage_usec/ {print $2}')"
  done
}

run_load() {  # dir, K, T; samples container CPU when the clients are stable and when the window is done
  docker compose exec -T client python -m desk_day.load --clients "$2" --traders "$3" --out "/bench/$1" \
    < /dev/null > "$1/load.log" 2>&1 &
  local load=$!
  if wait_marker "$1" "$load" stable; then
    cgroup_sample > "$1/cgroup.stable"
    if wait_marker "$1" "$load" done; then
      cgroup_sample > "$1/cgroup.done"
    fi
  fi
  wait "$load" || echo "$1: load exited with $?"
}

docker compose build
docker compose up -d --wait postgres stub client
docker compose exec -T client python -m desk_day.seed

for run in $(seq "$RUNS"); do
  for k in $KS; do
    for t in $TRADERS; do
      for variant in $(rotated "$run"); do
        dir="$RESULTS/${variant}_k${k}_run${run}"
        if ((t > 0)); then
          dir="$RESULTS/${variant}_k${k}_t${t}_run${run}"
        fi
        echo "== $dir"
        mkdir -p "$dir"
        rm -f "$dir"/{stable,unstable,done,summary.json,preview.json,cgroup.stable,cgroup.done}
        sql "DROP DATABASE IF EXISTS desk WITH (FORCE)"
        sql "CREATE DATABASE desk TEMPLATE desk_seed"
        VARIANT=$variant STREAM_THREADS=$((40 + k + 10)) docker compose up -d $SERVICES
        if docker compose exec -T client python -m desk_day.ready > "$dir/ready.log"; then
          sleep "$WARMUP"
          run_load "$dir" "$k" "$t"
        else
          echo "$dir: desk not ready, skipped"
        fi
        docker compose logs --no-color $SERVICES > "$dir/services.log"
        docker compose stop $SERVICES
      done
    done
  done
done
