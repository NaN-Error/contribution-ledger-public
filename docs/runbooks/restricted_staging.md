# Restricted synthetic staging

## Deliberately separate deployment

Use the standalone `compose.staging.yaml` only through its operator scripts. Do not merge it into `compose.yaml`, adopt pilot volumes implicitly, place it behind an arbitrary public tunnel, or open cloud firewall ports as a workaround. It is not a production configuration and it never enables real financial records.

The profile has a separate PostgreSQL database, evidence volume, MFA master and generated operator/runtime passwords. The API uses a non-owner `contribution_ledger_runtime` role. Startup checks for an unexpected superuser/role-creation/database-creation/replication/bypass privilege, table ownership, schema creation and ledger-truncate authority. The role still relies on application authorization for project isolation; it is not a row-level-security or hostile-database-administrator solution.

The runtime API cannot perform migrations or ordinary history deletion/truncation through that role. Existing history triggers remain. The operator service retains migration authority and must stay private. Exact native grants and all necessary runtime operations remain to be validated.

The app requires MFA for **all** accounts, secure host-prefixed cookies, one exact HTTPS browser origin, disabled development tools and manual-only operation. Generated phase-2 demo accounts are rejected at startup. Invite real test participants deliberately; this staging gate does not certify their identities or actual independence. There is no public registration, email delivery, domain purchase, hosted service or automatic certificate issuance.

GitHub and AI integrations remain disabled. Every network is internal. PostgreSQL, API and web have no published host ports. Only the TLS gateway can bind port 8443, initially on `127.0.0.1`; later an explicitly selected private IPv4 bind may be used after the readiness review. The gateway's client CIDRs are explicit, and it ignores client-supplied forwarding headers. API docs/OpenAPI and integration routes are blocked at the edge. The Caddy admin API is off. Services do not automatically restart after a failure.

## Prepare without opening the interface

The host needs the project's installed Python dependencies. Example hostname is fictional; configure its local/private DNS or hosts entry yourself:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/staging.ps1 -Action init -Hostname ledger.test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/staging.ps1 -Action prepare -Confirm PREPARE-ISOLATED-STAGING
```

Initialization writes private `.local/staging/operator.env` and an all-false readiness record without starting services. Preparation stops any existing staging API/web/gateway, builds the images, starts the database alone, applies migrations, initializes the MFA master without replacing it, and provisions the distinct runtime role. It does not open a host port.

Provide a certificate chain at `.local/staging/tls/server.crt` and its matching private key at `server.key`. It must be currently valid, contain the **exact hostname** in DNS subject alternative names and be trusted by the actual test browsers. The helper checks the key match, hostname and dates. It does **not** establish browser trust or consult a certificate revocation service. Do not bypass browser TLS errors.

Caddy is pinned to 2.11.4 and PostgreSQL to 17.11. Neither image has been pulled or exercised here; verify available architecture-specific images and digests before use. Runtime/container patch advisories and the inherited dependency locks still need review. The gate records this work, not a prefilled security assertion.

## Loopback-only verification drill

To make actual TLS/browser/MFA verification possible before claiming readiness, a separate drill action is available. It refuses a non-loopback host bind and does not update any readiness field:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/staging.ps1 -Action drill -Confirm START-LOOPBACK-ONLY-DRILL
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/staging.ps1 -Action setup-owner
```

The operator receives a private first-owner token through the established command. Open the exact trusted address, normally `https://ledger.test:8443`, create the owner, enroll MFA, save recovery codes and complete the browser checklist. No password-only project access is allowed.

Docker Desktop/NAT may change the peer address seen at the gateway. A request denied by the explicit CIDR rule is a safe failure, not justification for `0.0.0.0/0` or trusting arbitrary `X-Forwarded-For`. Verify the actual peer/network path and narrowly authorize it through the operator configuration. The loopback drill accepts a separately verified private NAT peer only as a single-host /32 (or IPv6 /128) rule, never a broad non-loopback network; its published host bind must remain 127.0.0.1. For private-network operation, an indistinguishable NAT peer is not proof of each end-client identity: enforce the intended client boundary at the actual host/firewall. If the deployment cannot enforce the intended client boundary, leave staging blocked; use an appropriately secured network/firewall design before remote access.

Stop the drill explicitly afterward:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/staging.ps1 -Action stop
```

## Readiness before the private-network start

Record the operator and evidence in `.local/staging/readiness.json`. `clean_build_verified`, `native_database_verified`, `restore_drill_verified`, `mfa_browser_verified`, `tls_and_network_verified`, and `dependency_review_completed` must each be true. Keep the actual reports separately. A boolean is a human attestation, not a cryptographic audit or something the program can prove from that file.

Only after those checks, and only for an explicitly approved private bind/client range:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/staging.ps1 -Action start -Confirm START-RESTRICTED-SYNTHETIC-STAGING
```

This remains synthetic, invited and manual-only. The source delivery sets no readiness flags and publishes nothing. The operator must still check the host firewall, NAT behavior, certificate trust, DNS, actual service exposure, recovery route, browser policies and account access.

Status and bounded service logs are available through Docker and the existing application/job status screens. Do not run `docker compose config` or environment inspection into a shared log: they may reveal operator passwords. There are no plaintext access-body logs or external analytics added here. Review unsuccessful startup with local protected logs, not by enabling debug mode or broad CORS.

Primary references: https://caddyserver.com/docs/caddyfile/directives/tls , https://caddyserver.com/docs/caddyfile/directives/reverse_proxy , https://github.com/caddyserver/caddy/releases/tag/v2.11.4 .
