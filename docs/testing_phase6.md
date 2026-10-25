# Phase-6 verification checklist

These are acceptance instructions, not a claim that the checks ran. Actual completed suite results are in test_results.json and verification/. User testing remains deferred at the user's request.

## Automated commands

From apps/api, after installing the committed development requirements:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

In PowerShell: `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q`.

The native subset requires an explicitly disposable PostgreSQL database ending `_test` in CL_TEST_DATABASE_URL. It uses isolated schemas and real independent connections. A configured but unreachable server is a failure, not a silent SQLite substitution. Run `python -m pytest -m postgres -q`. The five new native tests cover same/different command races, concurrent partial awards, history UPDATE/DELETE/TRUNCATE rejection and adjustment finalization races. Complete earlier native suites remain required. Privilege grants/ownership/inherited-role acceptance need a separate staged configuration, not only these races.

From apps/web: `npm ci`, `npm test`, `npm run build`. Node utility tests do not render React. A syntax transpilation pass is not semantic typechecking. The inherited candidate lock still needs a successful clean install; no fabricated shims or React mocks are shipped as framework verification.

## Synthetic human workflow

Create distinct fictional contributor, independent reviewer and independent resolver identities in a disposable test deployment; all relevant people acknowledge the approved policy. Keep any browser passwords or sessions private. Test ordinary and denied paths using separate sessions rather than changing hidden fields in one UI.

Review a 100-unit scope with 60-unit implementation and 40-unit tests. Assign a nonbeneficiary reviewer, inspect its packet, record insufficient findings and confirm no award. Start a fresh round after supplying actual test evidence; support each criterion with the exact submitted references. Verify that a vote alone still issues zero. Explicitly finalize only implementation and check 60 finalized, 40 pending, protected reserve unchanged. Refresh/replay the command and verify no duplication. New evidence for tests should stale its earlier unfinished review but retain implementation's original award. Resubmit and independently accept tests; exact total becomes 100 and the package completes.

Attempt self-review, unassigned decisions, a viewer's write, stale target hashes, missing/duplicate criteria, invented evidence references, unacknowledged participants and revoked reviewer access. Every attempt should fail without credit writes. Test policy quorums of two/three; one vote cannot bypass the requirement. Test loss of response and exact request replay. Verify request failure after attempted posting rolls back awards/events/projections together.

Inspect Contributions on desktop and a narrow mobile screen. Every percentage must show policy, milestone, pool and denominator; role components and current/original attribution remain inspectable. Private artifact titles/findings must not appear to unauthorized people through the review page, notifications, browser cache or API. Check keyboard order, labels, table scrolling, refresh/loading errors and empty states. Read-only users must have no create/decide/resolve controls.

Open a dispute, add a supplementary note and verify the affected pool's future-close blocker. Assign a genuinely independent resolver, not an original recipient or reviewer. Propose 60/40 reallocation, obtain the original-policy quorum and finalize. The unchanged 100-unit original award plus -40/+40 correction lines must produce exactly 60/40 current credit. Attempt 101 total units, negative/decimal atoms, duplicate roles, foreign recipients and a recipient resolving their own correction; all must fail. New notes/reassignment must stale resolution votes. Uphold keeps events unchanged. A repeated resolution must not duplicate adjustments. Settled cases preserve notes and cannot be silently edited.

Use the audited check-credit command to compare/rebuild projections on synthetic deliberately altered caches, never altered ledger events. Confirm unchanged history and an audit record. Suspend a contributor and retire their raw evidence; previously finalized credit must remain. Verify database and artifact-volume persistence after restart/rebuild. Actual operations with PostgreSQL, Windows, Docker, browser, live S3 and backups remain separately recorded gates.

## Browser smoke source

The earlier browser scripts remain at tests/e2e/. credit_smoke.py is a separate explicitly opted-in browser flow for a preassigned single-reviewer synthetic review in an already running disposable `_test` deployment. It refuses normal data settings and requires local credentials/IDs in environment variables. It is not implicitly run by source creation or by the Node tests. Its instructions are in the module docstring. The guarded earlier account smoke remains in CI; the preassigned credit smoke needs deliberate fixture setup before invocation.
