#!/usr/bin/env bash
# Source from another script. Does not mutate data or delete any volume.
stop_optional_integrations() {
  local ids old
  ids="$(docker ps -aq --filter label=com.docker.compose.project=contribution-ledger --filter label=com.contribution-ledger.optional)"
  if [[ -n "$ids" ]]; then
    while IFS= read -r id; do [[ "$id" =~ ^[a-f0-9]+$ ]] || return 1; docker stop "$id"; done <<< "$ids"
  fi
  old="$(docker ps -aq --filter label=com.docker.compose.project=contribution-ledger --filter label=com.docker.compose.service=github-worker)"
  if [[ -n "$old" ]]; then
    while IFS= read -r id; do [[ "$id" =~ ^[a-f0-9]+$ ]] || return 1; docker stop "$id"; done <<< "$old"
  fi
}
