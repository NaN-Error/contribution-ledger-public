#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/optional-stop.sh"
base() { docker compose --project-directory "$ROOT" -f compose.yaml "$@"; }
sync_compose() { docker compose --project-directory "$ROOT" -f compose.yaml -f compose.github.yaml -f compose.sync.yaml "$@"; }
[[ -f .env ]] || { echo 'Run normal setup first; read docs/github_sync.md.' >&2; exit 1; }
case "${1:-status}" in
 init)
    count="$(grep -c '^CL_JOBS_BROKER_PASSWORD=' .env || true)"
    [[ "$count" -le 1 ]] || { echo 'Duplicate broker configuration; resolve locally.' >&2; exit 1; }
    if [[ "$count" == 0 ]]; then
      secret="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
      (umask 077; printf '\nCL_JOBS_BROKER_PASSWORD=%s\n' "$secret" >> .env)
      unset secret
    else
      tr -d '\r' < .env | grep -Eq '^CL_JOBS_BROKER_PASSWORD=[a-f0-9]{64}$' || { echo 'Invalid existing broker value; not overwritten.' >&2; exit 1; }
    fi
    mkdir -p .local/github-secrets; chmod 700 .local/github-secrets
    if [[ ! -e .local/github-secrets/github-webhook-secret ]]; then
      (umask 077; set -o noclobber; od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > .local/github-secrets/github-webhook-secret)
    fi
    chmod 600 .env
    echo 'Missing local secrets generated; existing values preserved. No value was sent to GitHub or printed.'
    echo 'Privately configure your App webhook secret, then run bash scripts/github.sh provision before enabling intake.'
    ;;
 start)
    tr -d '\r' < .env | grep -Eq '^CL_JOBS_BROKER_PASSWORD=[a-f0-9]{64}$' || { echo 'Run bash scripts/sync.sh init first.' >&2; exit 1; }
    stop_optional_integrations; base stop api
    sync_compose build api web github-celery github-scheduler webhook-gateway
    base up -d --wait --wait-timeout 120 db
    base run --rm --no-deps migrate
    sync_compose up -d --wait --wait-timeout 120 api web github-broker github-celery github-scheduler webhook-gateway
    echo 'Optional local services started. Enable a repository schedule in GitHub > Synchronization. No public endpoint was created.'
    ;;
 pause) stop_optional_integrations; echo 'Optional integrations stopped; retained schedules/data are unchanged.' ;;
 status) sync_compose ps ;;
 logs) sync_compose logs --tail 100 --follow github-scheduler github-celery ;;
 manual) stop_optional_integrations; base up -d --wait --wait-timeout 120 api web ;;
 *) echo 'Usage: bash scripts/sync.sh {init|start|pause|status|logs|manual}' >&2; exit 1 ;;
esac
