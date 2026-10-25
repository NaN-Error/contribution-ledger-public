# Phase 9 test and acceptance checklist

The user has deferred thorough acceptance testing. No step below is marked passed merely because its script exists. See `test_results.json` for actual executed counts and environment limits.

## Automated commands

From `apps/api`, after installing committed compatible dependencies:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

PowerShell: set `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'` first. Existing SQLite/fake-transport tests require no real GitHub credentials. New tests exercise exact signatures, bad routing shapes, duplicated receipt IDs/bodies, rollback before acknowledgement, scheduled coalescing, durable publication retries, lease fencing, shared cooldowns, cancellation/revocation during a fetch, authority expiry, observations, restricted routes, migration preservation and unchanged evidence pins. This is simulated external behavior, not a live GitHub run.

Native tests require the existing explicitly disposable `CL_TEST_DATABASE_URL`. Six additional PostgreSQL tests cover simultaneous receipt acceptance, scheduler races, publisher claims, revocation/scheduling interaction, immutable history guards and scoped observation references. Do not point these at a real workspace database.

Optional native transport contracts require `requirements-jobs.lock`. Set `CL_TEST_BROKER_URL=redis://127.0.0.1:6379/15` only for disposable loopback Redis database 15. The roundtrip test uses a unique temporary queue and exact scoped UUIDs. It is a message serialization/transport test, not proof of the whole worker deployment. With no optional transport/database, these tests explicitly skip.

From `apps/web`, run `npm ci`, `npm test`, `npm run build`. Node tests include a real temporary gateway HTTP server, but do not render React. `scripts/check_typescript_syntax.cjs` only transpiles syntax; it cannot replace a semantic React typecheck. CI definitions now include an optional Redis service and installed job dependencies; the CI workflow itself has not run here.

## Local authorized GitHub/Docker acceptance

Use a throwaway repository owned/administered by the consenting tester and synthetic content only. Record each actual outcome without putting private keys, payloads or source into a public log.

- Upgrade phase 8, preserve a known source/evidence pin and contribution total; migration should not alter any of them. Normal startup must stop the optional workers and still allow manual accounting with GitHub disabled.
- Start optional services after protected setup. Connect the authorized repository, enable a six-hour schedule, and inspect a first bounded run. Confirm queues contain only scoped IDs. Pause/restart with broker state discarded: database-owned eligible work should be dispatched again without duplicate source versions or credit.
- Configure only an authorized HTTPS webhook route through the narrow gateway. Send a valid GitHub test event, redeliver it, and compare one durable receipt/effect. A bad signature, modified body, wrong installation app ID, duplicate security header, oversized/compressed body or wrong route must not queue work. API response must precede import work and raw payload must not appear in stored receipts.
- Make a real PR/comment change and inspect a later source capture. Disable webhook delivery, make another change within the lookback, then allow scheduled reconciliation to recover it. An old created PR updated now must be considered. Bounds/omissions and scan coverage must remain visible. Changing an unknown old entity outside the lookback is not guaranteed to be discovered.
- Deliver two authentic historical events in reverse order. Both must trigger current API reads, not replay old payload contents into the source head. Old immutable versions remain inspectable. Existing attached evidence stays pinned; a warning prompts an explicit reviewed update.
- Kill a worker during a request, wait for the claim to expire, and restart. A superseded lease must not commit. Cancel another job while data is in flight; ensure its stale response does not commit. Existing completed captures remain retained.
- Remove the authorizer's GitHub admin role and separately suspend/uninstall/remove the repository from the App. Received revocation events must fence immediately in the local database. Missed events must fail the next current permission check. Already sent requests cannot be recalled. Restore GitHub authority and explicitly reauthorize/re-enable; grants alone must not reactivate imports.
- Force a rate delay and inspect `next_attempt_at`/repository cooldown. Repeated manual requests must not bypass it. Exhaust five failures: the job stops automatically and the schedule requires explicit attention. Review a new bounded request only after resolving the cause/cooldown.
- Open synchronization as an administrator, reviewer, contributor and unrelated-workspace user. Only authorized raw-import readers may see it. Inspect nested tabs, pagination, stale version conflicts, exact reviewed settings, missing/error/loading states and mobile/keyboard behavior.
- Inspect retired/missing primary objects: show unavailable now while retaining earlier source/evidence history. A deleted child comment may only be represented by a changed parent capture or omission, not a guaranteed explicit tombstone.

## Browser source checks

`tests/e2e/accounts_smoke.py` now includes `github_sync_smoke.exercise_sync_shell` after the earlier manual flows. It inspects the disabled integration, empty synchronization pages and raw-data access denial without contacting GitHub. It requires the documented fresh disposable browser-test deployment and does not substitute for the real enabled/live flow above.

## Still open

Clean package/image installation, full React build/rendering, PowerShell paths/ACLs, native database races/privileges, actual Celery/Redis process recovery, live GitHub permission/event accuracy, HTTPS operation, security/load assessment, backup restore and human acceptance. Earlier phase gates remain open. This source is not a production compensation service.
