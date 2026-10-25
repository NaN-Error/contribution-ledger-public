# Phase 11 test and deferred acceptance checklist

Executed counts and exact commands live in `test_results.json` and `verification/phase11_*`. A source test file is not proof that its environment-dependent test ran. Native PostgreSQL, Windows/Docker, actual React rendering, deployed worker privilege recovery and live providers remain separate open gates.

## Available automated commands

```text
cd apps/api
PYTHONPATH=. python -m pytest -q
cd ../web
npm ci
npm test
npm run build
```

The Python suite includes parser/schema/reference checks, redaction and bounds, submitted-work packet creation, disclosure/payer separation, plan idempotency, rerun lineage, advisory visibility, invalid outputs, revocation during generation, ambiguous billing, lost workers, migration preservation, immutable histories and reviewer commentary without automatic awards. A synthetic end-to-end test independently finalizes accepted work after recording commentary through the separate review API.

The provider-message contract tests inspect simulated requests to OpenAI, Anthropic and Gemini; they are not live-company tests. Node tests execute actual pure TypeScript helpers plus existing proxy/gateway contracts. Transpilation is syntax checking, not a full React typecheck or browser test.

## Disposable native PostgreSQL

Set `CL_TEST_DATABASE_URL` to a deliberately disposable PostgreSQL database ending `_test`, then run `pytest -q -m postgres` in `apps/api`. Tests allocate isolated schemas. New native cases cover boolean freshness, a complete mock result with zero credit writes, duplicate-queue races, one worker claim, revocation before dispatch, immutable histories and scoped plan constraints. Earlier native tests remain. Do not run destructive or concurrency tests against a real game/team database.

Provision the supplied restricted AI worker only in a disposable deployment, confirm it can read sealed packets and insert results, and confirm raw evidence/password/ledger/finance read-write attempts fail. Test actual process death, credentials rotation, account removal, database restart and held cost reconciliation. SQLite tests do not verify these PostgreSQL grants or concurrency behavior.

## Browser walkthrough (deferred)

Prepare a fictional package with a statement, a UTF-8 test report, a raster image, a source link and a restricted artifact. Submit it; create a synthetic connection, review zero pricing, probe compatibility, and explicitly approve a new evidence-review profile. No real secret or provider request is needed.

Open Work packages → AI-assisted evidence review. Confirm that excluded images/URLs/restricted evidence are labeled, selected text is shown as plain text, packet line numbers are clear, and no request has been dispatched. Include a fake key pattern in synthetic text; verify redaction. Never use a real key to test masking.

Create an official plan, inspect its exact payload, enter a disclosure reference and explicitly approve it. Separately quote and authorize the zero-cost synthetic request. Advance the optional worker, refresh, and inspect the result. Every criterion should be insufficient, explicitly labeled synthetic. Confirm contribution credit stayed unchanged.

As the independently assigned reviewer, inspect original evidence and record agree/modify/reject/request-evidence commentary. Confirm these actions do not submit acceptance or issue units. Then use the ordinary manual decision and finalization controls; only those should change credit. Old results remain preserved and marked historical after accepted work or changed evidence.

Test a draft/advisory profile, another reviewer, a contributor/viewer, a removed user, an expired grant, stale evidence, repeated commands, a successor run through a new packet, input limits, missing original storage and worker/network outage. All visible runs should remain discoverable, not only favorable responses. The manual review remains usable with AI entirely disabled.

Use keyboard-only/mobile layouts, inspect loading/error/empty states, and verify plain-text rendering of malicious HTML-like strings. Real source files must not execute. Use `tests/e2e/assessment_smoke.py` only with its explicit disposable-local setup; it is provided but unexecuted here.

## Live providers (not executed)

Only after the provider/data arrangement and credentials are approved locally, use a harmless synthetic packet with a small reviewed budget. Deliberately enable all required live flags and approve that single packet/request. Confirm actual schema/request compatibility, model identifier and token billing. Test refusals/truncation/rate limits without blind regeneration; monitor the provider's independent account usage. Never give a test expectation permission to spend unlimited funds. A successful structured response does not prove contribution judgments are fair.

## Retention, installation and rollback

Test a backup restoration covering database, evidence, credential ciphertexts and the separate master. Retiring an original artifact must preserve explicit assessment-copy history rather than falsely promise erasure. Nonempty downgrade must be refused. Keep the open frontend dependency-installation/typecheck and prior-phase browser/runtime checks; implementing phase 11 does not resolve them.
