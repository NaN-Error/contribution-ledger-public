# Upgrade from phase 3 to phase 4

Source baseline: `0.3.0-phase3` → `0.4.0-phase4`. Migration: `0003_policies_budgets` → `0004_work_packages`. This is the complete source tree, not a database or compiled executable.

## Preserve your installation

Stop the application using `scripts/stop.ps1` (or `bash scripts/manage.sh stop`). Back up your existing source, `.env` and database before replacing files. A normal stop/start preserves the volume but is not a backup. Do not run `docker compose down -v`, delete Docker volumes, run account resets, or overwrite your own source edits without reconciliation.

Extract/merge the new `contribution-ledger/` files into the same project directory. Preserve the existing `.env`, project folder identity/Compose volume configuration, and real account data. No source deletion is required. The archive contains no `.env`, account database, passwords, uploaded artifacts or dependency directories. Do not nest a second `contribution-ledger` directory by accident; the supplied `compose.yaml` must remain at the project root.

Migrations 0001, 0002 and 0003 are unchanged. Migration 0004 adds five work-package tables and guards; it creates no packages, seed users, automatic approvals or earned units. Existing policies and planning allocations do not become work packages until an authorized user explicitly binds them.

With Docker Desktop running Linux containers, from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Open `http://127.0.0.1:5173` and sign in with the existing account. Do not run first-owner setup for an existing installation. On a genuinely fresh installation, the same setup-owner procedure documented in `setup.md` remains necessary.

## Post-upgrade checks when testing

Confirm status shows migration `0004_work_packages` and source version `0.4.0-phase4`. Your previous owner, memberships, policy versions/acknowledgements, milestone amounts and persistence marker should retain their IDs and values. Open a project and inspect the new Work packages tab. No package or credit should have appeared automatically. Follow the fictional workflow in `work_packages.md`, then restart and inspect history.

Existing approved unlinked allocations remain usable. Legacy resize/cancel commands now protect linked package scopes at both proposal and decision time. A budget proposal saved before a package was linked can therefore become invalid when subsequently reviewed; create a fresh compliant amendment instead of bypassing the guard.

## Rollback and verification limits

A nonempty phase-4 downgrade is deliberately refused before dropping history. Do not edit the applied migration to defeat this. The automatic downgrade exists only for empty phase-4 tables; otherwise use a carefully reviewed full backup restore or a forward corrective migration. Restoring an old backup discards later work and must be a deliberate operator decision.

SQLite tests exercised preservation, repeatable upgrade, empty downgrade and refusal with recorded work. The equivalent native PostgreSQL test is supplied but was not executed here. Docker, Windows/PowerShell, actual browser and clean dependency installation remain open verification gates. This release does not claim production readiness or a successfully installed frontend. All earlier candidate-lock checks remain pending.
