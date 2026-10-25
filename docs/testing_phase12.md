# Phase 12 verification guide

Actual executed counts and boundaries are recorded in `test_results.json` and `verification/phase12_*`. The following commands and human checks are not themselves evidence that they ran.

## Automated source tests

```powershell
# From apps/api with the locked development environment installed:
python -m pytest -q
# Optional native PostgreSQL cases require an explicitly configured disposable *_test DB:
python -m pytest -q -m postgres
# From apps/web:
npm ci
npm test
npm run build
```

The API suite includes deterministic captured-source grouping, numeric repository deduplication, explicit identity validation, strict scopes, manual artwork, source-pinned promotion, ordinary independent awards, missing-work disputes, stale/repeated commands, conservative cancellation, history guards, before/after denominators and origin filters. New native cases exercise simultaneous creation, duplicate commands, archive races, scoped FKs and mutation/truncate rejection; SQLite is not a concurrency substitute.

Frontend helper tests validate explicit UTC boundaries, exact displayed fractions, zero denominators, person filters, encoded query fields, UTF-8 request bounds, identity dispositions, promotion review and source-sharing requirements. They do not render React. Syntax transpilation is also not a semantic build.

## Deferred local acceptance

Use two isolated synthetic projects, one administrator, at least one independent reviewer, a contributor and a viewer. Never use synthetic second accounts as proof of real-world review independence.

Create a dedicated 1,000-unit approved historical milestone with 100 reserve. Define a past UTC interval and current agreement reference. Confirm no allocation or earned credit is created automatically. Attempt to use the same milestone twice and another project's milestone: both must be rejected.

Group an authorized small historical import twice; the second command must preserve zero new primary source claims. Inspect binary/truncated omissions. Review a co-author and a reviewer separately; unknown identity claims must block promotion until explicitly resolved. Split a group, merge two groups, reject an irrelevant candidate, and inspect the retained parent history. None creates a budget.

Have the contributor submit omitted artwork. The viewer must not submit it or inspect the private review queue; the author must see their own claim. Include the claim through a manual art candidate, record a revised disposition and verify the prior reason is retained. An unresolved claim or a claim linked to superseded/unaccepted work must block archival.

Allocate units in Milestones. The normal prospective package selector must not offer those reserved allocations. Refresh the historical batch, inspect source contents and confirm their disclosure, then complete the reused scope/attribution form. Check that promotion creates only a draft package and pins the exact observed source versions. A repeated request cannot produce another package. Work that later earns credit must resist candidate rejection/cancellation.

Use protected evidence and Human reviews to accept an art deliverable. Verify independent quorum and beneficiary conflicts, original acceptance time, additive ledger events and retained review history. Current accepted shares can change before the full historical batch is archived; pending budgets and unreviewed work are not final revenue rights.

Inspect Opening balance: baseline/current denominators, separate batch-specific units, other intervening awards, missing-work dispositions and disputes. Leave one candidate undecided or allocation unused and verify the blocker. Open a dispute in an affected policy/pool and verify archival fails. After resolving issues, archive once and repeat the exact command; no extra credit or snapshot should appear. Try changing budget or adding a missing claim afterward; use a new scope or existing-award dispute instead.

In Contribution overview, select art and retrospective origin. Inspect the changed denominator label. Select a single contributor without narrowing their denominator. Check a departed contributor's preserved units and whole-project activity's distinct scope. Raw imported content remains admin/reviewer-only. Test loading, retry, keyboard navigation, viewport 390px and stale tabs throughout.

## Prepared browser inspection

`tests/e2e/reconstruction_smoke.py` is an opt-in Playwright inspection against an already prepared synthetic local *_test deployment. It checks the historical and overview screens on desktop/mobile and asserts read-only inspection does not change credit. See its header for environment variables. No screenshots, browser traces, credentials or packet contents are saved. It was not executed here unless explicitly reported in the release results.

## Inherited gates

Clean downloads/build; Docker/PowerShell; real PostgreSQL migration/locks/roles; current GitHub permissions; provider data/key/billing arrangements; deployed workers/broker/HTTPS; live S3; security/load; backups/restore; evaluator quality; and the user's deferred thorough testing remain separate. Mock success does not close those gates.
