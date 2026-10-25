# Upgrade to phase 14

**Source version:** `0.14.0-phase14`. This is a source delivery, not a verified production deployment. Read `project_status.md` and `testing_phase14.md` before deciding to operate it. Financial records remain synthetic-only.

## Preserve the old installation first

Keep the phase-13 source tag, private `.env`, `postgres_data`, `evidence_data`, configured `github_secrets`, and both `ai_credentials` / `ai_master`. Phase 14 adds `auth_master`: once a person enrolls an authenticator, that separate master is required to decrypt the stored seed. A database-only backup is incomplete.

The standard database image changes deliberately from `postgres:17.7-bookworm` to `postgres:17.11-bookworm`, following the upstream August 13, 2026 security release. This changes a patch version, not the major database series. The image has not been pulled or tested here; review and verify it on the actual platform. Python, Node, JavaScript and Python-package pins otherwise remain unchanged. Old immutable migrations are not edited.

For an existing populated installation, take a coordinated backup **before** starting the new database image or applying migration 0014. The new recovery helper can inspect and capture a stopped-writer phase-13 database without requiring it to have the new schema. Build its helper image only; do not use normal startup yet:

```powershell
docker build --target base -f infra/api.Dockerfile -t contribution-ledger-api:0.14.0-phase14 .
```

Follow `runbooks/backup_restore.md`. Its host Python needs the project's installed dependencies. Keep a tested recovery route using the old source and images; the new native Docker restore has not been executed in this development environment. Do not call an untested encrypted file a verified recovery plan.

## Apply the source update

Overlay the complete source while preserving `.env` and volumes. No existing source path is intentionally deleted. Do not copy source release manifests over private operator configuration. From the repository root, with Docker Desktop running Linux containers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The scripts stop optional integration writers, stop the API, build, bring up PostgreSQL and apply forward migrations before restarting the normal application. An error leaves the operation incomplete; inspect it without removing volumes. Existing owners sign in normally. A new database alone needs `scripts/setup-owner.ps1`.

Migration **0014_security_recovery** adds one `authenticators` table and two browser-session fields plus an index. Existing accounts, workspaces, contribution events, evidence, closed distributions and earlier migration bytes remain unchanged. No user is enrolled or marked MFA-verified automatically. Downgrade refuses to remove retained authenticator rows. Restore a coordinated backup instead of trying to force a destructive downgrade.

This phase also repairs the inherited operator-CLI import (`system_status`), which prevented the CLI from importing. An import regression test now covers it. That repair is not a claim that native Docker startup has been verified.

## Optional local authenticator setup

Local MFA remains opt-in so existing accounts do not suddenly require an unconfigured key. To provision its new private master volume deliberately:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\security.ps1 -Action init
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Initialization stops writers, migrates and creates or checks the key without replacing an existing one. If factors exist but the key is missing, it refuses; restore the original key. Then use **Account and sessions → Authenticator protection**. Keep the one-time recovery codes privately. Read `account_security.md`.

The local API still uses the trusted operator database connection. The new non-owner runtime role applies to the separate restricted staging configuration, not silently to an existing pilot. Re-run the established optional GitHub/AI setup procedures only when deliberately enabling those integrations. They remain off in the initial staging profile.

## Separate staging is not an upgrade shortcut

`compose.staging.yaml` is a standalone, new deployment with its own volumes, generated operator/runtime credentials, HTTPS certificate requirements, mandatory MFA and readiness gate. Never combine it with the normal compose file. It does not adopt the local pilot's data automatically and does not publish a public service. Follow `runbooks/restricted_staging.md`.

The complete installed React build, browser enrollment, Windows helpers, native PostgreSQL concurrency/permissions, Docker backups and restore must still be verified. A source ZIP, unit-test pass or readiness declaration is not that verification.
