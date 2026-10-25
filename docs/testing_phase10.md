# Phase 10 testing checklist

All data below must be fictional unless the operator and payer deliberately authorize an isolated live test. Provider fixture tests use fake responses; there is no automatic paid generation. Actual executed results are in `test_results.json` and `verification/phase10_*`. The user has deferred thorough acceptance testing until full project completion; this checklist preserves rather than silently clears those gates.

## Automated commands

From `apps/api`, using the project's installed pinned development environment:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

From `apps/web`:

```bash
npm ci
npm test
npm run build
```

The development environment executed backend tests against injected SQLite, local AES-GCM/files, mock provider HTTP boundaries and inherited fake integrations. Native PostgreSQL cases require an expressly disposable `_test` database and the existing test configuration. They are not SQLite concurrency proofs. The two optional Celery/Redis cases retain their own dependency/broker requirements. Never target the real application database with test reset fixtures.

The source-only browser scenario `tests/e2e/ai_smoke.py` is called from the opt-in `accounts_smoke.py`. It uses actual UI/API and advances real test DB jobs with the fake provider, refusing live flags. It is not a test of a separately deployed restricted worker process. Follow existing browser harness setup and disposable-database safeguards. No browser scenario was executed here.

`python scripts/verify_source.py` checks Python/JSON/YAML/source/lock structure, not installed compatibility. Syntax transpilation of TSX is not a semantic React build. The inherited candidate frontend and optional jobs locks still require downloaded installation.

## No-cost end-to-end acceptance

1. Start from a preserved phase-9 fixture, upgrade, and check migration 0010 without account/evidence/credit resets. Repeat migration and restart; values stay unchanged.
2. Initialize/start the optional AI worker. With live and paid flags disabled, the only selectable provider is mock. No key is accepted for mock and no provider request occurs.
3. Owner creates a zero-cap private synthetic connection. Another contributor/viewer cannot see its catalog, jobs, key or cost records by guessing URLs. A shared connection is visible only to authorized project admin/reviewer roles; finance/contributor is not implicit billing authority.
4. Catalog job advances only with the worker operating. View the synthetic model, save a zero price review, prepare a quote and inspect the synthetic prompt. GET quote must not invoke generation.
5. Approve exactly one probe. Replay its request ID and confirm one job/one invocation. Zero-cost result has a protocol pass, not contribution units or a personal score.
6. Share the connection, create a profile draft, review it and approve it as project administrator. Catalog refresh/new model discovery does not replace the approved profile. A new profile requires explicit prospective approval with the expected previous approved ID.
7. Revoke the connection, rotate a permitted fake live-fixture key, suspend its owner, or remove relevant sharing. Previously queued jobs must fail eligibility or cancel safely; history remains visible under permitted access. Profile history does not become a hidden fallback model.
8. Repeat cross-workspace, stale version/hash, viewer write and non-owner spend attempts. Ordinary API/client response/log storage must not include keys or provider error bodies. Validate server checks, not just hidden buttons.

## Provider-contract and spending cases

Use simulated OpenAI, Anthropic and Gemini responses: list pagination, missing/unknown capabilities, unsupported modalities, denial, invalid key, 429, GET timeout, truncated JSON, duplicate keys, refusal and unreported/cached/thinking token usage. External redirects or model text must not create a request to an unapproved origin.

Under simulated permitted paid configuration, review a current price, reserve exact micro-USD, and submit two concurrent jobs against insufficient shared remaining capacity. Exactly one authorized reservation can win if only one fits. Run this against native PostgreSQL, not just sequential SQLite. Current code uses the common scoped lock.

Kill a worker after durable dispatch, let the lease expire, and verify uncertain cost/no automatic second POST. Revoke after the provider receives a request and confirm stale qualification cannot commit while known/uncertain spending remains accounted for. Reconciliation is one reasoned immutable payer entry; repeated identical reconciliation is safe and conflicting declarations fail.

An expired price, stale model fingerprint, changed credential generation, insufficient remaining cap, changed UTC month, disabled operator paid flag and more than five unresolved holds must block/cancel as appropriate. A charge above the reservation remains recorded. A failed model-access/protocol check invalidates prior qualification rather than leaving a stale positive indefinitely.

## Storage and native role checks

Verify AES-GCM context-binding, tamper rejection, read-only worker credential mounts, no evidence/GitHub key mounts, symlink rejection and private master permissions. Repeat initialization without replacing the master. Preserve encrypted files after an ambiguous DB commit; confirm pre-commit rejected writes are cleaned. Test an external-provider revocation separately because local revoke does not call the provider key-management API.

Provision the reserved worker role on a disposable PostgreSQL instance and connect as that actual role. Confirm it can run synthetic catalog/probe/maintenance, including narrow workspace locking, but cannot read password hashes, evidence/ledger/finance tables or approve profiles/modify memberships. Check effective column/PUBLIC grants, not merely intended SQL strings. Test startup failure with an unsafe preexisting role rather than silently reusing it. This role provisioning has not been executed in the development container.

Restore matching database/credential/master snapshots in an isolated environment with all optional consumers stopped. Check referenced credentials without logging plaintext. Do not count a file-copy operation as a completed restore drill.

## Optional live smoke — explicit separate authorization only

For each permitted provider independently, document the operator, account arrangement, payer, date, data terms and provider-side controls. Enable just that provider and catalog access first, keeping paid probes off. Enter a dedicated API key only through the protected local application workflow. Refresh models and inspect actual access/capability limits.

Only after a reviewed current price and an explicit spending decision, enable the one fixed synthetic probe. Record returned model identifier, safe usage and actual billed outcome independently. Do not send real game code, scores, salaries or personal data. Disabling/rotating the key must stop new jobs. Never mark OpenAI, Anthropic or Gemini live smoke passed because another adapter or mock passed.

No live provider call, paid generation, public deployment, browser run, Docker/PowerShell startup, native concurrency, deployed role test or human acceptance was performed by this delivery.
