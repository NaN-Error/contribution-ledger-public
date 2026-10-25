> **Phase-11 update:** For evidence assessments and current upgrade steps, read `ai_assessments.md` and `upgrade_phase11.md`. Old protocol-only profiles remain unchanged. New runs need separate disclosure/payer approvals, and existing AI worker grants must be refreshed. Current executed/deferred checks are in `test_results.json`.

# AI operator guide and recovery boundaries

This guide describes source behavior, not a verified Docker/PostgreSQL deployment. Read ADR 0011 and `testing_phase10.md`. Normal startup remains local-only/manual; the optional AI overlay must be explicitly initialized and started.

## Persist these independently

- `postgres_data`: accounts, evidence metadata, policies/credit, GitHub state, AI references/catalogs/jobs/usage/profile history.
- `evidence_data`: existing protected uploaded artifact bytes; not mounted to the AI worker.
- `github_secrets`: only for an enabled GitHub integration, retained from previous phases.
- `ai_credentials`: authenticated encrypted provider credentials, writable by the API and read-only to the AI worker.
- `ai_master`: separate AES-256 master key, read-only to API/worker; only explicit initialization has write access.
- Private `.env`: application settings and database passwords, including a separate restricted-worker password. This file is not encrypted by the provider-key vault.

Docker Compose prepends its project name to actual volume names. Inspect the existing deployment; do not assume a second extraction refers to the same volumes. Never run `docker compose down -v` as an upgrade. An encrypted credential backup without its correct master key is unusable; storing both together without equivalent protection defeats the isolation goal. Restore consistent database/credential/key versions with workers stopped. No automatic full backup/restore tool is claimed in P10; comprehensive recovery drills remain P14.

Keep host access and backups restricted. Root or an operator with both key and ciphertext can decrypt credentials. Application encryption is not protection against a fully compromised backend. Revocation cannot erase previous exports/backups/provider records.

## First initialization and worker privilege provisioning

`scripts/ai.ps1 -Action init` (or `bash scripts/ai.sh init`) uses the current operator database account. It generates a separate 64-hex-character worker password only if absent, runs the additive migration, initializes storage without provider network access, and provisions the reserved `contribution_ledger_ai_worker` role.

The provisioner is deliberately limited to a dedicated application database/public schema. It refuses unrelated privileged roles or unexpected ownership/membership and checks effective permissions including column grants. It does not silently rewrite arbitrary customized deployment grants. Migration introduces a narrowly scoped workspace-lock function with fixed search path and revoked PUBLIC execution. The worker receives just the function execution and specific AI table/reference privileges it needs; user reference reads are limited to `id,is_active`, not password hashes.

The worker cannot ordinarily read contribution events, finance/simulation scenarios or uploaded evidence, write account membership, approve profiles, or issue credit. It has no evidence/GitHub-secret mount and uses its own database password, not the operator password. The default API remains operator-owned. These statements describe intended supplied grants and tests; actual native role provisioning, cross-role negative tests and deployed container mounts still require verification.

Re-running initialization does not overwrite a master key or an existing worker password. It may reapply the reserved role's reviewed grants. A custom least-privilege API role must receive new migration access explicitly; the script does not guess that role. Do not edit applied migrations to work around an existing deployment.

## Jobs, leases and scheduling

AI uses its own database-owned job queue because the older GitHub outbox has GitHub-specific foreign keys. The optional AI polling process performs bounded maintenance, claims eligible work under the common workspace lock and commits its lease before networking. It is independent of Redis and Celery. The supplied combined overlay can keep both integration systems active without pretending they share one payload type.

Catalogs are queued on connection creation, manual request and roughly daily while the worker is active. A job may still be waiting on credentials, permissions, cooldowns or capacity. The worker processes bounded records; there is no always-on behavior when the deployment is stopped. A successful catalog has at most 2,000 models/twenty provider pages; retained model IDs max 5,000. Incomplete or failed refreshes do not erase the last complete catalog. Selection qualification uses at most 48-hour catalog age, not merely a green label from months ago.

