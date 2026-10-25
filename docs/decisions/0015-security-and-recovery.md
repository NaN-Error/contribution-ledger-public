# ADR 0015 — Account factors, coordinated recovery and restricted staging

**Date:** September 14, 2026. **State:** implemented source with native/browser/security acceptance open. Supersedes no accounting policy. Applied migrations 0001–0013 remain unchanged.

## Decisions

Add optional local TOTP and mandatory MFA for all restricted-stage accounts. Use a separate operator master to encrypt account-bound seeds. Password success produces a pre-authentication session without a project identity when a factor is required. Recovery codes are high-entropy, hashed and single-use. Operator identity recovery forces re-enrollment. TOTP is intentionally not presented as phishing-resistant; passkeys are outside this phase.

Add migration 0014 for factor storage and pending/verified session fields. Do not mark old sessions verified, silently require uninitialized local MFA, or erase factors by downgrade. Keep the source's hard synthetic-only finance gate.

Use explicit stopped-writer local-storage captures, not a database-only backup. Pair a data archive with separately controlled recovery material and an external recovery key. Use bounded authenticated frames and strict regular-file extraction. The format is application-specific and needs external review before high-value use. Restore into a new offline Docker target only; preserve and replay calculations, verify bytes and secrets, and invalidate copied access. No automatic cutover, role/global-ACL assumption, S3-wide capture or secure-erasure claim.

Restricted staging is a standalone private-network/manual-only deployment, not a flag exposing the local operator-owned pilot. Add a non-owner runtime role, MFA startup gates, supplied trusted TLS, exact host/origin, CIDR boundary, no API/DB/web host ports and no development accounts. Provide a loopback-only drill before human readiness attestation. Production remains blocked. Credential/provider/global role/host trust remains explicit.

Repair the inherited operator-CLI import. Deliberately update the PostgreSQL patch pin to 17.11 and add the reviewed Caddy 2.11.4 staging tag. Keep all other pins until clean installation and advisory review can support changes. Do not report absent scanners, unpulled images or unexecuted native processes as passing.

## Consequences

Backups now depend on retaining the new authentication master as well as existing AI/GitHub material. A provider-secret rotation is distinct from encryption-master rotation; the latter still needs an explicit offline re-encryption design. A source artifact retirement does not remove a prepared AI packet. Every financial output remains reproducible and synthetic. Tests exercise local crypto and SQLite restoration, while native restore/privileges/browser/TLS remain blocking deployment gates. Phase-15 evaluation development can continue without falsely marking those gates complete.
