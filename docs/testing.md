> **Current phase 13:** Source `0.13.0-phase13`. Read `upgrade_phase13.md`, `finance.md` and `testing_phase13.md` for financial records; `project_status.md` and `test_results.json` are the current executed/deferred verification record. Existing owners do not repeat setup. Preserve database, evidence and configured credential/master volumes. All financial records remain synthetic-only. Older walkthroughs below are retained for earlier features, not claims about the current migration or verified readiness.

> **Phase-11 update:** For evidence assessments and current upgrade steps, read `ai_assessments.md` and `upgrade_phase11.md`. Old protocol-only profiles remain unchanged. New runs need separate disclosure/payer approvals, and existing AI worker grants must be refreshed. Current executed/deferred checks are in `test_results.json`.

# Earlier integration setup notes (retained)

Phase 8 originally introduced source `0.8.0-phase8`; it is not the current version. For the optional GitHub profile read `github_setup.md`, `github_imports.md`, `upgrade_phase8.md` and `testing_phase8.md`. The original manual commands below still apply with GitHub disabled. Stop an explicitly enabled GitHub worker separately using `scripts/github.ps1 -Action manual` before returning to base-only operation. Tests not listed as executed in the latest release remain pending.

# Testing the current source

## Results and boundaries

`docs/test_results.json` records the executed suites. `docs/releases/phase13.md` is the current release summary. `docs/releases/phase6.md` is historical. Phase-6 routes and checks are described in `testing_phase6.md`. Historical phase-1/2 results remain in their release notes; phase-2 structured results are in `docs/releases/phase2_test_results.json`. Tests against injected SQLite verify application behavior and migration structure, not PostgreSQL UUID/locking behavior. Node tests exercise actual utility/API-client/proxy code, not React rendering. All unexecuted integration, installation and user checks remain open.

## Backend

After a clean installation of `apps/api/requirements-dev.lock`, run from `apps/api`:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

PowerShell equivalent: `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q`.

Phase-3 tests cover strict schemas, exact unit and ratio arithmetic, policy fingerprints, acknowledgements, roster changes, current/pinned readiness, budget previews and gates, stale/repeated decisions, history immutability, scoped references, rollback, issued-unit guards and history pagination. A seeded randomized arithmetic test runs 300 scenarios; this is one counted test, not 300 independent tests.

The existing tests cover bootstrap rotation/expiry, generic login failures and throttling, cookies/CSRF/origin/body bounds, password and recovery flows, session revocation, account disablement, foreign-scope GET/write attempts, permission changes, last-owner checks, invitation replay/expiry/supersession/issuer changes, existing-account protection, optimistic versions, composite foreign keys, audit mutation rejection, and a synthetic two-workspace team. They do not claim that future unimplemented endpoints are protected by these tests.

Twenty-eight tests require a disposable native PostgreSQL database and `CL_TEST_DATABASE_URL` naming a database ending in `_test`. The three foundation tests operate only on their synthetic marker. The five account tests create/drop unique schemas inside that disposable database and test migration preservation, audit triggers, composite scope rejection and concurrent bootstrap/invitation/last-owner decisions. Five additional phase-3 tests cover a real 0002→0003 upgrade preserving accounts, native history/constraint checks, competing allocations, duplicate decisions, and concurrent revision/acknowledgement requests. Never point this variable at team data. A configured but unavailable PostgreSQL server is a failure, not an automatic SQLite fallback.

```text
CL_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/contribution_ledger_test
```

CI creates its own disposable service/database with an explicitly synthetic fixture password. This workflow is provided, not claimed to have run remotely. `scripts/test.ps1` builds test images; it does not by itself run the native PostgreSQL or browser suites.

## Frontend and proxy

From `apps/web`:

```bash
npm ci
npm test
npm run typecheck
npm run build
```

The Node suite compiles the actual status, roadmap, account, planning-arithmetic and API-client utilities. It tests token-fragment handling, response validation, concurrent session deduplication, late-session-response handling, cookie/CSRF forwarding, bounded JSON proxy writes, stale-write no-retry behavior, static assets/security headers and status failures. Temporary server fixtures are not the React UI. `npm ci` must verify the inherited candidate lock before a full build is accepted.

## Browser checks

Install Chromium with `python -m playwright install chromium` after installing the Python dev dependencies. With the full app running locally:

```bash
python tests/e2e/browser_smoke.py
```

This checks the signed-out gate, operator guide, invitation/recovery navigation, anonymous business-data rejection and mobile overflow. It creates anonymous sessions but no accounts.

`tests/e2e/accounts_smoke.py` is deliberately separate: it creates synthetic accounts, workspaces, invitations and audit records using the actual UI and checks private workspace isolation, viewer permissions, session revocation, system outages, and mobile layout. It now calls `planning_smoke.py` to create/approve/acknowledge a policy, create/approve a milestone, preview/approve a 700-unit allocation, reject a reserve overspend, create a successor draft, and check read-only mobile views. This helper is not a standalone deployment command. It requires an unbootstrapped disposable native deployment, a database name ending in `_test`, enabled development tools and `CL_E2E_ALLOW_ACCOUNT_CREATION=1`. Use the provided CI workflow or an isolated equivalent with matching CL_DB_* settings. Never run it against your normal application database. It does not save passwords, tokens or secret-bearing screenshots, and it does not pretend to delete permanent audit history afterward. A second run needs a newly provisioned disposable installation.

## Persistence and source checks

