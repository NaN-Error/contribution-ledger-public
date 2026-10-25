# GitHub API contract — phase 8

The application exposes these endpoints on its existing local API, not on GitHub. Every route requires a current ledger session. Mutations require the existing exact Origin and CSRF checks. `P` below abbreviates `/api/v1/workspaces/{workspace_id}/projects/{project_id}`; use actual UUIDs. The authenticated API schema also documents exact request types and required bounds. Never put credentials in these application requests.

## Authorization and repository selection

| Method and path | Permission | Purpose |
|---|---|---|
| GET `P/github` | Admin/reviewer | Configuration, verified connections, repositories, retained-version counts |
| POST `P/github/authorize` | Admin | Installation ID plus reason; returns session-bound OAuth URL and flow metadata |
| POST `/api/v1/github/callback` | Bound session/admin | `{state, code}` after explicit callback verification |
| POST `/api/v1/github/connect` | Bound session/admin | `{flow_id, reviewed_proof_hash, repository_ids, sharing_confirmed:true, reason}` |
| POST `P/github/connections/{id}/disconnect` | Admin | `{expected_version, reviewed:true, reason}` |

The browser GET `/github/callback` serves only the application shell and strips query credentials before verification. It does not itself write a connection. Begin requires the browser origin to equal the configured callback origin. A flow is single-use, session/actor/workspace/project/installation bound, expires after 10 minutes, and has a reviewed proof fingerprint. Connect only accepts repositories from that proof. `installation_id` and selected GitHub repository IDs are positive safe integers, not local UUIDs. The API does not accept arbitrary remote URLs or bearer tokens.

## Imports and source records

| Method and path | Permission | Purpose |
|---|---|---|
| POST `P/github/imports` | Admin | Save a bounded durable request |
| GET `P/github/imports` | Admin/reviewer | Paged run history |
| GET `P/github/imports/{id}` | Admin/reviewer | State, cursor, observations, omissions, error/delay and anchor |
| POST `P/github/imports/{id}/resume` | Admin | `{expected_version, reason}`; delay and access checks apply |
| POST `P/github/imports/{id}/cancel` | Admin | Same shape; invalidate pending worker writes |
| GET `P/github/sources` | Admin/reviewer | Paged versions; optional local `repository_id` and `kind` |
| GET `P/github/sources/{id}` | Admin/reviewer | Hash-checked normalized document and number of other retained versions |

Import body: local `repository_id` UUID; `start_at` and `end_before` with explicit offsets; integer `request_limit` (10–1000, default 200); integer `entity_limit` (1–200, default 50); `request_id` UUID; `reason`; `reviewed:true`. Ranges are increasing, at most 366 days, and not future-ending. Request IDs are idempotency keys: reuse for a repeat of the same intended command, not a different import. Responses are ordinary JSON with bounded lists and optional `next_offset`.

## Identity decisions and evidence sharing

| Method and path | Permission | Purpose |
|---|---|---|
| GET `P/github/identities` | Admin/reviewer | Claims, version, optional current local mapping and active people |
| GET `P/github/identities/{id}/history` | Admin/reviewer | Preserved mapping decisions |
| POST `P/github/identities/{id}/mapping` | Admin | `{expected_version, user_id:UUID|null, reviewed:true, reason}` |
| POST `P/github/sources/{id}/link` | Admin | Explicitly share an exact version with an existing package |
| GET `P/work-packages/{package_id}/evidence/{evidence_id}/revisions/{revision}/github-source` | Authorized evidence reader | Exact pinned source, checked against current and historical evidence visibility |

Link body: `package_id`, `expected_package_version`, `reviewed_source_hash`, existing `EvidenceMetadata` object, `reason`, `request_id`, `sharing_confirmed:true`. The metadata shape is the same validated title/provenance/category/date/author/visibility/deliverable shape used in manual evidence. The caller cannot submit or modify the server `external_source` proof. Package writes must be allowed by the existing work/evidence state machine. Replays cannot duplicate the package/source link.

All financial and contribution endpoints remain separate. None of these routes issues units, edits current contribution shares, closes a financial period, activates a policy or pays anyone.

## Error handling

Validation errors use existing sanitized 422 responses. Unknown/cross-project IDs use the existing nondisclosing not-found behavior; lack of permitted role is denied by the authorization layer. State/hash/version changes produce actionable conflicts rather than stale writes. Provider access denial, rate limits, revoked/suspended installations, malformed/oversized responses and network uncertainty are mapped to bounded errors without storing or returning secret-bearing upstream bodies. Use the returned error code and request ID for support, not raw OAuth URLs or bearer tokens.

The callback's maximum transport work budget is 60 seconds and its reverse-proxy response allowance is 90 seconds; ordinary API requests retain the smaller proxy timeout. These are application bounds, not a guarantee about every operating-system resolver/network stall. Retrying a failed OAuth callback begins a fresh flow. Only the separate worker handles saved import retries.
