# ADR 0009 — Read-only GitHub evidence and first durable import adapter

Date: September 14, 2026. State: implemented in source; native/live/browser acceptance open. Supersedes no economic policy or applied migration. Baseline: 0.7.0-phase7; delivery: 0.8.0-phase8.

## Decisions

Use one operator-controlled GitHub.com App, selected repositories, fixed provider origins and versioned read-only REST calls. Start authorization from the existing local session, use one-use state plus S256 PKCE, and prove both App installation identity and the authorizing user's repo-admin authority. This deliberately restricts sharing more than ordinary read access. Do not retain user or refresh tokens. Issue narrowly scoped installation tokens for individual fetch checkpoints. A finite local sharing proof expires within 24 hours; install access is checked per checkpoint, not live user-role revocation. Document that gap and retain the phase-9 revocation gate.

Use a SecretStore abstraction with allowlisted operator-provisioned files. A stopped-service provisioning command copies protected host staging files into a private Linux-permissioned named volume. Runtime consumers mount it read-only. This is not an encrypted multi-tenant BYOK backend; phase 10 expands that contract. Do not put keys in the database, web requests, environment examples or queue bodies. Key rotation is atomic per file, not as a pair; stop consumers and rerun after interruption.

Activate PostgreSQL import/task/outbox persistence and a separate DB-polling worker now. **Defer Celery/Redis transport activation to phase 9** rather than introduce untested broker behavior while implementing basic import semantics. This is an explicit implementation-order decision relative to the planned general worker stack, not a framework switch. Work leasing, fencing, bounded retries, cancellation and idempotent effects already belong to the database. The current job_outbox is import-specific; a future migration must extend/generalize it rather than pretend it is already a universal dispatcher.

Preserve normalized source versions and immutable observations instead of cloning/executing repositories. Bound dates, endpoints, pagination, bytes, entity counts and quota. Record requested scope and actual observation time separately. A current API response is not historical time travel. Double-check PR file revision boundaries and omit ambiguous captures. Best-effort redaction reduces accidental retention but does not guarantee all secrets are removed.

Keep raw imports restricted to admins/reviewers, while explicit source-to-package linking uses the existing evidence access model and a server-generated exact-source pin. Share only after an explicit visibility confirmation. Preserve that pin through subsequent manual evidence amendments; let new source evidence invalidate unfinished review packets without changing finalized awards or saved scenarios. Separate numeric GitHub identities from local accounts and from unverified commit/co-author claims. Mapping is an auditable human decision, not identity verification or credit.

## Invariants

No import/link/mapping writes the credit ledger or financial tables. Existing workspace-lock order, policy quorum, evidence and package rules remain intact. One source version linked twice to one package does not duplicate evidence. Immutable source records and scoped composite keys have migration-level guards; a nonempty downgrade refuses history deletion. Applied migrations 0001–0007 remain unchanged.

The default database profile remains operator-owned. The worker's application code has no ledger finalization call, but least-privilege database enforcement is **not provisioned or verified** by this release. The earlier phase-6 privilege script is not a complete role plan for these eleven new tables. Source security tests are not an infrastructure security audit. No production-ready or complete fairness claim follows from passing the offline suites.

## Consequences and next work

The manual workflow remains usable without GitHub. Imports run only while the explicitly enabled worker/deployment operates. Live App setup, organization/SSO behavior, actual returned admin flags, native concurrency, image/build compatibility and browser flow must be tested against the owner-authorized fixture repository. Phase 9 will add signed webhooks, authoritative reconciliation, dispatch/scheduler improvements and stronger revocation handling. It must retain all archived source/evidence/credit relationships and the no-economic-write boundary.
