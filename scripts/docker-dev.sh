#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
minimum_free_gb=${DOCKER_MIN_FREE_GB:-10}
build_cache_limit=${DOCKER_BUILD_CACHE_LIMIT:-8GB}

available_kb() {
  df -Pk "$repo_root" | awk 'NR == 2 { print $4 }'
}

cleanup_rebuild_debris() {
  echo "Keeping Docker build cache at or below $build_cache_limit..."
  docker builder prune --force --max-used-space "$build_cache_limit"
  docker image prune --force --filter "until=168h"
  docker container prune --force --filter "until=168h"
}

require_free_space() {
  required_kb=$((minimum_free_gb * 1024 * 1024))
  free_kb=$(available_kb)

  if [ "$free_kb" -lt "$required_kb" ]; then
    free_gb=$((free_kb / 1024 / 1024))
    echo "Refusing a Docker rebuild: ${free_gb} GB free, ${minimum_free_gb} GB required." >&2
    echo "Free host storage or run '$0 clean', then retry." >&2
    exit 1
  fi
}

require_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "Docker is not ready. Start Docker Desktop and retry." >&2
    exit 1
  fi
}

action=${1:-up}
require_docker

case "$action" in
  up)
    cleanup_rebuild_debris
    require_free_space
    cd "$repo_root"
    docker compose up --build -d
    cleanup_rebuild_debris
    ;;
  clean)
    cleanup_rebuild_debris
    ;;
  status)
    df -h "$repo_root"
    docker system df
    ;;
  *)
    echo "Usage: $0 [up|clean|status]" >&2
    exit 2
    ;;
esac
