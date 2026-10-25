# Upgrade from phase 1 to phase 2

Baseline: the supplied `0.1.0-phase1` archive, not an assumed remote Git branch. This is a complete source archive, not a binary patch. No phase-1 files are intentionally deleted; see the alphabetical inventory for exact changes.

If you have not run phase 1, extract phase 2 and follow the normal setup guide. You do not need to install phase 1 first.

For an existing local installation, stop it with `scripts/stop.ps1` (or `bash scripts/manage.sh stop`). Preserve your original project folder, `.env`, and database data; take a verified operator backup before migrating anything important. Compare any local code edits before replacing source files. Copy the new `contribution-ledger/` contents into the existing project directory, without replacing `.env`. No local settings file is shipped. The Compose project name remains `contribution-ledger`, so the named volume is reused.

Start normally. The startup script explicitly runs Alembic forward to `0002_accounts_access`. The applied `0001_foundation` file is byte-for-byte unchanged. The new migration adds 11 tables, constraints/indexes, an audit immutability trigger, and one empty installation-state row. It does not create a user, overwrite the persistence marker, or reset the database. The marker remains optional and synthetic.

Run `scripts/setup-owner.ps1` to generate the first-owner token, then finish setup in the browser. Stop/start must preserve that owner. Re-running setup-token after setup is refused; use audited recovery for a lost password. Normal startup never generates a new setup/recovery token.

The web proxy now forwards bounded JSON mutations and same-origin cookies instead of allowing only reads. Compose derives the exact allowed origins from `CL_WEB_PORT`, so a changed local web port remains usable. Continue to use the same host spelling (localhost or 127.0.0.1) during a session; cookies are host-specific.

Do not run `docker compose down -v`, delete the data volume, downgrade migrations, or change `.env` database credentials as a troubleshooting shortcut. Alembic downgrade removes phase-2 tables and therefore is not a safe rollback for account data. Restore a verified backup into a separate environment when necessary.

Actual PostgreSQL upgrade, Docker startup and PowerShell execution were not performed in the delivery environment. Their test commands remain included and their acceptance status remains open.
