#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/optional-stop.sh"
compose() { docker compose --project-directory "$ROOT" -f "$ROOT/compose.yaml" "$@"; }
case "${1:-help}" in
  doctor)
    command -v docker >/dev/null || { echo 'Docker is missing. Install Docker and the Compose v2 plugin.' >&2; exit 1; }
    [[ "$(docker info --format '{{.OSType}}')" == 'linux' ]] || { echo 'Linux containers are required.' >&2; exit 1; }
    docker compose version
    echo 'First build needs internet access. No GitHub or AI credentials are required.'
    ;;
  init)
    if [[ -e .env ]]; then echo 'Existing .env preserved.'; exit 0; fi
    password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    (umask 077; set -o noclobber; sed "s/REPLACE_WITH_GENERATED_PASSWORD/$password/" .env.example > .env)
    echo 'Created private local configuration. Password is not displayed.'
    ;;
  start)
    bash "$0" doctor
    bash "$0" init
    stop_optional_integrations
    compose stop api
    compose build api web
    compose up -d --wait --wait-timeout 120 db
    compose run --rm --no-deps migrate
    compose up -d --wait --wait-timeout 120 api web
    web_port="$(sed -n 's/^CL_WEB_PORT=//p' .env | tr -d '\r')"
    echo "Application: http://127.0.0.1:${web_port:-5173}"
    ;;
  setup-owner) compose exec -T api python -m app.cli setup-token ;;
  account)
    [[ $# -eq 4 ]] || { echo 'Usage: bash scripts/manage.sh account {recover|disable|enable} EMAIL "REASON"' >&2; exit 1; }
    [[ "$2" == recover || "$2" == disable || "$2" == enable ]] || { echo 'Unknown account action.' >&2; exit 1; }
    read -r -p "Verify the intended account owner, then type $3 to confirm $2: " answer
    [[ "$answer" == "$3" ]] || { echo 'Cancelled.'; exit 0; }
    compose exec -T api python -m app.cli "$2-account" --email "$3" --reason "$4"
    ;;
  seed-team)
    read -r -p 'Type CREATE SYNTHETIC TEAM to create optional accounts and display passwords once: ' answer
    [[ "$answer" == 'CREATE SYNTHETIC TEAM' ]] || { echo 'Cancelled.'; exit 0; }
    compose exec -T api python -m app.cli seed-team --confirm "$answer"
    ;;
  prune-auth) compose exec -T api python -m app.cli prune-auth ;;
  stop) stop_optional_integrations; compose down --remove-orphans ;;
  logs) compose logs --tail 150 --follow "${2:-api}" ;;
  seed) compose exec -T api python -m app.cli seed ;;
  reset-development)
    read -r -p 'Type DELETE DEVELOPMENT RECORDS to delete the synthetic marker: ' answer
    [[ "$answer" == 'DELETE DEVELOPMENT RECORDS' ]] || { echo 'Cancelled.'; exit 0; }
    compose exec -T api python -m app.cli reset-development --confirm "$answer"
    ;;
  *) echo 'Usage: bash scripts/manage.sh {doctor|init|start|setup-owner|account ACTION EMAIL REASON|seed-team|prune-auth|stop|logs [api|db|web]|seed|reset-development}' ;;
esac
