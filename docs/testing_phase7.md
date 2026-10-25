# Phase 7 verification and deferred acceptance

Executed counts and artifacts are in `test_results.json` and `verification/phase7_*`. Historical phase-6 results are under `releases/`. Do not infer a successful React render from Node tests or PostgreSQL locking from SQLite fixtures. The user has deferred thorough acceptance testing until project completion; the following procedures remain instructions until actually performed.

## Executed suite structure

`apps/api/tests/test_simulator_calculation.py` loads exactly 25 named fictional cases from `tests/fixtures/simulator_cases.json`. Expected cent amounts are explicit, including the agreed five-person $10,000 case. Cases cover code/art/QA/research, departures, unfinished work, corrections, empty/disputed pools, zero totals, large totals and stable ties. Seeded quota/conservation/permutation loops are counted as tests, not thousands of extra passed cases. Invalid strict types and the method's non-monotone rounding behavior are tested separately.

`test_simulator_periods.py` checks local month boundaries, a DST-changing month, UTC conversion, leap/year rollover, invalid/ambiguous/nonexistent boundaries and original-acceptance eligibility. `test_simulator_flow.py` exercises actual routes against injected SQLite: partial credit, pending reserve, no economic writes from preview, saved reproduction, changes after capture, dispute blocking/resolution, stale/idempotent saves, viewer/current access, foreign IDs, CSRF, transaction rollback, history guards, departed credit, tamper errors and projection reconstruction.

`test_simulator_five_person.py` creates an approved mixed-pool policy and acknowledged participants through the actual application. It plans art and research deliverables, attaches synthetic image/statement evidence, obtains an independent review, finalizes credit, calculates and saves the expected five-person distribution. It does not directly fabricate credit rows. This is an application integration test, not a browser run or proof of human independence.

`apps/web/tests/simulator.test.mjs` and `simulator_api.test.mjs` check exact decimal input/display, month/URL helpers, explicit non-payable flags, authenticated transport, stale responses and saved GET behavior. They do not load React or render controls.

## Repeat local automated checks

From `apps/api`, after installing the committed development dependencies and using disposable test settings:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -q
```

From `apps/web` after a successful network-backed install:

```powershell
npm ci
npm test
npm run build
```

Use the existing root test scripts for container execution. The API test image now copies the canonical synthetic `tests/fixtures` corpus. Never point integration or seed procedures at actual project data.

## Native PostgreSQL checks — unexecuted here

Follow the existing guarded disposable `*_test` PostgreSQL configuration, then run the full backend suite. Five phase-7 native tests in `test_postgres_simulator.py` cover simultaneous identical saves, capture racing a credit finalization, UPDATE/DELETE/TRUNCATE guards, scoped foreign keys, and repeatable migrations. Earlier native tests remain required. Successful offline SQL generation is not a native migration run.

Provision/test real runtime roles separately before remote use. Default Compose still uses an operator-owned account. A successful request as that account does not prove least-privilege enforcement. Restore both data and artifact stores, verify old awards/scenarios, then test new writes in an isolated recovered deployment.

## Browser and Windows checklist — deferred

Start from a fresh installation and separately from a preserved phase-6 copy. Verify the new migration without changing accounts, artifacts or earlier credit. Sign in, open a project and choose Revenue simulator. Verify keyboard focus, labels, mobile table scrolling, loading/errors, month and amount validation, explicit draft/source choices and policy warnings.

Use a fully accepted fictional project. Confirm pending units and protected reserve remain outside person denominators. Choose another source-policy version and verify its older/newer awards are not mixed. Compare a draft calculation policy; confirm it stays draft and the ledger does not change. Inspect both the displayed timezone bounds and incomplete-month warning.

Calculate $10,000, save a titled hypothetical example, reopen its project-protected link, and verify exact cents and rounding details. A change to the form must hide the previous preview. Change credit/attribution or planning from another session before saving; the stale save must fail and require a new review. Repeating one successful save must return the same example. Later credit and corrections change new previews, not saved examples.

Create an unresolved dispute on an included award. The affected pool must have no recipient amounts and its cents must remain unallocated; the other pool cannot receive extra money. Resolve through independent review and calculate again. Verify a departed contributor's finalized credit stays present, while a removed viewer cannot fetch a saved example URL. Clearing sessions or using a private window must require sign-in. Do not mistake inability to refetch for erasing an already downloaded copy.

Exercise exact-cent fixtures, including one cent among three equal identifiers, in the backend corpus. UI displayed percentages may be rounded labels, but line amounts must match the integer engine, and recipient plus blocked totals must equal the input. A zero input with an empty pool is still explicitly blocked. No scenario route can award credit, approve a financial close, export a payment order or send money.

## Optional actual-browser smoke source

`tests/e2e/simulator_smoke.py` requires Playwright/Chromium and a prepared, explicitly synthetic localhost deployment backed by a disposable `*_test` database. It is not run automatically. Required environment: `CL_E2E_ALLOW_SIMULATOR=1`, normal development DB settings, `CL_E2E_EMAIL`, `CL_E2E_PASSWORD`, `CL_E2E_WORKSPACE_ID`, `CL_E2E_PROJECT_ID`, `CL_E2E_SOURCE_POLICY_ID`, and optionally `CL_E2E_BASE_URL`. The project name must include `synthetic` or `smoke`, and it must already contain accepted credit. The script saves one non-payable example and verifies unchanged total credit and signed-out denial. Keep credentials local, not in source or chat. Running it without these prerequisites is not a passed acceptance test.

## Retained gates

Clean dependency resolution, full React semantic typecheck/build, actual browser rendering, Docker/PostgreSQL, Windows PowerShell, non-owner DB privileges, live S3, security/load/restore and human acceptance remain separate gates. No live AI or paid external service is part of phase 7. Current test results must describe their actual environment and cannot stand in for any of these gates.
