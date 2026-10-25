# Upgrade from phase 2 to phase 3

**Baseline:** the supplied `contribution_ledger_phase2.zip`, source `0.2.0-phase2`. **Target:** `0.3.0-phase3`, Alembic head `0003_policies_budgets`.

This is a complete source package. A new user can install it directly without installing earlier phases. No source file from the baseline is intentionally deleted. Compare `docs/file_changes.md` before replacing locally modified files.

## Existing local installation

Stop the existing application using `scripts/stop.ps1` or `bash scripts/manage.sh stop`. Preserve the old source, `.env` and database volume, and make a verified operator backup before migrating anything important. Stop/start is not a backup. Full operational backup tooling is still phase 14; use disposable synthetic data until then.

Copy the new `contribution-ledger/` contents into the existing source directory. Do not copy one nested project folder inside another. Keep your existing `.env`; the archive contains no local secrets. The Compose project name remains `contribution-ledger`, and its named database volume remains unchanged.

Run from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Normal startup rebuilds the code, runs migrations forward and starts services. It does not reset the database, generate policy examples, create a second owner or issue units. Open the same hostname you used previously, sign in with the existing account, and inspect System overview. Expected version: `0.3.0-phase3`; expected schema: `0003_policies_budgets`.

Open a project. Policies and Milestones are new tabs; the existing project settings and membership editor moved under **Settings and access**. The project defaults to Policies. All old workspaces, memberships and accounts should remain.

## Migration boundary

Applied migrations `0001_foundation` and `0002_accounts_access` remain byte-for-byte identical to phase 2. The additive migration creates eight tables: policy versions, participant snapshots, policy approvals, acknowledgements, milestones, planning allocations, budget amendments, and budget decisions. It adds scoped constraints/indexes and mutation-rejecting triggers for six immutable record tables. It does not add a contribution-event or payment table. Its downgrade intentionally refuses to drop nonempty phase-3 records.

Do not use `docker compose down -v`, delete volumes, change database credentials, edit earlier migration files or bypass history triggers to fix an upgrade. Keep old-source and verified backup copies; investigate migration errors before continuing. A restore into an isolated environment is safer than attempting destructive rollback on important data.

## Fresh installation

Run the normal start script, then `scripts/setup-owner.ps1` once and complete the owner form. A phase-1 installation without accounts also needs this explicit owner setup after migration. A phase-2 installation that already has an owner does not. An existing owner who lost a password uses the audited recovery process in `docs/account_access.md`.

## Verification still required

The migration was exercised through the injected SQLite test database and statically compiled for PostgreSQL. The native PostgreSQL upgrade/preservation, append-only trigger, duplicate-decision and concurrent-allocation tests are supplied but not run in the delivery environment. Windows execution, Docker rebuild, preservation on actual restart, browser rendering and clean package installation remain open. Keep these checks in the project status when continuing development.
