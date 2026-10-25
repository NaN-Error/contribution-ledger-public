# Upgrade to phase 7

Full source: 0.7.0-phase7. Baseline: the actual phase-6 source ZIP. The user may defer these steps until testing the completed project. Do not mistake this document for evidence that Docker, PostgreSQL, PowerShell or the browser ran here.

## Preserve existing work and data

Before replacing files, retain your local source changes and back up `.env`, the `postgres_data` volume, the separate `evidence_data` volume, operator configuration and protected recovery material. A database backup does not contain uploaded bytes. Stop application writers through the existing stop command; do not use `docker compose down -v`, delete volumes, run reset/seed commands, or recreate the owner.

Extract the full `contribution-ledger/` source and merge any actual local edits. This delivery contains no .env, real account information, database, artifact bytes, node_modules, compiled frontend or container image. It changes no third-party dependency selection. The inherited lock still requires a successful downloaded installation. Review the alphabetical file inventory; no baseline source deletion is intended.

## Start and migrate

From the folder containing `compose.yaml`, with Docker Desktop in Linux-container mode:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Startup runs the existing migration procedure. `0007_hypothetical_simulator` adds one table, `simulation_scenarios`, with scoped references, request-id uniqueness and ordinary-mutation guards. Applied migrations 0001–0006 are unchanged. There is no credit backfill, financial record generation, new default user or automatic scenario seed. Existing owners sign in normally; the first-owner setup command is only for a fresh empty installation.

Open `http://127.0.0.1:5173` and inspect status/readiness. Select the project and **Revenue simulator**. Use existing accepted synthetic credit to calculate a preview. Empty credit produces a blocked pool. Read `revenue_simulator.md` and `testing_phase7.md` for the exact behavior and deferred checklist.

## Recovery and role review

A downgrade with saved examples refuses to erase them. Do not bypass guards, edit applied migrations or silently drop the new table. Use a tested matching source/data backup for a deliberate rollback. Verify both stores and accounts after recovery before any further operation.

Default Compose remains operator-owned. The earlier optional `infra/ledger-privileges.sql` addresses phase-6 tables only; it is not a complete phase-7 production role setup. A separately provisioned non-owner runtime must receive reviewed SELECT/INSERT privileges on the new scenario table and the necessary existing reads/audit insert, but no scenario UPDATE/DELETE/TRUNCATE privilege. Existing inherited/default privileges and triggers must be checked natively. Never grant future AI workers credit-write authority. No role split is automatically enabled or claimed as verified.

Keep this source build local with synthetic data. Native migration races, actual React build/rendering, Windows operation, backups and non-owner permission tests remain in the open verification gates.