`python scripts/check_stack.py --allow-synthetic-seed` remains an opt-in Docker test that creates only the marker and temporarily restarts/stops services. It preserves the volume and attempts to restore the database service in a finally block. Only run when interruption is acceptable.

```bash
python scripts/verify_source.py
bash -n scripts/manage.sh
node --check apps/web/server.mjs
```

`scripts/check_typescript_syntax.cjs` optionally uses an installed TypeScript package via CL_TYPESCRIPT_PATH. It is syntax-only, not React semantic checking. Check migrations 0001, 0002 and 0003 against the phase-3 ZIP; all must remain identical.

## Later manual acceptance checklist

1. Fresh setup: start from a clean folder; setup requires the explicit operator token; repeated setup is refused. No default account or password exists.
2. Login/session: wrong passwords give the same message as unknown users, repeated attempts are limited, logout/reload requires login, another session can be revoked, password change invalidates other sessions, idle/absolute expiry works.
3. Team access: create two workspaces; invite five fictional contributors and a separate reviewer; use isolated browser contexts. A member without a project grant sees no project. Viewer/project-admin/workspace-admin differences match the matrix.
4. Invitations and changes: expired/revoked/reused links fail; a second pending invitation replaces the first; an existing account must sign in; suspended access is not restored by an invite; stale version updates fail; last-owner removal is blocked.
5. Recovery and history: operator verifies the owner, issues a recovery token, user sets a password, reused/expired tokens fail. Disable/enable and membership changes preserve identity and append history. No normal reset deletes accounts.
6. Upgrade/interface: preserve `.env`, migrations and marker; stop/start keeps accounts. Test keyboard/mobile layouts, error/loading states, permission changes in another session and API/database outage recovery.

The additional policy/budget manual checklist is in `policies_and_budgets.md`. Include clean-build, 0002→0003 preservation, two-admin competing allocation, stale preview, policy succession, joining/departing participants and zero-issued-credit checks.

User acceptance is intentionally deferred until the user tests the project. Do not mark these checks complete just because their code or checklist exists.

## Phase-4 additions

The new tests exercise one-to-one approved allocation binding, positive/incomplete/overbudget scopes, exact unit and percentage plans, an explicit unassigned rounding bucket, stable ties, scoped participants, coordinator/admin/reviewer permissions, pinned-policy acknowledgement changes, immutable amendments, state transitions, stale reviews, exact submission snapshots, historical read access, duplicate/cancel protection, legacy budget-route guards and safe draft resizing. A deterministic randomized rounding test covers 500 cases and counts as one test.

Five additional native PostgreSQL tests in `tests/test_postgres_work_packages.py` cover competing package binds, stale concurrent scope edits, repeated submission, repeated cancellation and 0003→0004 preservation/guards. They use the same explicitly disposable PostgreSQL fixture and are skipped only when no native test URL is configured. SQLite does not prove PostgreSQL locking or deployment behavior.

`accounts_smoke.py` additionally calls `work_packages_smoke.py`: create a three-deliverable package under the existing 700-unit fixture, mix direct/percentage attribution, approve/start/submit, inspect viewer restrictions on mobile, withdraw/amend while preserving the original submission, cancel once and inspect returned planning capacity. It is supplied actual-browser acceptance source, not a rendered test performed in this delivery. The first-owner/disposable test protections are unchanged.

The Node suite adds exact work-package form serialization, budget bounds, percentage validation, preserved raw attribution round-trips and UTF-8 request limits. It still does not render React. `npm run build` must complete before accepting the UI; syntax transpilation alone is insufficient.

Use `work_packages.md` for the deferred manual checklist. The current complete-backend test command also records every skipped native test; do not count skipped tests as passed. Earlier interrupted/timed-out attempts are not successful runs. Only the completed run in `docs/test_results.json` is used for reported totals.

## Phase 5: evidence tests

The ordinary backend suite now includes bounded text/raster validation, private local object storage, stubbed S3 contracts, protected evidence routes, restricted-history redaction, snapshot/stale-submission behavior, retirement failure, migration preservation and immutable/scoped records. `tests/test_postgres_evidence.py` adds five genuine native race/upgrade cases; without `CL_TEST_DATABASE_URL` they skip explicitly, rather than using SQLite as a stand-in for locks.

`npm test` includes evidence utilities and the real Node proxy with large bounded JSON and binary response/header tests. These do not render React. The guarded `tests/e2e/accounts_smoke.py` now calls evidence upload/image/text/revision/stale/resubmit/restricted-view checks through `work_packages_smoke.py` and `evidence_smoke.py`; a built frontend and disposable opted-in native deployment are required. Its presence is not an executed browser result. `docs/evidence_and_artifacts.md` has the manual Windows/mobile/persistence checklist. S3 live bucket/credential/retention and Docker artifact-volume restore checks remain unexecuted.

## Phase 7 additions

Read `testing_phase7.md` and `test_results.json`. The current source adds exact calculation fixtures, protected previews and saved-example checks, native database test source and an opt-in browser scenario. No unexecuted browser/native test is counted as passed.

## Phase 10 continuation

The current source is 0.10.0-phase10. Follow `upgrade_phase10.md`, `ai_connections.md`, `ai_operations.md` and `testing_phase10.md` for optional synthetic AI setup. Normal startup requires no AI key. Only explicit operator/payer opt-in permits a potentially billable synthetic probe; actual evidence assessment remains phase 11. New `ai_credentials` and separate `ai_master` volumes require protected consistent recovery. All earlier unexecuted native/build/browser/live checks remain open.
