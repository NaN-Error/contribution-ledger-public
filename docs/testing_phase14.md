# Phase-14 verification checklist

The user will perform thorough acceptance after development. Keep each unchecked native/browser/live item open until it is actually run. `test_results.json` contains the executed counts, not this checklist's intended outcomes.

## Automated source checks

From `apps/api`, with the pinned environment installed:

```text
python -m pytest -q
```

New suites are `test_phase14_mfa.py`, `test_phase14_archive.py`, `test_phase14_recovery.py`, `test_phase14_boundaries.py` and `test_postgres_phase14.py`. Existing account/tenant/evidence/ledger/GitHub/AI/finance tests remain. Native cases require `CL_TEST_DATABASE_URL` for a disposable `*_test` database; no SQLite success replaces them.

From `apps/web`, run `npm ci`, `npm test`, `npm run build`. From the root, run `python scripts/verify_source.py`, `node scripts/check_typescript_syntax.cjs`, and the documented actual browser scripts. Syntax transpilation and pure Node helpers do not render React or establish type safety. The account browser smoke includes `mfa_smoke.py` only when `CL_E2E_ALLOW_MFA_ENROLLMENT=1`; initialize its protected master first and use an explicit absolute `CL_AUTH_MASTER_KEY_FILE` shared by the operator and API. CI supplies this path and initialization. The new UI drill has not been executed here.

## Deferred browser and account drill

Use fictional accounts and protected local configuration. Initialize the MFA master explicitly. Enroll an account using an authenticator, confirm a code and privately save recovery codes. Verify an earlier session is revoked. Log out, enter the password, verify project/evidence/finance routes are inaccessible until MFA passes, then sign in. Try the consumed step/code again and verify rejection. Confirm a recovery code works once with the password and fails on reuse. Confirm expired challenges require a fresh login.

Test incorrect passwords, invalid codes, rate limits, blocked cross-origin mutations and stale CSRF. A password reset must leave MFA enabled. A local verified removal must revoke sessions. A verified operator reset must require re-enrollment rather than grant project access. A missing master cannot be initialized over existing factor rows. Review recovery-code visibility with screen readers, keyboard navigation and mobile layout; never record the values in the test report.

For staging, verify required enrollment after first-owner setup/invitation, HTTPS host-prefixed HttpOnly cookies, no password-only privileged endpoint, no factor-disable action, hidden docs, disabled development seed/reset and blocked AI/GitHub calls. Observe actual Docker NAT peer behavior; do not widen access as a troubleshooting shortcut. Test denied clients from another machine before accepting a private-network bind.

## Native restore and security drill

Create a fictional accepted deliverable, closed financial distribution and referenced text/image documents. Configure test encrypted credentials and an enrolled MFA account. Save expected identifiers/counts and a financial JSON export, not secrets. Stop writers, capture the deployment, move the matching recovery bundle/key into their separate controls and restore to a new isolated `ledger-restore-*` target. Verify no host ports/workers exist. Compare the frozen export and calculation, every expected required document, retained-key decrypt counts and revoked copied sessions. Test missing bundle, altered byte, wrong key and missing blob failures; the original deployment must remain untouched.

Execute native multi-connection MFA recovery-code races and all earlier budget/finalization/close races. Provision the staging runtime role, test normal operations, then demonstrate that it cannot migrate, truncate or disable immutable-history protection. Test each optional worker under its designated role separately. A role tested as the database owner is not the limited-role test.

Run an upgrade from a populated phase-13 database, repeat migration, and test a failed upgrade in isolation. Do not attempt destructive history downgrade on the original. Record which recovery source/image/role commands actually worked. Stop after a failed check; do not turn its readiness field true.

## Acceptance evidence to record

Record source hashes, installed dependency/architecture/image digests, native versions, test command and exit result, operator, UTC time, capture/restore IDs, anonymized result counts, browser/platform and known failures. Do not include `.env`, passwords, recovery codes, keys, raw private packets or original confidential documents. Keep full restricted diagnostics locally. A completed human shadow pilot is phase 15, not inferred from fictional accounts.
