# Phase 13 API contract

Base: `/api/v1/workspaces/{workspace_id}/projects/{project_id}/finance`.

All routes require the existing opaque session cookie and current project access. Mutations require same-origin JSON and CSRF. All database actions acquire the existing shared workspace lock; finance, credit, policy and membership writers therefore use the same serialization boundary. Native PostgreSQL execution still requires separate verification. AI workers receive no finance-table grants in this phase.

## Roles and resources

| Method and suffix | Access | Purpose |
|---|---|---|
| GET `/options` | Project member | Capability flags; policy options only for administrator/finance |
| GET `/periods` | Project member | Month/state/close IDs, not private entry amounts |
| POST `/periods` | Administrator | Explicit synthetic stream period creation |
| GET `/periods/{id}` | Administrator/finance | Period, entries, documents, proposal history, release version |
| POST `/periods/{id}/documents` | Administrator/finance | Bounded protected original upload |
| GET `/documents/{id}/preview` | Administrator/finance | Plain text only; raster originals download-only |
| GET `/documents/{id}/download` | Administrator/finance | Current authorization + checksum verification |
| POST `/periods/{id}/entries` | Administrator/finance | Unapproved documented entry |
| POST `/periods/{id}/import-receipts` | Administrator/finance | Atomic canonical receipt CSV batch |
| POST `/entries/{id}/decisions` | Administrator | Approve/reject, or void approved open-period declaration |
| POST `/periods/{id}/preview?kind=close` | Administrator/finance | Read-only fresh cash/share calculation |
| POST `/periods/{id}/preview?kind=release_correction` | Administrator/finance | Read-only same-roster correction comparison |
| POST `/periods/{id}/proposals` | Administrator/finance; correction administrator | Preserve the reviewed exact preview |
| GET `/proposals/{id}` | Administrator/finance | Preserved proposal and decision |
| POST `/proposals/{id}/decisions` | Administrator | Revalidate and approve/reject exactly once |
| GET `/releases` | Administrator/finance | Preserved release-share versions |
| GET `/closes/{id}` | Administrator/finance | Replayed immutable distribution |
| GET `/closes/{id}/export?format=csv\|json\|zip` | Administrator/finance | Deterministic download; no payment side effect |
| GET `/closes/{id}/payments` | Administrator/finance | Current declaration history and reconciliation |
| POST `/closes/{id}/payments` | Administrator/finance | Completed external-transfer declaration |
| POST `/payments/{id}/void` | Administrator | Correction of a mistaken declaration only |
| GET `/closes/{id}/statement` | Current recipient | Own statement, without financial source files |
| GET `/closes/{id}/statement?recipient_id={id}` | Administrator/finance for another person | Selected recipient statement |

Responses for preserved objects contain `id`, `created_by`, `created_at`, `record`, and `record_hash`. Status fields are derived from separate immutable decisions. All commands contain `request_id` UUID and a reason of 8–500 characters. Reuse an ID only for an identical command by the same actor within the same project. A changed command under the same ID is rejected. Current access is checked before idempotent replay too.

Amounts are strict integers, never booleans, strings, exponents or binary-floating values. `amount_cents` must be 1..1,000,000,000,000. Negative corrections select `adjustment_debit` with a positive amount; do not submit negative receipt values.

## Representative period body

```json
{
  "request_id": "00000000-0000-0000-0000-000000000013",
  "reason": "Open a reviewed synthetic accounting period",
  "month": "2030-01",
  "source_policy_id": "00000000-0000-0000-0000-000000000001",
  "calculation_policy_id": "00000000-0000-0000-0000-000000000001",
  "agreement_reference": "Synthetic finance agreement version 1",
  "deficit_rule": "carry_negative_balance_forward",
  "synthetic_only": true,
  "period_rules_reviewed": true
}
```

IDs/date above are placeholders for explanation, not an existing project or a runnable command against real data. Full schemas: `app/finance/periods/schemas.py`; real fictional request fixtures: `tests/phase13_helpers.py`.

## Approval boundaries

Entry decision: `reviewed_entry_hash`, `expected_decision_hash` (null initially), `action`, `document_reviewed=true`, request and reason.

Proposal: `kind`, `reviewed_preview_hash`, `financial_records_reviewed=true`, `contribution_scope_reviewed=true`, `synthetic_only=true`, request/reason. Preview has an explanatory `record.blockers` array. Stale inputs cannot be proposed.

Proposal decision: `reviewed_proposal_hash`, `action` approve/reject, `reviewed=true`, `synthetic_only=true`, request/reason. An approved close is inserted atomically with the release snapshot when first needed and a preserved approval record. A duplicate approved request returns the same decision; a different request against an already decided proposal conflicts.

Payment: `recipient_id`, positive `amount_cents`, `provider`, `external_reference`, `paid_at` explicit ISO seconds/offset, `reviewed_close_hash`, `externally_completed=true`, `synthetic_only=true`, optional strict `overpayment_acknowledged`, request/reason.

Payment correction: `reviewed_payment_hash`, `bookkeeping_correction_only=true`, request/reason. It never mutates the underlying distribution or sends a reverse transfer.

## Errors and security

400/415/413 represent malformed protocol, unsupported encoding/content type or bounded request size. 403 denotes missing role or browser-origin/CSRF authorization; inaccessible project/scoped references use 404. Strict schema and unsupported economics often return 422. Stale fingerprints, duplicate sources, decided proposals, missing bytes, immutable periods and blocked closes use explicit 409 codes. The UI must show the returned reason and refresh; do not automatically regenerate request IDs and retry an uncertain approval.

Protected downloads include `no-store`, attachment disposition, `nosniff`, restrictive sandbox CSP, `Vary: Cookie` and `X-Content-SHA256`. No public bearer download links are created. The Node proxy preserves the artifact bytes, attachment and hash while stripping spoofed forwarding headers. Declarations and exports do not establish external financial truth.
