# Upgrade from phase 7 to phase 8

This is complete source, not a patch-only ZIP or prebuilt installer. Preserve local edits separately and use the full `contribution-ledger/` root. Do not overwrite `.env`, database/evidence volumes or protected recovery material. Do not use `docker compose down -v` as an upgrade or troubleshooting shortcut.

## Default manual workflow

Stop the existing services before replacing source or applying an upgrade. Back up `postgres_data`, `evidence_data`, `.env` and protected configuration using a procedure you have actually tested. Source ZIPs are not data backups. Existing migrations `0001_foundation` through `0007_hypothetical_simulator` are unchanged; never replace them with modified historical definitions.

Extract this release, preserve your existing `.env`, and run the documented normal startup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The new additive migration is `0008_github_history`. It adds eleven tables for authorizations, connections, repositories, import tasks/outbox, retained source versions/observations, identity decisions and source evidence links. It does not create installations, run imports, reset accounts, reassign units or modify hypothetical examples. Nonempty downgrade is deliberately refused; restoring tested backups is a separate recovery decision, not an automatic migration command.

Open `http://127.0.0.1:5173` and sign in with the existing owner. Do not rerun first-owner setup. The new GitHub tab explains that the optional integration is off. The phase-7 manual workflow should work with no external key or account. Before relying on the release, follow all earlier open installation/native/browser checks plus `testing_phase8.md`.

## Optional GitHub activation, later when testing

Read `github_setup.md` in full. Add the nonsecret App ID and Client ID to `.env`, stage the two protected credential files, explicitly provision them, and start with `scripts/github.ps1 -Action start`. This creates a private `github_secrets` volume and runs a separate worker. No repository is connected or imported automatically.

For future upgrades of an already-enabled profile, stop both the API and `github-worker` before replacing code, migrating or rotating credentials. Resume through the GitHub-specific script; the normal base script does not know to stop a worker already created by the optional overlay. Use `-Action manual` to deliberately disable the integration and stop that worker while retaining history.

Preserve `github_secrets` and its protected recovery material in addition to the two data volumes. The runtime mounts it read-only with restrictive Linux file permissions. Host staging files, downloaded PEM files and volume backups remain secrets and require host protection. This feature does not encrypt the host volume or erase retired copies. Do not put the private key or client secret into `.env` or the ZIP.

Credential replacement is a stopped-service operator action. Provision validates both files before replacing them, atomically per file; interrupted pair rotation must be repeated before restarting. Reauthorize connections after replacement/expiry as required. Removing a local connection does not uninstall the GitHub App or erase retained source/work-package snapshots.

## Dependency and operational changes

Only `cryptography==46.0.4` was added to the Python dependency locks for actual RSA signing; the previous third-party selections are preserved. The frontend candidate lock still needs a clean network-backed installation. REST API behavior is pinned to `2026-03-10` and should be rechecked before deployment. This source release has no verified Docker image build/digests, Windows run, native PostgreSQL migration/concurrency or live GitHub import.

The phase-8 worker is a small DB/outbox-driven adapter; Celery/Redis, webhooks and recurring reconciliation remain phase 9. It checks local permissions, installation validity, grant versions and finite sharing-authority expiry but does not continuously observe GitHub user role revocation. Do not use this local prototype for remote production/private-team access until those controls and the complete security/restore gates are implemented and reviewed.
