# ADR 0003 — Invited accounts and scoped access

Date: September 13, 2026. Status: implemented in source; environment acceptance remains open. Builds on phase 1 without changing applied migration 0001 or inherited framework versions.

## Decisions

Use server-owned opaque sessions instead of browser JWTs. Store purpose-separated SHA-256 hashes of random 256-bit session/invitation/recovery secrets. Derive a session-bound CSRF value from the raw cookie; return it through same-origin JSON and keep it in browser memory. HttpOnly/Lax cookies are local HTTP in development; the secure branch uses Secure and the `__Host-` prefix. Staging/production remain blocked until the planned remote hardening gate.

Use argon2-cffi 25.1.0 with Argon2id (64 MiB, three iterations, four lanes); cap new passwords to 15–128 characters and verify with a dummy hash for unknown accounts. The added exact dependencies are argon2-cffi/bindings 25.1.0, cffi 2.0.0, and pycparser 3.0. These versions were present in the execution environment; clean pinned installation remains unverified. Password hashing can be memory/CPU intensive, so load/concurrency validation remains part of later hardening.

Apply explicit Origin plus CSRF checks to bounded JSON writes, including login/bootstrap. Never trust a client-provided X-Forwarded-For to bypass the local peer throttle. PostgreSQL-backed fixed 15-minute windows survive process restarts. Peer limits are intentionally shared behind the trusted local proxy; deployment-aware rate limiting comes before remote use. Bound pending body size in both proxy and API. Keep credentials out of browser storage, request URLs, allowlisted logs and responses not explicitly delivering a newly issued secret.

Bootstrap/recovery are explicit host-operator operations, not unauthenticated public self-registration. Operator recovery records a reason, revokes sessions and returns a one-time token rather than impersonating the user. No email verification/delivery is implied by possessing an ASCII email string.

Centralize active workspace/project permission resolution. Composite foreign keys make project membership/evidence-facing IDs tenant-consistent. Workspace owners/admins inherit only their own workspace's project administration. Ordinary members require explicit grants. Use expected versions for editable access/settings and workspace row locks around scoped mutations. Serialize invited-account creation through a database installation row. Lock individual users for password/disablement and membership-cap decisions. Native PostgreSQL lock behavior has dedicated but unexecuted tests; SQLite does not validate it.

Preserve identity and role history rather than delete members. Suspend workspaces and explicit grants separately; do not auto-restore grants through new invitations. Append audit events and install database triggers against ordinary mutation. Database administrator trust is not removed by these triggers. Do not expose economic approvals or let administrative status bypass the future independence check.

## Scope corrections and limitations

The phase-1 read-only Node proxy had to be extended for real account writes and Set-Cookie responses. This is an intentional source change, not enabling arbitrary upstream URLs. The proxy strips spoofed forwarding/authorization headers, and supplied Uvicorn commands explicitly disable proxy-header interpretation even for direct loopback calls. Automatic catalog/provider/GitHub behavior is still absent.

The UI clears inaccessible data after failed checks/reload. Revocation cannot erase previously delivered information or abort every request already in flight. Public technical health checks remain without account authentication on loopback; no private team records are in those responses. Re-enable/recovery are not substitutes for an agreed identity-verification procedure. No multi-factor authentication, independent penetration test, production deployment, or paid-service integration is claimed.

## Primary references checked during implementation

- argon2-cffi API: https://argon2-cffi.readthedocs.io/en/latest/api.html
- OWASP password storage: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP session management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP CSRF prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- SQLAlchemy constraints: https://docs.sqlalchemy.org/en/20/core/constraints.html

These references informed the design. They are not a certificate that this implementation has passed an external security review.
