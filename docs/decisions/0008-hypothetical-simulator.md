# ADR 0008 — Hypothetical distributions with captured ledger inputs

Date: September 13, 2026. Status: implemented in source, environment acceptance open.
Supersedes no applied migration or existing credit policy. Extends ADR 0007.

## Scope and economic boundary

Phase 7 adds a pure calculation engine, a protected what-if interface and explicitly saved non-payable examples. It does not create financial receipts, amounts owed, payment instructions, release-share freezes, tax records, ownership, or additional credit. The hypothetical USD input is an assumed distributable amount after any external deductions. No expenses are automatically deducted. The examples must never be migrated into phase-13 approved closes merely because a row exists.

The first useful manual workflow is now implemented in source: budget → scope → evidence → independent review → accepted units → hypothetical distribution. Full-stack acceptance remains unverified, and the team has deferred user testing. GitHub and AI are deliberately unnecessary.

## Explicit source policy and calculation policy

One source policy supplies immutable awards across all of its milestones. Other policy versions are counted as excluded rather than silently combined. One calculation policy supplies pool keys, weights and accounting timezone. By default the user chooses the same policy; selecting a draft successor allows a what-if comparison without moving awards, activating the draft, reapplying its review/category rules, or treating acknowledgement as complete. The UI shows both versions, states and their fingerprints.

Release credit is cumulative for original acceptance instants before the selected month's exclusive end and no later than capture time. Ongoing credit is limited to original acceptance instants in that local calendar month, start-inclusive/end-exclusive. The month is interpreted in the calculation policy's IANA timezone. Ambiguous or nonexistent month-boundary midnights are rejected; there is no guessed offset. Future months contain only already accepted work, not a prediction.

An attribution correction belongs to the original award, not to the month in which the correction was approved. Current corrected attribution is used for a newly calculated past-month example. Therefore it is explicitly not a reconstruction of what participants knew or were owed in that past month. Saved examples preserve the earlier view. Calendar-month operation is the existing initial policy scope; arbitrary windows, expiring credit, cross-policy consolidation and permanent release freezes are outside this phase.

## Exact arithmetic and bounds

Money is integer USD cents; contribution amounts remain integer atoms, 1 unit = 1,000 atoms. Reject booleans, numeric strings, binary floats, negatives and amounts above 1,000,000,000,000 cents ($10,000,000,000.00). Frontend input converts decimal strings with BigInt before sending a bounded safe JSON integer. No currency conversion or implicit unit conversion occurs.

The pure engine `app.finance.calculation.engine` applies largest-remainder allocation twice: first among policy pools using basis-point weights totaling 10,000, then among eligible contributors separately within each pool using recognized atoms. Compute integer floor and remainder; distribute leftover cents by descending remainder then ascending stable ASCII pool key or contributor UUID. Display names and input ordering never determine a tie. Preserve the floor, numerator, denominator and optional extra cent for every line. Zero-weight contributors receive no cents. The sum of person amounts plus explicitly unallocated pool amounts equals the hypothetical input exactly.

Largest-remainder allocation can be non-monotone: increasing a total or changing weights can cause a small recipient amount to drop because the leftover-cent ordering changes. An explicit regression test preserves this behavior rather than promising impossible smoothness. The implementation does not claim this convention is the uniquely fair method. A future convention change needs a new version and must preserve replay of archived `largest-remainder-v1` examples.

## Blockers and pending work

An empty pool is explicitly blocked even for a zero-dollar input. An unresolved dispute on an eligible award blocks the affected pool. Other pools may show partial hypothetical amounts, but the overall example is marked blocked. Blocked cents remain unallocated; there is no renormalization to other pools and no owner fallback. A dispute outside the chosen award/date scope is not silently reclassified as resolved. The phase-6 `require_clear_pool` guard remains mandatory for eventual financial closes; a phase-7 preview is not permission to bypass it.

Only finalized awards contribute to denominators. Pending allocations, unissued reserve, inactive proposals and evidence activity do not earn credit. Planning totals are current and not month-filtered, which is stated separately. Departed/suspended contributors' historical credit remains included. Balances are reconstructed from signed events, not from mutable projection caches. Negative per-role attribution or a sum inconsistent with an original award blocks calculation.

## Stable capture and concurrent writes

Routes acquire current project access with the existing workspace lock before capture. Existing credit, policy, planning and membership writers use that same tenant lock. This serializes capture against current mutators even with PostgreSQL READ COMMITTED statement snapshots; it is not a claim that unrelated SELECTs are inherently repeatable. Future writers must preserve the lock protocol or introduce an explicit versioned snapshot transaction and corresponding races. Direct database-operator writes are outside this guarantee. SQLite behavior is tested, but real PostgreSQL locking/races are still unexecuted.

Capture includes source award/event rows, current attribution, original acceptance dates, both policy versions, period boundaries, planning, known exclusions and current dispute IDs. The ledger revision is a SHA-256 fingerprint of canonical original award/event content, not an editable sequential counter. Snapshot hash includes the inputs and current captured state, excluding the wall-clock capture label. Save recalculates under the lock and refuses changed state; it does not silently accept a stale preview. Request identifiers are actor-bound and idempotent. A repeated identical save returns the original example, not a fresh statement.

Current SQL transaction references used during implementation:
- PostgreSQL transaction isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- SQLAlchemy session transaction management: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
These inform locking/transaction choices, not claims of completed native verification.

## Saved examples and permissions

Migration `0007_hypothetical_simulator` adds only `simulation_scenarios`. Earlier migrations 0001–0006 are unchanged. No seed, backfill, automatic saving or financial state transition runs on startup. The table rejects ordinary UPDATE/DELETE, and PostgreSQL additionally rejects TRUNCATE. Nonempty downgrade is refused.

Every currently authorized project role may calculate and read project-visible examples. Viewers cannot save them. Every route resolves workspace and project scope on the server; links contain only identifiers and never grant access by possession. Current access checks and no-store responses apply to historical examples too. The recorded source is contribution/policy/planning information already project-visible; private artifact bytes and restricted review findings are not copied into this module. Revocation cannot erase a copy already received by an authorized person.

Saved examples store input, ledger snapshot, engine input/output, engine version, capture label and fingerprints. On read, validate record/snapshot fingerprints and rerun the pure engine from the archived calculation inputs. Do not call AI, query current economic totals, or replace the archived result. Fingerprints detect inconsistency, not a privileged operator who replaces content and all corresponding hashes; they are not external notarization or tamper-proof infrastructure.

Bounds fail explicitly: 200 policies in options, 2,000 original awards and milestones per source policy, 20,000 signed events, 10,000 planning allocations, 10,000 engine recipients, and 1,000 saved examples per project. Lists paginate. No archive deletion UI exists; do not remove history to work around limits. These small-team bounds can later be expanded with performance tests rather than silent truncation.

## Acceptance evidence and future work

The canonical corpus has 25 fictional fixtures, plus deterministic seeded arithmetic properties, API authorization/staleness tests and a real application-command five-person workflow covering non-code image/research evidence. Native PostgreSQL and actual browser sources are supplied but not automatically considered passed. Results are in `docs/test_results.json`.

Phase 8 starts GitHub evidence import. Imported activity must not issue units or alter historical scenarios. Phase 13 reuses the pure engine, but needs separately approved accounting records, broader close guards, permanent release scope and independent financial finalization; it cannot relabel saved examples as paid.
