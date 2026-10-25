#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/optional-stop.sh"
base() { docker compose --project-directory "$ROOT" -f compose.yaml "$@"; }
github() { docker compose --project-directory "$ROOT" -f compose.yaml -f compose.github.yaml "$@"; }
[[ -f .env ]] || { echo 'Run normal startup first, then follow docs/github_setup.md.' >&2; exit 1; }
case "${1:-status}" in
 provision)
    for name in github-private-key.pem github-client-secret; do
      [[ -f ".local/github-secrets/$name" ]] || { echo "Missing protected secret mount file: $name" >&2; exit 1; }
    done
    read -r -p 'Type PROVISION GITHUB SECRETS to replace credentials and stop API/worker: ' confirm
    [[ "$confirm" == 'PROVISION GITHUB SECRETS' ]] || { echo 'Cancelled.'; exit 0; }
    stop_optional_integrations
    github stop api github-worker
    base build api
    github run --rm --no-deps github-provision python -m app.security.secrets.provision --confirm "$confirm"
    echo 'Provisioned. Run this script with start to resume; protect host files and secret volume backups.'
    ;;
 start)
    stop_optional_integrations
    github stop api
    github build api web github-worker
    github up -d --wait --wait-timeout 120 db
    base run --rm --no-deps migrate
    github up -d --wait --wait-timeout 120 api web github-worker
    echo 'Use the configured 127.0.0.1 browser origin and open the project GitHub tab. No authorization or import is created automatically.'
    ;;
 pause) stop_optional_integrations ;;
 status) github ps ;;
 logs) github logs --tail 100 --follow github-worker ;;
 step) github run --rm --no-deps github-worker python -m app.workers.github --max-steps 1 ;;
 manual) stop_optional_integrations; base up -d --wait --wait-timeout 120 api web ;;
 *) echo 'Usage: bash scripts/github.sh {provision|start|pause|status|logs|step|manual}' >&2; exit 1 ;;
esac