Eligible catalog failures retry at most three attempts. A 429 delay is shared by the connection so another request cannot bypass it. Jobs waiting beyond the current month or their price/model generation are cancelled safely before a probe is sent. Expired catalog leases are recovered with bounded retry. Worker leases expire after 1,800 seconds; fixed-host transport has shorter connect/read limits.

A probe is durably marked dispatched **before** networking. If that worker disappears after the marker, recovery cannot know whether the provider received/billed the call: mark it ambiguous and keep the hold. Do not dispatch that probe again. Revocation or a lost lease prevents later qualification writes but cannot undo an already-sent request. For uncertain costs, the payer inspects the provider bill and records a one-time reconciliation through the API/UI.

The system deliberately avoids exactly-once network billing claims. Local idempotency prevents duplicate application commands from initiating duplicate jobs; it is not a provider transaction guarantee. Even a local pre-send crash can conservatively reserve money unnecessarily until reviewed.

## Credential errors and orphan recovery

AES-GCM authenticated context includes tenant, project, connection and provider. Reusing a ciphertext with another binding fails. Files use operator-generated UUID references and restrictive POSIX modes; symlinks, nonregular files, unexpected sizes and unsafe master permissions are rejected. Windows host filesystem semantics still need the container deployment check.

Known pre-commit create/rotation failures attempt removal of newly written ciphertexts. A process crash or ambiguous database commit can leave an encrypted orphan; retain it until an operator can compare a consistent database snapshot with storage. There is **no automatic orphan deletion or key-recovery route**. Never delete a file merely because it was not in an older backup. Do not log or print decrypted values to inspect this state.

Rotation writes a new credential and commits a new generation before best-effort old-file deletion. Revocation commits disabled state first. Both return a deletion flag; a false flag means local encrypted bytes require operator attention, not that access should be re-enabled. Revoke/rotate the API key at the provider as separately required. Key loss cannot be repaired by recreating a random master; replace the permitted provider credentials through a reviewed recovery process.

If storage initialized but the database role could not be provisioned, retain both volumes. Fix the stated privilege prerequisite, then repeat initialization. Never replace the existing master to resolve a connection error.

## Limits and privacy

There are 50 connection history records and 10,000 AI jobs per project, 5,000 retained models/prices per connection, 1,000 profile versions per project, and at most five held/uncertain probes per connection. History is deliberately not silently deleted to make room; reaching a quota needs a reviewed future archival decision. API lists are bounded/paginated and dashboards present recent pages, not an implied exhaustive listing.

Costs are estimates per connection per UTC month; current monthly cap range is $0–$1,000. A cap is not account-wide, does not meter outside calls, and does not validate a payer's manually reviewed price. Provider discounts, priority tiers, taxes, service tools or missing token usage may require reconciliation. Existing provider account billing controls remain the payer's responsibility.

The fixed synthetic probe can test text/JSON protocol compatibility only. Its success says nothing about coding ability, contextual correctness, quality, bias or suitability for compensation. The model identifier may represent a provider-controlled alias. No credential entitlement or API result establishes permission to send proprietary repository code; P11 must enforce project-specific data sharing independently.

## Pausing and upgrade behavior

Normal `start.ps1` and optional start/init commands stop labeled integration workers before migrations. `ai.ps1 -Action pause` stops all optional integrations, including GitHub consumers. `manual` restores the normal API/web mode and preserves all volumes; use it to keep the manual application available during provider outages.

For combined GitHub and AI, use `ai.ps1 -Action start -WithGitHubSync` after both systems have been deliberately configured. A different standalone overlay start can recreate the API with different settings. Inspect resolved configuration locally, but never paste resolved secret-bearing Compose output into chat. No public listener, tunnel, hosting purchase or provider account mutation is made by these tools.
