#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/optional-stop.sh
action="${1:-status}"
files=(-f compose.yaml)
if [[ "${2:-}" == '--with-github-sync' ]]; then files+=(-f compose.github.yaml -f compose.sync.yaml); fi
files+=(-f compose.ai.yaml)
base(){ docker compose --project-directory "$PWD" -f compose.yaml "$@"; }
ai(){ docker compose --project-directory "$PWD" "${files[@]}" "$@"; }
case "$action" in
  init)
    [[ -f .env ]] || { echo 'Run normal local setup first.' >&2; exit 1; }
    python3 - <<'ENV'
import os,re,secrets
from pathlib import Path
p=Path('.env');lines=[s for s in p.read_text().splitlines() if s.startswith('CL_AI_DB_PASSWORD=')]
if len(lines)>1 or (lines and not re.fullmatch(r'CL_AI_DB_PASSWORD=[a-f0-9]{64}',lines[0])):
    raise SystemExit('Existing AI worker password settings are invalid/duplicated; not overwritten.')
if not lines:
    with p.open('a') as f:f.write('\nCL_AI_DB_PASSWORD='+secrets.token_hex(32)+'\n')
ENV
    stop_optional_integrations
    base stop api
    ai build ai-init ai-provision
    base up -d --wait --wait-timeout 120 db
    base run --rm --no-deps migrate
    ai run --rm --no-deps ai-init
    ai run --rm --no-deps ai-provision
    echo 'AI storage and restricted worker role prepared; no provider contacted. Next: bash scripts/ai.sh start.'
    ;;
  start)
    [[ "$(grep -c '^CL_AI_DB_PASSWORD=' .env || true)" == 1 ]] && grep -qE '^CL_AI_DB_PASSWORD=[a-f0-9]{64}$' .env || { echo 'Run AI init first.' >&2;exit 1; }
    stop_optional_integrations
    base stop api
    ai build api web ai-worker
    base up -d --wait --wait-timeout 120 db
    base run --rm --no-deps migrate
    services=(api web ai-worker)
    if [[ "${2:-}" == '--with-github-sync' ]]; then
      ai build github-celery github-scheduler webhook-gateway
      services+=(github-broker github-celery github-scheduler webhook-gateway)
    fi
    ai up -d --wait --wait-timeout 120 "${services[@]}"
    echo 'Explicit AI worker started. Defaults allow only synthetic no-cost calls; live use needs operator and payer approval.'
    ;;
  pause) stop_optional_integrations; echo 'Optional workers stopped. Already-sent calls can still be billed.' ;;
  status) ai ps ;;
  logs) ai logs --tail 100 --follow ai-worker ;;
  manual) stop_optional_integrations; base up -d --wait --wait-timeout 120 api web ;;
  *) echo 'Usage: bash scripts/ai.sh {init|start|pause|status|logs|manual} [--with-github-sync]' >&2; exit 2 ;;
esac
