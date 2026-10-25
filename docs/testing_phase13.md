# Phase 13 testing and deferred acceptance

Use synthetic data in a disposable local project. Do not supply actual bank/payment references or change an actual compensation agreement. The release notes and `test_results.json` report executed results separately from tests supplied but not run.

## Automated commands

From `apps/api`, using the installed project Python dependencies:

```text
python -m pytest -q tests/test_finance_rules.py tests/test_finance_workflow.py tests/test_finance_integrity.py tests/test_finance_access_payments.py
python -m pytest -q
```

From `apps/web`:

```text
npm ci
npm test
npm run build
```

Native PostgreSQL tests in `tests/test_postgres_finance.py` require the same explicitly configured disposable `CL_TEST_DATABASE_URL` as earlier native suites. They exercise simultaneous identical period/entry/close/payment commands, immutable history including TRUNCATE, and cross-project database references. Never point test fixtures at a real database. Optional broker tests are independent of this finance feature.

`test_finance_rules.py` includes one seeded 500-scenario arithmetic loop counted as ONE test, not 500 passes. Financial application fixtures create synthetic evidence, independent review and finalized credit through the real routes; they do not call GitHub/AI/banks. Clock overrides are isolated to tests for finished-month scenarios, not a production bypass.

## Manual browser checklist

**Existing data and migration:** upgrade from phase 12 without changing old migrations or deleting volumes. Existing owner, policy acknowledgements, accepted credit, disputes and hypothetical examples remain. Readiness reports 0013. Restart and verify private finance documents and close records persist. Verify populated downgrade refuses before deleting history.

**Roles:** administrator creates a period and approves source records. Finance member can inspect/upload/propose and record declarations but cannot approve/void/create periods. Contributor, reviewer and viewer cannot read financial source documents, full closes or another person's statement by guessing IDs. Current recipient can inspect their own result without private financial inputs. Suspended access cannot download old links. Cross-project IDs fail; hiding buttons is not the security test.

**Statements and receipts:** attach synthetic plain text and safe raster originals, inspect checksum/download headers, test invalid names, oversize bytes, non-UTF8 and forged image extensions. Text previews must not execute HTML/Markdown or formulas. Enter a net receipt with platform fees and refunds already removed; a second linked refund deduction must fail. Unsupported cost category and wrong receipt basis fail. Pending entries block; rejected/voided entries do not deduct. A prior closed entry cannot be edited or voided.

**CSV:** exact header, positive integer cents, quoted description with commas. Replay identical command returns the same rows. Change/truncate the command under the same ID, duplicate an external line, place an invalid/duplicate row after a valid new one: no partial import. Test formula, Unicode digits, decimal, huge, zero and negative values. Counts stay bounded. References from other periods retain duplicate protection.

**Reserves/deficits:** initial 1,000 cents minus 1,600 cents yields zero distribution and -600 carryforward. Next month's receipts absorb that deficit. Holds reduce current distributions without assigning ownership; releases cannot exceed the reserve. A new unfunded hold blocks. Closed-period adjustment uses a later documented correction linked to an earlier approved source, never overwrites that source.

**Close review:** month must have ended. All required acknowledgements, attribution and financial entries must be resolved. Open award disputes, empty required pools, unfinished initial release work, unarchived historical scope and unavailable approved documents block. Save preview, then add a valid financial entry or change relevant ledger/dispute state: old proposal approval must fail. Repeating identical finalization yields one close/release snapshot and no duplicate award.

**Release corrections:** first freeze Alice 100%, then resolve a real synthetic attribution dispute to Alice 60%/Bob 40% through independent review. Next close blocks until an explicit same-roster release correction is approved. Future close reflects 60/40; first close/export stays identical. Newly budgeted work cannot enter the correction roster. No automatic retroactive refund or payment instruction.

**Exports:** inspect exact recipient cents and rounding. CSV/JSON/ZIP exports repeated before and after a payment declaration are byte-identical. Check ZIP file hashes. Names beginning `=`, `+`, `-`, `@`, hidden controls or full-width formula symbols display with a visible `text: ` prefix in CSV; original names remain JSON data. Never erase those prefixes and re-execute data. Corrupt stored calculation while updating only its outer hash in a disposable copy: replay rejects inconsistent arithmetic.

**External declarations:** partial record reduces outstanding only. Duplicate provider/reference fails even after a void. Wrong recipient, future time, pre-close advance, missing offset and wrong close hash fail. Overpayment requires explicit acknowledgement and is displayed separately. Voiding a mistaken declaration preserves its history and original reference; it does not reverse a transfer. Frozen amounts remain unchanged.

**Responsive/accessibility:** keyboard navigation, readable labels, errors announced, long names/UUIDs wrap, table scroll on a 390-pixel viewport, checkboxes separate from submit buttons, loading/error/empty states, no disappearing entered values without a successful command, and no fake green payment-success indicator.

## Supplied rendered smoke

`tests/e2e/finance_smoke.py` is opt-in and read-only against a prepared synthetic closed period. It requires a local disposable `_test` deployment, `CL_E2E_ALLOW_FINANCE=1`, workspace/project/period IDs, and a finance/admin test login in operator environment variables. It verifies period navigation, closed distribution, declaration UI, repeated export and unchanged credit at desktop/mobile sizes. It does not seed records, record payments, alter awards, contact external providers or save screenshots/traces. Preparing a synthetic fixture and running an actual built browser remain explicit acceptance work.

## Open verification gates

A successful structural parse/transpile is not a full React typecheck or render. A valid candidate lock is not a clean downloaded install. Mock provider/GitHub tests are not live integrations. SQLite does not establish PostgreSQL concurrency or deployed worker grants. No test fixture proves worker classification, ownership, tax compliance, actual bank receipts, fairness, secure backup recovery or production readiness. Those gates and the user's deferred thorough testing remain open.
