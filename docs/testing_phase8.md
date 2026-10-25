# Phase 8 testing and acceptance

The user has deferred thorough application acceptance until the complete project exists. The checks below are supplied for that later process; their presence does not mean they ran. All data and accounts used here must be fictional or explicitly authorized for testing.

## Executed here

The complete backend run passed **635 tests**, with **39 native PostgreSQL cases skipped**. Of these, 125 backend passes and six native cases were added in phase 8. It used the existing injected SQLite fixtures, actual local file operations, cryptographic signing checks, bounded fake provider responses and stubbed cloud contracts. No external GitHub connection was used. Node pure/helper/API-client/static-proxy tests pass separately; see the final count in `test_results.json`. A fixture HTTP server is not a rendered React browser.

Raw evidence is under `verification/phase8_*`. Do not count deterministic input loops as individual tests or add earlier partial reruns to the total. Offline PostgreSQL migration SQL generation is not a native database execution.

## Commands

From `apps/api`, run the backend test suite in its pinned environment:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
```

The existing documented backend dependency installation/container-test procedure still applies. Native tests require a dedicated disposable PostgreSQL database and the project's `CL_TEST_DATABASE_URL` guard. Follow `testing.md` and never point destructive/native fixtures at the user's development or real data database. The six new native cases cover concurrent import idempotency/exclusivity, worker claims/fences, immutable history/truncate guards, scoped foreign keys and repeatable migration.

From `apps/web`:

```text
npm ci
npm test
npm run build
```

`npm test` compiles only its pure-module subset and runs Node fixtures. The full build must pass the semantic React check and Vite build separately. The source transpilation report is syntax-only. Run all earlier real browser flows, then the new `tests/e2e/github_callback_smoke.py` against a disposable built deployment using its documented command-line options. That smoke checks local callback handling, query cleanup and no unexpected external call; it is not live OAuth acceptance.

## Local Docker / Windows acceptance

Start from both a fresh extraction and an upgraded phase-7 volume. Confirm existing account, marker, evidence, finalized award, open dispute and saved simulator example survive. The new GitHub tab should explain disabled configuration without breaking manual operations. Confirm no external service is called merely by startup. Check the private secret volume provisioning from a Windows path containing spaces and verify API/worker can read only the staged allowed files; private files must not appear in images, process output or web downloads.

Run `provision`, `start`, `status`, `pause`, `step` and `manual` explicitly. Confirm `manual` stops the separate worker as well as disabling the API adapter. Stop services before rotating keys or upgrading again. Test restart recovery from a killed checkpoint and an expired lease; do not assume a one-second recovery or exactly-once networking.

## Authorized live GitHub acceptance — not executed

Create a dedicated private fixture repository with two known authors, multiple commit emails, a co-author trailer, a PR merged by a different person, an issue/comment, review, simple check, missing author and a binary change. Give only the required read permissions to the App. No repository builds or scripts are run by this application. Use a project administrator who is also authorized to share the repository; verify an ordinary GitHub reader is not offered as a sharing authority.

Exercise state tampering/replay, another ledger session, wrong installation, wrong App ID/key, suspended installation, removed repository, insufficient/read-plus-write permissions, expired local proof and provider denial. Confirm a selected repository cannot be replaced by another ID in the confirmation. Inspect that OAuth codes/state do not persist in the URL/storage/logs and user tokens are not stored. Start an organization SSO session where required.

Create a narrow import and inspect PRs/issues/commits/reviews/checks with actual capture dates, default-branch SHA and role distinctions. Re-import without changes: no duplicate source content or credit. Change a PR after the requested cutoff: a new source version/limitation must appear, not a reconstructed historical fact. Change head/base during file capture: preserve the omission. Test capped pagination, rate-limit delay, exhausted budget, quota, oversized response and cancelling an in-flight request; partial evidence must remain visible. Don't intentionally overload GitHub to manufacture a rate limit; use stubs for destructive/high-volume cases.

Map two identities and unmap one; multiple matching emails must not auto-map. A bot cannot map to a human. Attach a preserved source to a permitted work package, then attach it again: one link, zero new contribution units. Confirm restricted visibility for contributor/reviewer/admin, explicit project sharing for authorized readers, historical restriction after a visibility edit, and denied access after membership removal. Update the remote PR: the pinned work evidence, finalized credit and saved simulator example must not silently change. Disconnect: stop future fetches, retain prior history, and do not imply GitHub uninstall.

The maximum 24-hour sharing-authority lease is a known limit: individual GitHub role revocation is not observed instantaneously in this phase. Phase 9 and a real security review must address that deployment boundary before public use.

## Remaining gates

No native PostgreSQL, Docker/PowerShell, full React build, actual browser, live GitHub, independent security audit, least-privilege DB deployment, live S3, recovery drill or human acceptance was completed here. Keep those explicitly open. Synthetic tests and separate test users cannot prove real human independence or legal permission to share source.
