# Phase 12 API

Base: `/api/v1/workspaces/{workspace_id}/projects/{project_id}`. Existing authenticated sessions, exact-origin/CSRF rules, current project permissions and bounded JSON requests apply. Unknown cross-project IDs return no private records. Source inputs never become executable instructions.

## Historical reconstruction

Under `/reconstruction`:

| Method and route | Authority | Effect |
|---|---|---|
| GET empty suffix | Member | Public batch definitions and capabilities |
| GET `/options` | Admin/reviewer | Eligible dedicated milestones and bounded completed historical import selector |
| POST empty suffix | Admin | Create immutable historical definition; request_id deduplicated |
| GET `/{batch}` | Member | Public definition, own claims; privileged candidate/approval details for admin/reviewer |
| GET `/{batch}/history?offset=0` | Admin/reviewer | Twenty preserved commands, exact next_offset |
| POST `/{batch}/approve-scope` | Admin | Approve reviewed policy/budget/credit baseline |
| POST `/{batch}/group-import` | Admin | Group previously captured history, not fetch or award |
| POST `/{batch}/candidates` | Admin | Add a manual outcome candidate |
| POST `/{batch}/candidates/{id}/revisions` | Admin | Preserve a reasoned draft revision |
| POST `/{batch}/candidates/{id}/disposition` | Admin | Reject/restore eligible draft or reject a cancelled unaccepted linked package |
| POST `/{batch}/regroup` | Admin | Merge draft candidates or split a proper source subset |
| POST `/{batch}/promote` | Admin | Reuse a reviewed allocation and normal package/evidence services |
| POST `/{batch}/missing-claims` | Non-viewer member | Record immutable original missing-work statement |
| POST `/{batch}/resolve-claim` | Admin | Include/decline, or explicitly revise disposition before archival |
| GET `/{batch}/opening-preview` | Admin/reviewer | Current preserved-input candidate; no credit write |
| POST `/{batch}/freeze` | Admin | Archive current independently accepted balance once |

Most commands require `{request_id, expected_version, reason}`. Scope approval, promotion and freeze additionally require `reviewed: true` and the returned `reviewed_hash`. Promotion carries `candidate_id`, `allocation_id`, `expected_allocation_version`, normal `scope` and `project_sharing_confirmed: true`.

Batch creation carries `milestone_id`, `title`, offset-aware `start_at` and `end_before`, `historical_scope`, `agreement_reference`, and `reason`. The interval is half-open and historical. Missing claims have `{request_id,title,category,description}` without an expected-version requirement; they deliberately invalidate any older balance preview. Other concurrent changes use version checks.

Candidate documents contain title/category/summary, unresolved_questions and explicit identity_resolutions. Each resolution uses external_key, `participant` plus user_id or `context_only` without a user_id, and a human reason. The server validates against the pinned source identities and active participants. Group provenance is preserved separately and cannot be supplied as arbitrary replacement history.

Idempotent repeat commands return their original `result` alongside the currently authorized batch state. Reusing a request ID for a different body, actor-scoped batch command, or operation conflicts. Rejected, stale or failed transactions issue no units. Promoting twice cannot bind another package, budget or source version.

## Reporting

`GET /reports/overview` accepts `policy_id`, `pool_key`, `category`, `origin` (`prospective`/`retrospective`) and `person_id`. It groups exact event-derived units by policy and pool; category/origin narrow the denominator, person only filters displayed rows. The report includes applied filters, denominator label, capture instant, fingerprint, current award IDs, category/origin totals, affected disputed units and pending planned allocations. Names are alphabetic; no global score is created.

Admin/reviewer activity counts have their own whole-project retained-source scope. A scan above 20,000 source versions returns unavailable rather than partial counts pretending to be complete. Human evidence snapshot counts are not AI sufficiency judgments. No request sends data to a provider, imports source from GitHub, creates finance obligations or alters existing ledger awards.
