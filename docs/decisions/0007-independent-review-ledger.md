# ADR 0007 — Independent human acceptance and append-only contribution credit

Status: implemented in source, environment acceptance pending. Baseline 0.5.0-phase5. Source 0.6.0-phase6. Date September 13, 2026 (America/Puerto_Rico).

## Decision

The accounting unit is an independently budgeted deliverable, not a PR, upload, review vote or AI assessment. Human review is bound to the exact latest submitted scope, policy identity/content, resolved attribution, allocation planning version and evidence snapshot. The assigned independent quorum is the approved policy's number (1–3). Each reviewer records criterion-by-criterion findings with bounded explanations and references. All must accept. A separate, explicitly confirmed finalization posts the award in one transaction. The new tables are review_rounds, review_assignments, review_decisions, credit_awards, contribution_events, contribution_balances, credit_disputes, dispute_assignments, dispute_notes, dispute_resolutions and participant_notifications.

The finalizer is an assigned independent reviewer, not a beneficiary-admin acting alone. Exclude every positive recipient in the package and the submission author from the acceptance quorum. Application checks cannot establish undisclosed real-world conflicts or prevent one human controlling several accounts. Do not market account-role checks as proof of independence. Current permissions and policy readiness are checked at assignment, vote and finalization. A new round explicitly supersedes unfinished decisions, never an award.

Assignment/vote/finalization commands use UUID idempotency identifiers bound to actor and input. Ledger uniqueness additionally prevents a second award for a deliverable even using another request ID. All scoped mutations acquire workspace, then milestone, then package locks. The pilot serializes workspace mutations conservatively rather than promising maximum write throughput. PostgreSQL native race tests are supplied but have not been executed here. SQLite tests cannot establish PostgreSQL concurrency guarantees.

## Accounting

An award preserves its original recipients and accepted integer-atom budget. Positive initial event lines sum to that budget. Corrective event lines net to zero; per-recipient balances cannot become negative. Display views derive from preserved events; mutable balances and parent issued totals are repairable projections, not the accounting source. A checked operator command rebuilds projections, never events. Exact units use 1,000 atoms per unit; no binary floating-point balance arithmetic.

A credit posting advances milestone credit totals/version, but not the allocation's planning version. Otherwise accepting one portion would falsely invalidate unchanged remaining deliverables. Any genuine new evidence/resubmission stales unfinished rounds. After partial acceptance, scope/attribution and cancellation remain conservatively frozen. New evidence and explicit resubmission for remaining portions are permitted after validating actual issued awards. Fully accepted scope becomes completed. Historical evidence-free phase-4 submissions are never backfilled.

## Disputes

A nonviewer participant may file a specific concern against a finalized award. Before acceptance, use review requests for evidence or changes. One active dispute per award avoids parallel contradictory outcomes. Immutable notes (plaintext and optional HTTPS labels, not fetched) capture supplementary claims. Notes are project-visible; restricted file contents must not be pasted into them.

An administrator assigns a current independent resolver who is not a beneficiary, complainant, original acceptance reviewer or reviewer of a prior finalized resolution for this award. The resolver proposes uphold or exact-budget reallocation. The original policy's quorum applies; the resolver is part of that quorum and alone can finalize the approved resolution. Proposed recipients cannot be reviewers. New notes, reassignment, balance changes or loss of current authority stale unfinished proposals. Original award references, decisions and source snapshots remain unchanged. Open disputes expose a pool-specific close blocker and the mandatory future-finance helper require_clear_pool. No actual close route exists before phase 13.

Corrections may reassign existing units; total-award rescission, damages, negative entitlements, equity transfers, post-payment recovery and partial-scope cancellation are deliberately not implemented. Such extensions need separate budget/finance policy and immutable event designs, not an administrator's arbitrary balance edit.

## Database privilege boundary

Migration 0006 guards ten immutable tables against ordinary UPDATE/DELETE, and PostgreSQL TRUNCATE, and revokes PUBLIC writes. A unique scoped submission index supports exact foreign keys without editing migration 0004. Optional infra/ledger-privileges.sql grants narrowly scoped capabilities to pre-created nonowner roles; it is not run automatically. Default local Compose still uses an operator-owned DSN. Owners/superusers can bypass ordinary safeguards, so native least-privilege deployment acceptance remains open. The script covers new tables only, not every earlier API table. A future AI worker gets no credit-writer role, secret backend access or arbitrary SQL capability. Its complete evidence-only access will be provisioned when that worker exists.

## References checked in this development phase

PostgreSQL explicit locking: https://www.postgresql.org/docs/current/explicit-locking.html
PostgreSQL privileges: https://www.postgresql.org/docs/current/ddl-priv.html
SQLAlchemy session transaction basics: https://docs.sqlalchemy.org/en/20/orm/session_basics.html

These explain mechanisms, not a certification of this application. Exact dependencies and base images are unchanged from phase 5 apart from the source version. Existing install/React/native/Windows/S3/backup/security/user gates remain open.
