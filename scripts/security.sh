#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/optional-stop.sh"
case "${1:-status}" in
 init)
  stop_optional_integrations
  docker compose -f compose.yaml stop api web
  docker compose -f compose.yaml build api migrate security-init
  docker compose -f compose.yaml up -d --wait db
  docker compose -f compose.yaml run --rm --no-deps migrate
  docker compose -f compose.yaml run --rm --no-deps security-init
  echo 'Protected authentication key initialized or verified. Recreate API, then enroll in Account and sessions.';;
 status) docker compose -f compose.yaml ps;;
 *) echo 'Use init or status.' >&2; exit 2;;
esac
