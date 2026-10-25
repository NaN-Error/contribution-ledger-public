# Phase-3 policy and budget API

All routes use the same scoped accounts/session protocol from `auth_api.md`: a current session, exact allowed browser Origin, JSON for writes, and current `X-CSRF-Token`. The browser helper does not automatically retry writes. A 409 requires refreshing and human review, not blind replay. No endpoint accepts a caller-supplied approver or acknowledgement actor.

Base: `/api/v1/workspaces/{workspace_id}/projects/{project_id}`. IDs must come from authorized application responses. A missing/inaccessible scoped resource is not a way to enumerate another workspace.

## Policies

| Method and suffix | Permission | Behavior |
|---|---|---|
| GET `/policies/templates` | Project read | Two unsaved example rule documents |
| GET `/policies` | Project read | Versions latest first, latest version, current candidate |
| POST `/policies` | Project manage | Save a new immutable version and participant snapshot |
| GET `/policies/{policy_id}` | Project read | Exact document, approval and acknowledgement state |
| POST `/policies/{policy_id}/approve` | Project manage | Approve latest reviewed version prospectively |
| POST `/policies/{policy_id}/acknowledge` | Project read | Record signed-in actor's own review only |

Create fields: `expected_latest_version` (0 initially), `title`, complete `rules`, `agreement_reference`, `reason`. Copy a permitted template or current document, intentionally review/edit it, then submit the complete schema. No field is a secret connection or actual legal signature. See `app/policies/schemas.py` for the exact strict schema.

Supported rules: schema 1, USD, matching project IANA timezone, unit scale 1000; unique eligible category names; 1–3 independent reviewers, beneficiary-cannot-approve-alone=true and budgeted-deliverable acceptance; explicit project-admin governance and acknowledgement scope; one release pool or release/ongoing with positive integer basis points totaling 10000; monthly day-1 midnight accounting with rejection of ambiguous/nonexistent local boundaries; explicit revenue basis, nonduplicate permitted deductions and meaningful accounting/attribution/departure text. Platform fees cannot be deducted again from net storefront receipts. Unknown fields fail validation.

Approval body:

```json
{
  "expected_latest_version": 1,
  "reviewed_content_hash": "<copy the exact returned SHA-256 fingerprint>",
  "examples_reviewed": true,
  "effective_at": null,
  "reason": "Reviewed the complete synthetic policy and participant list"
}
```

The angle-bracket hash above is an instruction placeholder, not a valid fingerprint. `null` means immediate approval. For scheduled approval supply an offset-aware ISO instant with seconds; Unix numeric timestamps and inferred local times are rejected. Review confirmations require JSON `true`, not 1 or a string. Approval history cannot be updated or deleted through the API.

Acknowledgement body: `reviewed_content_hash` and `reviewed: true`. The actor comes from the session. A successful exact replay is idempotent. A draft cannot be acknowledged before administrative approval.

Response readiness flags are distinct: `is_latest_revision`, `is_current_candidate`, `ready_for_pinned_work`, `usable_for_new_milestones`. `my_acknowledgement` is a boolean. `acknowledgements` includes required participants, missing IDs and a complete flag. A draft successor need not be the current effective policy.

## Milestones

| Method and suffix | Permission | Behavior |
|---|---|---|
| GET `/milestones` | Project read | Approved totals and statuses |
| POST `/milestones` | Project manage | Zero-budget draft plus immutable initial-budget proposal |
| GET `/milestones/{id}` | Project read | Allocations, pinned policy and first 20 history rows |
| POST `/milestones/{id}/preview` | Project manage | Pure proposed before/after result; no writes |
| POST `/milestones/{id}/amendments` | Project manage | Store a pending proposal; no approved-total change |
| POST `/milestones/{id}/amendments/{proposal_id}/decision` | Project manage | Approve/reject exact stored preview under current revision |

History query: `?history_offset=0`; follow `next_history_offset` until null. New decisions can change page positions; refresh returns to the newest page. Amount projections and historical previews have integer atoms and exact scoped ratios.

Creation fields: `name`, optional `description`, `policy_id`, positive integer `total_atoms`, nonnegative integer `reserve_floor_atoms`, `reason`. Example: 1,000 units and a 100-unit reserve become `total_atoms: 1000000, reserve_floor_atoms: 100000`.

Preview and proposal body:

```json
{
  "expected_version": 2,
  "change": {
    "kind": "allocate",
    "title": "Implement multiplayer reconnection",
    "category": "code",
    "pool_key": "release",
    "atoms": 700000
  },
  "reason": "Budget this synthetic outcome before work begins"
}
```

The expected revision must come from the current milestone; the number above is illustrative. Preview returns `preview` and `preview_hash`. A proposal recomputes them server-side rather than trusting a client-provided snapshot.

Other change shapes:

- `initial_budget` or `set_budget`: `total_atoms`, `reserve_floor_atoms`.
- `resize_allocation`: `allocation_id`, positive `atoms`.
- `cancel_allocation`: `allocation_id` only; permitted only for no-issued allocation.

Decision fields: `decision` (`approve`/`reject`), `expected_version`, `reviewed_preview_hash`, `reason`. The hash must be copied from the stored proposal. A preview uses the literal temporary allocation ID `proposed` for a new row; after approval its persistent ID is the proposal UUID. This substitution does not award personal credit. History preserves the reviewed placeholder and the actual proposal identifier.

Approval checks the exact current snapshot against the stored fingerprint inside the transaction. A stale proposal cannot be approved. A rejection may close a stale proposal after refreshing the milestone revision; it never changes totals. Repeated decisions return 409. Do not auto-retry after an unknown network outcome: reload the history first.

## Validation, locking and limits

Atom fields are integer JSON numbers up to 1,000,000,000,000; not floats, strings or booleans. There is no `issued_atoms`, personal percentage, beneficiary or payment parameter in budget commands. Unknown fields are rejected. Issued projections are future-ledger integration points, not exposed award controls.

Writes and coherent reads acquire the existing workspace lock; budget decisions then acquire the milestone lock in the same order. Database constraints enforce nonnegative amounts, assigned plus protected reserve within total, and issued within allocation. PostgreSQL race behavior still needs native verification; SQLite tests do not establish it. History tables reject ordinary updates/deletes in the database. Operator/superuser tampering is outside that guarantee and must be addressed by later deployment privileges and backups.

Typical errors: 401 signed out, 403 insufficient role/CSRF, 404 inaccessible scope, 409 stale version/duplicate decision/missing acknowledgements/overspend/limit, 422 invalid fields or retroactive policy time. Error envelopes are sanitized as `{ "error": { "code", "message", "request_id" } }`; validation does not echo submitted policy or credential data. Current limits: 200 policy versions and 200 milestones per project, 500 proposals per milestone. There is no financial close, payout or credit issuance endpoint in phase 3.
