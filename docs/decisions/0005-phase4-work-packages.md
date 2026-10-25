# ADR 0005 — Work packages and immutable scope

Date: September 13, 2026. Status: implemented in phase-4 source; runtime acceptance remains open. Baseline: ADR 0004 and the actual phase-3 archive. No dependency upgrade or new external service.

## Decision

One work package binds permanently to one approved, positive milestone allocation, with inherited project, policy, category and pool. A unique constraint prevents double binding. A cancelled package still owns its historical binding; subsequent work requires another approved allocation. Package creation consumes no additional milestone budget.

Use a mutable `work_packages` projection plus append-only scope revisions, per-revision participant references, events and submission snapshots. The allocation and milestone remain authoritative for approved planning capacity. Four history tables reject ordinary UPDATE/DELETE, and package deletion or rebinding is prohibited by database triggers. These are application/ordinary-DML protections, not protection against a database superuser or stolen operator access.

Each revision stores a bounded JSON document with independently identifiable deliverables, acceptance criteria, evidence requirements, original attribution proposals, resolved integer amounts, and named participant snapshots. Participant references use scoped foreign keys. A deliverable identity is scoped to `(package_id, scope_revision, deliverable_id)`, not a globally authorized record: later evidence/review code must resolve it through its immutable parent revision. There is no SQL table for each nested attribution row at this stage. Do not infer cross-project access from a nested UUID.

## Precise planning attribution

One unit is 1,000 integer atoms; API amounts remain integers. Direct unit proposals must not exceed their deliverable. Percentage proposals use integer basis points (10,000 = 100%), with largest-remainder rounding over each person/role **and an explicit unassigned bucket**. Ties use UUID + role lexicographic order, with the unassigned bucket last. Input ordering never changes the result. Preserve source percentages as well as resolved atoms. An incomplete percentage proposal remains incomplete even when its unassigned bucket rounds to zero atoms. Very small complete allocations can legitimately give a person zero atoms; show the result rather than inventing value.

Drafts may have no deliverables, an unplanned parent remainder, or incomplete attribution. They must still describe a useful outcome, criteria, evidence requirements and eligible intended participants. Scope approval, start and submission require the entire parent budget split among deliverables, every deliverable fully attributed, eligible active participants, and the approved/effective/acknowledged pinned policy. This is not a completion percentage or compensation formula. No work-hour or complexity score is stored.

## Permissions and workflow

Administrators and contributors may create packages. Only an administrator or the current assigned coordinator may amend/start/submit/withdraw a package. An explicitly assigned coordinator may hold another active non-viewer project role, but an unrelated contributor or reviewer cannot edit that scope. Administrators approve planning scope and cancel; administrators and project reviewers can request changes to a submitted package. These rules never grant independent acceptance of one's own contribution credit.

States: draft → budget_approved → in_progress → submitted. A reviewer/administrator can request changes; a coordinator/administrator can withdraw. Both paths preserve the submission and require a new revision and fresh scope approval. An amendment to approved or in-progress work returns it to draft and clears approval. `completed` is reserved for phase 6's independent acceptance workflow: there is deliberately no phase-4 completion/award endpoint. No phase-4 action accepts evidence.

Submission archives the exact scope, attribution, policy fingerprint, parent budget/version, author and note. `evidence_status=not_collected_phase4` and a null evidence snapshot identify a readiness declaration, not verified work. Phase 5 must create real evidence snapshots; phase 6 must bind approvals to those snapshots. Do not backfill old declarations to claim evidence existed earlier.

## Budget interoperability

All business commands use existing scoped authorization and workspace → milestone → package lock order, then optimistic version/hash validation. The workspace lock also keeps current roster/policy reads coherent. The review fingerprint includes the current milestone/allocation versions, so even another planning amendment can require a fresh review.

Older budget routes now inspect linked packages both at proposal time **and decision time**. An unapproved draft can be resized only to at least its child-budget total. Successful resize appends a new scope revision and `budget_rebound` event recording the new parent amount; older snapshots remain unchanged. Approved/in-progress/submitted scopes cannot be silently resized. First make the appropriate scope amendment (withdraw if submitted), then use the existing budget amendment process, then approve the resulting scope again.

Cancellation is a confirmed administrative transaction: record and approve the linked budget cancellation, set the package cancelled, append history. Only unissued capacity is released; protected reserve and history remain. Any nonzero issued projection blocks the whole phase-4 command rather than guessing a partial-credit reversal. Future partial cancellation/adjustments require phase-6 ledger rules. Terminal packages are not reopened or deleted. Ordinary external budget cancellation of a linked package is denied.

## Pilot bounds and tradeoffs

Up to 200 packages per project, 30 deliverables per revision, 30 attribution rows per deliverable, 50 intended contributors, 500 revisions and 2,000 events per package. API request limit is 65,536 bytes; browser commands warn at 64,000 UTF-8 bytes. These bounds are ceilings, not a guarantee that a maximal document fits. Shorten/restructure scope without increasing its total budget. Lists are paginated; options report truncation beyond 1,000 allocations. History shows 20 events per page; older submissions remain reachable from their events.

Small bounded lists currently read snapshot documents under workspace locks. This is intentionally simple for a local team, not a high-throughput design. Index/search/materialized projection improvements require future measured need, not a premature service split.

## Verification boundary

SQLite application tests exercise real command routing, migrations, constraints and triggers. Five new native PostgreSQL tests cover competing binds, edits, submissions, cancellation and upgrade/immutability; their execution requires the disposable PostgreSQL fixture. Browser acceptance source covers a three-deliverable flow but must run against a built UI. See `docs/test_results.json` for what actually executed. These tests do not constitute a security audit or completed human acceptance.
