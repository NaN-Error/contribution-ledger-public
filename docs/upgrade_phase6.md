# Upgrade to phase 6

Baseline: complete source 0.5.0-phase5. Target: 0.6.0-phase6. This package is source, not an installer or prebuilt image. Full clean-install and Windows/native/browser verification remain open; use synthetic data.

Stop the local services without deleting volumes. Back up existing source edits, `.env`, the PostgreSQL store and `evidence_data` using the existing documented procedures. Do not run `docker compose down -v`, delete the database, rerun first-owner setup or replace your configuration with a test fixture. Extract the complete new `contribution-ledger/` source, preserving your local `.env` and named volumes. No baseline source paths are intentionally deleted by this upgrade; verify the included alphabetical manifest.

From that root with Docker Desktop running Linux containers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Normal startup runs forward migrations, not seed/reset/recovery. The new head is `0006_human_credit`, with eleven tables and one unique submission-scope index. Migrations 0001–0005 are unchanged. Existing accounts, policies, work, submitted evidence and artifacts are preserved. No historical submission is automatically accepted, no unit is awarded during migration, and no person receives a default share. Existing owners sign in normally at `http://127.0.0.1:5173`.

New tabs: Human reviews, Contributions, Disputes. Work-package detail now has independent per-deliverable assignment controls. A real independent reviewer must exist and acknowledge relevant policy; source upgrades never create dummy approval accounts. No GitHub, AI API key or cloud account is needed.

The database migration refuses downgrade when any new review/credit/dispute/notification records exist. Do not overwrite 0006 or bypass guards to force rollback. For a failed upgrade, stop writes and investigate from the backup; restoring only old code while retaining a newer schema is not a verified rollback. Preserving data takes priority over clearing an error quickly.

No base image or third-party dependency selection was changed in this phase; only source-version labels advanced. The inherited npm lock remains candidate pending successful network-backed installation. Default local operator-owned DB access is not the future least-privilege deployment profile. Detailed review walkthrough: human_review_and_credit.md. Test gates: testing_phase6.md and project_status.md.
