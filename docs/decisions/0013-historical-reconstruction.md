# ADR 0013 — Historical reconstruction without a second credit path

**Date:** September 14, 2026. **State:** Implemented in source, native/runtime/user validation open.

## Decision

A retrospective batch owns one dedicated, already-approved milestone with no preexisting allocations or awards. The batch's immutable definition records the historical interval, current retrospective agreement reference and initial budget. An administrator approves the exact policy/budget/contribution baseline. This is an agreement recorded now, not an assertion that it existed during the historical interval.

Imported objects become candidate outcome groupings, not accepted packages or credit. Structured captured relationships link pull requests, issues, commits, reviews, comments and checks where available. No text instructions are followed and no provider, code execution, URL fetch or new GitHub request is involved. Model-generated grouping is deliberately not added: current deterministic grouping is inspectable, and phase-11 AI remains available only through its approved evidence-review path. No universal unit estimate is generated.

A primary source-entity claim uses numeric GitHub repository ID, source kind and remote key. It is unique within the local project across import versions and reconnections. Claims remain after rejection and can be moved between draft candidates only within their batch. Re-importing an entity does not produce more candidate credit. This is conservative duplicate handling, not semantic fraud detection: different entities, manual descriptions or paraphrased copies may still describe overlapping work. Some genuine shared-context uses are blocked and require explicitly redesigning the group before promotion; there is no silent override.

## Existing accounting is reused

A candidate is converted only after explicit source/identity review, removal of unresolved questions, current policy readiness, an approved matching-category allocation, full scope attribution, and explicit project-evidence disclosure confirmation. Scope, package, evidence and independent finalization services are reused. Promotion creates an ordinary draft package and pins source versions; it does not approve the package, accept work or award units. Even administrators cannot self-approve their own credit through this route.

Awards take effect through the existing per-deliverable finalization. The later opening-balance archive captures those recognized awards and their current attribution. It does not atomically issue a new balance, backdate acceptance, create payments, or establish phase-13 permanent release shares. During review, current contribution ratios may change as further work is accepted.

The archive requires resolved candidate dispositions, completed linked packages, addressed missing-work claims, no unaccepted allocated capacity, current policy acknowledgements and no open disputes in affected policy/pools. Protected/unissued reserve remains unowned. Before/after shares retain explicit numerators and denominators. Baseline-to-current changes can include other work and corrections outside this batch; batch-specific units are displayed separately.

A frozen batch cannot acquire new candidates, change claims or grow its milestone. Additional historical work uses a new explicit milestone; corrections to already accepted credit use existing disputes. A snapshot preserves its original record while current ledger attribution may change through those corrections. It is an accounting archive, not the last word on historical truth.

## Missing work and projection history

Current non-viewer members can submit missing-work claims. Original claim text is immutable; the author and authorized administrators/reviewers can see it. Administrative inclusion/decline decisions may be explicitly revised before archival, preserving the prior disposition in the event chain. This prevents a mistaken early inclusion or later regrouping from permanently stranding a batch. No original claim is deleted.

Reconstruction command history and opening snapshots reject ordinary database updates/deletes. Mutable candidate/batch/claim projections preserve identity fields. Commands have request IDs, expected versions and reviewed fingerprints. Every mutation uses current workspace authorization and the established workspace → milestone → batch lock order. Actual native PostgreSQL concurrency and least-privilege provisioning remain untested here; SQLite cannot prove those properties.

## Reporting

The overview groups finalized event-derived credit by policy and pool. Category and prospective/retrospective filters explicitly narrow denominators; a person filter only limits rows. Names are displayed alphabetically. Non-code work has the same accepted-credit representation. Pending budgets are separate from issued units. Snapshot counts are not evidence sufficiency scores. Raw activity statistics remain administrator/reviewer-only and have a separate whole-project retained-source scope; they are not effort or value.

## Bounds and tradeoffs

Local pilot limits: 100 batches/project, 200 candidate records/batch (including superseded ones), 200 missing claims/batch, 2,000 commands/batch, 500 imported observation rows per grouping call, 30 source records per promoted package, 6,000 awards per policy/report, and 20,000 retained source versions for activity counting. Reaching a limit produces an explicit error or unavailable count, never a silently complete claim. Source read selection covers the latest 100 completed historical imports. JSON commands remain bounded at 64 KB.

Sources unavailable to the importer, other branches, missing binary contents and off-platform work are not reconstructed automatically. Current origin labels are presentation metadata, not inserted retroactively into existing hashed submissions. Historical credit uses its actual acceptance timestamp in the phase-7 simulator; no revenue history is fabricated.

No new third-party dependency version, external service, paid request, deployment exposure or secret volume is introduced. Existing AI initialization now checks the current application migration head rather than hardcoding phase 11; its reconstruction privileges remain excluded. System phase metadata is derived from the source release version.
