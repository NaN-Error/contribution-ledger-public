# Phase-14 security review record

This is an implementation review and adversarial-test record, **not an independent penetration test, certification or declaration that no defect remains**. Source version `0.14.0-phase14` remains synthetic. Native and browser gates are not waived.

## Changes and retained boundaries

The inherited operator CLI had malformed imports including a nonexistent `inspect_credittem_status`; it now imports `system_status` correctly and has an import regression. Password-only sessions cannot pass project authorization when MFA applies. Seeds use a separate master, recovery codes are one-use hashed secrets, attempts are bounded, and pending sessions have a short expiry. Operator reset forces re-enrollment rather than removing the boundary.

The final new migration keeps SQLite session-column changes in place rather than rebuilding a parent table referenced by GitHub records. It also starts an explicit SQLite transaction for legacy-driver DDL: a failed forward upgrade or blocked deep downgrade must not leave columns removed while the Alembic revision rolls back. Populated upgrade, failure rollback and retry tests exercise this behavior. Applied migrations 0001–0013 are not edited.

Direct API responses now add no-referrer and deny-framing headers. Read-only requests with a body and ambiguous Host headers are rejected. Existing origin/CSRF, upload bounds, restricted evidence, private financial documents, independent-review, exact-money, prompt-injection and provider-spending checks remain in the full regression. Input validation is not malware scanning, and accepted citations are not proof of model truth.

Restricted staging is separate, mandatory-MFA, manual-only, HTTPS and CIDR-gated. It uses a non-owner runtime database role with native startup checks and preserves the trusted operator path for migrations. No phase opens public signup, production settings or real finance. An outside-CIDR denial is not a reason to trust unverified forwarding headers.

Recovery tooling stops labelled writers, checks inventory, makes paired authenticated encrypted bundles, rejects unsafe extraction, restores only into a new isolated target and verifies retained records/bytes/keys. The local SQLite restore test exercises a real synthetic financial close and secret recovery. Native deployed recovery, privilege reconstruction, source-global role configuration and Windows ACLs remain open.

## Dependency decision

Normal/CI PostgreSQL moves from **17.7** to **17.11**. Upstream's August 13, 2026 release describes security fixes; retain the old image only for isolated pre-upgrade recovery drills, and verify the new platform image/digest before use. Staging adds Caddy **2.11.4**, whose upstream release includes security-related patches. No image has been pulled here.

All other inherited package/runtime pins remain explicit but require clean installation, vulnerability-advisory review and digest/hash completion. Updating two component tags does **not** establish that the whole stack is vulnerability-free or current. Python 3.13.5 / Node 22.16.0 are the available test runtimes, not a claim about the newest supported patch. The candidate frontend lock still lacks completed network-backed installation evidence. No unrun scanner is reported as clean.

## Release-blocking checks still open

Clean dependency installation and full React/Vite build; actual browser/cookie/MFA flows; Windows helpers; native PostgreSQL migrations and MFA/budget/close concurrency; runtime/worker privileges and function ACLs; container architecture/digests; edge peer/TLS/firewall behavior; coordinated native restore and failed-upgrade recovery; full artifact/key/packet retention policy; live external-provider authorization, data and billing controls; threat review of backup encryption and factor implementation; independent security/load testing; the user's deferred acceptance.

The loopback-only drill permits testing these gates without pretending they passed. A manually completed readiness record is an operator attestation, not cryptographic proof. Public production and real finance remain rejected even after that record.

Primary references checked September 14, 2026:

- MFA: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- TOTP protocol/test vectors: https://www.rfc-editor.org/rfc/rfc6238
- PostgreSQL security patch release: https://www.postgresql.org/about/news/postgresql-186-1711-1615-1519-1424-and-19-beta-3-released-3365/
- Dump/restore scope and trust: https://www.postgresql.org/docs/current/app-pgdump.html and https://www.postgresql.org/docs/current/app-pgrestore.html
- Caddy release: https://github.com/caddyserver/caddy/releases/tag/v2.11.4
- Caddy TLS: https://caddyserver.com/docs/caddyfile/directives/tls
