# Upgrade to phase 10

Baseline: actual `contribution_ledger_phase9.zip`, source 0.9.0-phase9. Destination: 0.10.0-phase10. This is full source, not a binary installer. Clean dependency installation, Docker/native PostgreSQL, PowerShell, browser and live-provider acceptance remain open.

## Preserve first

Stop the running optional workers/API before copying files or migrating. Back up private `.env`, the actual `postgres_data`/`evidence_data` volumes, configured GitHub secrets and protected recovery material. Preserve existing accounts and prior migrations. Do not delete volumes, bootstrap another owner, run seed/reset, or overwrite the host environment with the example file.

The archive has full `contribution-ledger/` paths and no deliberate source deletions. Copy it into the existing project directory without creating an extra nested root. It contains no real database, `.env`, provider keys, dependency folders or built images. Do not mix an older `apps/api` with the new frontend/migration.

## Normal manual-only upgrade

From the project root, with Docker Desktop in Linux-container mode:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The script stops optional integrations before migrations. Existing owners sign in normally at `http://127.0.0.1:5173`. The additive head is `0010_ai_provider_foundation`. Migrations `0001` through `0009` are byte-for-byte preserved. No startup connection, catalog, generation, evidence evaluation, credit or financial obligation is created. The AI settings page can display the feature, but queued work requires the explicitly enabled AI worker.

Migration 0010 adds nine tables: `ai_connections`, `ai_models`, `ai_prices`, `ai_usage_buckets`, `ai_jobs`, `ai_operation_events`, `ai_profiles`, `ai_profile_approvals`, `ai_usage_resolutions`. It adds scoped foreign keys and immutable history/identity guards plus a narrow PostgreSQL locking function. Existing GitHub/contribution/evidence records are not reinterpreted. A nonempty P10 downgrade is refused before dropping its history. Do not force that downgrade; restore a complete reviewed backup instead.

## Optional no-cost AI workflow

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action init
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action start
```

Read `ai_connections.md` first. Initialization creates separate encrypted-credential and master-key volumes and the restricted AI worker DB role. No provider is contacted, and default flags permit only the synthetic provider. Init stops the API; start restores it after successful setup. `-WithGitHubSync` on start combines an already-configured GitHub-sync deployment with AI. Standalone normal startup intentionally returns to manual mode.

From this point onward, preserve the `ai_credentials` and separate `ai_master` volumes as well as `.env`. Both master and ciphertext must match to restore credentials. The AI worker database password remains in protected `.env`, not in the credential vault. Do not share it or put it in the source ZIP.

## Verify later, before real use

Follow `testing_phase10.md`. Confirm migration head and prior data persistence; finish a fake-only catalog/probe/profile workflow; demonstrate that a catalog change cannot alter the approved profile; verify current role isolation and queued revocation; check worker recovery and the native restricted role. A protocol probe cannot evaluate real contributions. Actual AI evidence review is phase 11.

If initialization, package installation or migrations fail, preserve state and record sanitized error messages locally. The development container could not verify your Docker/Windows/installed React/native database environment. None of the source delivery's skipped tests should be marked complete without actually executing them.
