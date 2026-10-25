# ADR 0016 — Offline evaluation and a source test candidate

Date: September 14, 2026. Baseline: the actual 0.14.0-phase14 archive. Decision: implement remaining self-contained evaluation/handoff work and defer real participants/accounts until testing, as requested by the owner.

## Separation of completion states

Do not block useful release preparation on a fictitious human pilot, and do not label it completed. Source implementation, a successful local installation, native concurrency/permissions, real browser operation, model quality, and real-use approval remain different states. The designation is **0.16.0-phase16, internal source test candidate**, not a verified runnable release.

P15C provides a private blank observation schema and descriptive summarizer. P16 supplies guided setup and release/maintenance tooling before that human stage occurs. This changes delivery order only; it does not bypass staging or real-use gates.

## Evaluation design

Use the application's existing prompt, no-network mock provider and assessment validator. Supply 24 synthetic scenario families with seven controlled variants each, separate families between calibration and holdout, and freeze provisional thresholds. Randomize/rotate criterion IDs and ordering across families to avoid an obvious label shortcut. Keep synthetic ambiguity separate from claimed human disagreement.

Do not add a raw paid-evaluation endpoint that bypasses existing packet disclosure and payer approvals. The offline scorer accepts bounded outputs, exact packet/prompt/profile fingerprints, explicit failures and unknown usage. Its reports do not contain raw model prose. Missing predictions remain in coverage denominators. A valid citation is not proof of a true interpretation. Correlated variants are not independent real cases.

The mock always answers insufficient. The calibration run demonstrates protocol and harness behavior, not model accuracy. Holdout structure can be checked explicitly, but no scored holdout result is included. No live provider was called.

## Product finishing and operations

Add a read-only Getting started guide for manual and historical paths, accurate pending-human roadmap labels and current overview text. Preserve all account/credit/evidence/finance guards. New Windows wrappers delegate to existing startup/test scripts; they do not reset data or launch public services.

Correct the API test image to keep the monorepo at `/repo`, with `/repo/apps/api` as its test working directory. Newer operator tests resolve scripts from the repository root and could not load under the inherited flat `/app` layout. Extra test source stays out of the runtime stage.

No migration after 0014 or new third-party dependency version is required. The existing locks/images remain unverified installation candidates; source-version/image labels change only. The manifest verifies listed source bytes, not an operator's trustworthiness or deployment readiness.

## Deferred verification

Actual downloaded build, Windows/Compose execution, native PostgreSQL grants/concurrency, built browser flows, native restoration, authorized live integrations, independent reference labels, security/load review and two real shadow periods remain open. Do not promise readiness merely because many unit tests passed.
