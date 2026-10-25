# Signed intake and synchronization API

All ordinary routes require the current session, scoped access, exact browser origin and CSRF protection for mutations. Prefix `P=/api/v1/workspaces/{workspace_id}/projects/{project_id}/github`. UUIDs from another project return denial/not-found, not a data leak. Read access is administrator/reviewer only for raw imported data; project contributors see only explicitly shared evidence.

## Unauthenticated-to-browser, authenticated-to-GitHub ingress

`POST /api/v1/github/webhook` is the sole browser-auth exception. Operator flags must enable GitHub and webhook intake. Requires `Content-Type: application/json`, bounded uncompressed raw body (1 MiB), `X-Hub-Signature-256: sha256=<64 hex>`, UUID `X-GitHub-Delivery`, and a valid `X-GitHub-Event`. HMAC uses the exact received bytes and mounted signing secret. Duplicate security headers/JSON keys, malformed IDs, incorrect app IDs in full installation envelopes, nested-routing mismatches and conflicting reuse are rejected. Query/extra path routes are not proxied by the gateway.

202: receipt and routing intent committed, including idempotent duplicate acknowledgement or ignored unsupported event. 400/401/409: invalid signature/shape/conflicting routing as applicable. 404: not enabled. 413: too large. 503: secret/intake/storage capacity unavailable. Never retry blindly as if 202 meant completed work. A signed unknown-installation event is not a new connection. Bodies and tokens are not saved; hashes and safe numeric targets are.

Implemented event/action allowlists live in `app/integrations/github/webhook_protocol.py`. Content-event hints cover push, pull_request, pull_request_review, pull_request_review_comment, issues, issue_comment, check_run and check_suite. Installation and installation_repositories events cover explicit lifecycle changes; repository changed visibility/name/owner/deletion can fence sharing. Unknown future events are ignored, not executed. Ping is validated and durably acknowledged without work. Action validation is intentionally conservative. App lifecycle envelopes require their documented full installation/app identity; simple event-header relabeling of a signed content payload cannot become a global uninstall.

## Project routes

| Method and suffix | Behavior |
|---|---|
| GET `P/sync` | Settings, job/signal counts, component heartbeats and new/unavailable pinned-source warnings |
| PUT `P/sync/{repository_id}` | Administrator reviews configuration; expected_version=0 for first save |
| POST `P/sync/{repository_id}/request` | Request next eligible run; does not bypass active work or GitHub cooldown |
| GET `P/jobs?limit=25&offset=0` | Scoped import jobs and dispatch metadata |
| GET `P/deliveries?limit=25&offset=0` | Scoped receipt target outcomes and safe fingerprints |
| GET `P/observations?limit=25&offset=0` | Latest local root/child observations; preserved version ID when unavailable |

PUT body: `expected_version`, `enabled`, `interval_minutes`, `lookback_days`, `request_limit`, `entity_limit`, `reviewed:true`, `reason`. Request-next body: `expected_version`, `reviewed:true`, `reason`. A stale version is a conflict. Disabling cancels that schedule's unfinished import and pending signals, never finalized economic history. Existing import cancel/resume endpoints retain their phase-8 schema and reject resuming exhausted five-failure jobs. Cancelling a scheduled job pauses its configuration.

The due transition, import/outbox creation, selected-signal linkage and immutable sync-run record use one transaction. Multiple schedulers do not intentionally create overlapping imports for one repository; verify the included multi-connection tests under PostgreSQL. Message publication occurs outside that transaction using a short database-owned dispatch lease. Queue payloads contain three UUIDs only. At-least-once broker redelivery is safe only because the handler rechecks its scoped row and current lease/state/access; neither an event nor message is authority to award units.

## Retention, bounds and omissions

Default receipt capacity is 100,000; unknown signed deliveries count toward it. Intake fails closed when full; inspect database capacity and approved retention procedures. No destructive cleanup endpoint was added. Pending signals are bounded to 1,000 per repository; over-cap signals record an ignored reconciliation-needed state. Run quotas and existing source-byte quotas also apply. Large imports can be incomplete; a completed bounded run does not mean every changed comment, branch or PR in GitHub was captured. Configured lookback and tracked-root round robin cannot discover all unknown old objects. A 404 for a primary root after verified access becomes an unavailable observation without deleting history.

No new route clones repositories, executes code, transfers money, changes contribution policy, awards units, changes a pinned source or connects an AI provider. See `github_sync.md` for operational and credential boundaries.
