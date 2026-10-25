# Hypothetical simulator API

All routes are under `/api/v1/workspaces/{workspace_id}/projects/{project_id}/simulator`. Use UUIDs belonging to the current authorized project. Existing HttpOnly sessions, exact-origin/CSRF rules and current membership checks apply. Mutation methods require `X-CSRF-Token` from the authenticated session, even when POST is used for a read-only economic preview. No token belongs in a URL. Responses use the existing no-store policy.

| Method and suffix | Behavior |
|---|---|
| GET `/options` | Current scoped policy versions/readiness, `can_save`, limits and non-payable notice |
| POST `/preview` | Capture and compute, without saving a scenario or changing economic records |
| POST `/scenarios` | Explicitly save a reviewed non-payable example; HTTP 201 |
| GET `/scenarios?offset=0&limit=20` | Paginated project examples; limit 1–50, offset 0–1000 |
| GET `/scenarios/{scenario_id}` | Authorize, verify fingerprints and replay the preserved calculation |

No PATCH, DELETE, pay, approve-distribution, arbitrary-balance setter or finance-close route is introduced. Viewers can preview/read but cannot save.

## Preview request

```json
{
  "source_policy_id": "10000000-0000-4000-8000-000000000001",
  "calculation_policy_id": "10000000-0000-4000-8000-000000000001",
  "month": "2026-09",
  "amount_cents": 1000000
}
```

UUIDs above are placeholders, not a seeded project. `amount_cents` is a strict nonnegative integer at most 1,000,000,000,000; 1,000,000 cents means $10,000. Numeric strings, booleans and floats are invalid. The accounting year range is 2000–9998. The existing policy schema provides USD and calendar-month rules. Unknown request fields are rejected.

The response is a `hypothetical_simulation` record with `payable: false`, explicit notice, original input, capture instant, snapshot, snapshot hash, pure calculation input, result and result hash. Result includes engine version, hypothetical/non-payable flags, pool weights, rounding lines, recognized denominators, person totals, unallocated cents, and `calculated` or `blocked` status. The snapshot records both policies, exact month boundaries, canonical award/event source and its `ledger_revision` fingerprint, eligible awards/current attributions, exclusions, planning, dispute IDs, names and warnings.

A blocked pool is a valid hypothetical response, not an API failure. `empty_pool` and `unresolved_dispute` describe why no person allocation was made from that pool. Its cents remain unallocated. The absence of a blocker is not financial approval.

## Save request

```json
{
  "request_id": "20000000-0000-4000-8000-000000000001",
  "title": "September release versus ongoing example",
  "input": {
    "source_policy_id": "10000000-0000-4000-8000-000000000001",
    "calculation_policy_id": "10000000-0000-4000-8000-000000000001",
    "month": "2026-09",
    "amount_cents": 1000000
  },
  "reviewed_snapshot_hash": "REPLACE_WITH_THE_64_CHARACTER_HASH_FROM_PREVIEW",
  "hypothetical_confirmed": true
}
```

Use the actual UUIDs, a fresh random request UUID, a 2–120-character title and the exact SHA-256 snapshot hash returned by the preview. The placeholder string is intentionally invalid. Never send a client-supplied record/result as the source of truth. The backend recalculates and rejects changed state. A repeated identical actor/request returns the same saved row; reuse with different inputs/actor yields `idempotency_conflict`.

The saved response contains id, title, created_by, created_at, record_hash, preserved record, `reproduced: true` after verification, and a historical-example notice. Listing returns summaries and `next_offset`. A link using those IDs is not public access.

## Important failures

401: no valid session. 403: forbidden operation, including viewer save or CSRF failure. A foreign/missing project, policy or scenario is not exposed by guessing an identifier. 409 includes `stale_simulation`, `idempotency_conflict`, `ledger_integrity_error`, `planning_integrity_error`, `simulation_integrity_error`, `scenario_limit` and unsupported calculation source values. 422 includes malformed money/month, ambiguous/nonexistent accounting boundaries and scope-limit failures. Inspect the existing structured error envelope and request identifier, not raw database exceptions.

## Transaction and recovery contract

Acquire `project_access(lock=True)` before calling capture/save. The shared workspace lock serializes current writers; future integrations must honor the same protocol. A preview performs no scenario/award/event/budget writes; the authentication layer can update session activity. A save inserts the example and audit entry together. Failures roll back both. The signed ledger is read rather than repaired by this module.

Pure replay uses `app.finance.calculation.engine.distribute`. `verify_record` also checks snapshot/ledger hashes; the stored row's record hash is checked before replay. Do not update old snapshots when new awards arrive. No AI/provider is needed. Default database ownership remains the local operator profile, not verified least-privilege deployment.
