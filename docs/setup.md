> **Current phase 13:** Source `0.13.0-phase13`. Read `upgrade_phase13.md`, `finance.md` and `testing_phase13.md` for financial records; `project_status.md` and `test_results.json` are the current executed/deferred verification record. Existing owners do not repeat setup. Preserve database, evidence and configured credential/master volumes. All financial records remain synthetic-only. Older walkthroughs below are retained for earlier features, not claims about the current migration or verified readiness.

> **Phase-11 update:** For evidence assessments and current upgrade steps, read `ai_assessments.md` and `upgrade_phase11.md`. Old protocol-only profiles remain unchanged. New runs need separate disclosure/payer approvals, and existing AI worker grants must be refreshed. Current executed/deferred checks are in `test_results.json`.

# Earlier integration setup notes (retained)

Phase 8 originally introduced source `0.8.0-phase8`; it is not the current version. For the optional GitHub profile read `github_setup.md`, `github_imports.md`, `upgrade_phase8.md` and `testing_phase8.md`. The original manual commands below still apply with GitHub disabled. Stop an explicitly enabled GitHub worker separately using `scripts/github.ps1 -Action manual` before returning to base-only operation. Tests not listed as executed in the latest release remain pending.

# Local setup

## Prerequisites and first startup

Use Docker Desktop with Linux containers and PowerShell on Windows. Extract the ZIP into a normal working directory, then open PowerShell in `contribution-ledger` beside `compose.yaml`. Docker installs Python/Node dependencies inside the images; host Python/Node are only needed for native development and test commands. The first build needs working package registries and image downloads.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-owner.ps1
```

The process-only execution-policy argument does not change saved machine policy. Follow your organization’s restrictions on managed devices. `doctor` checks Docker/Compose and Linux-container mode. `start` initializes `.env` only if absent, builds images, starts PostgreSQL, explicitly migrates forward, and starts the API/web services. It does not seed accounts or reset anything.

Open `http://127.0.0.1:5173`. Use the token printed by setup-owner within one hour. Choose an email, display name, unique 15–128 character passphrase, workspace, project and IANA timezone. No email service is required. Setup works once. There is no hardcoded application password. The generated database password in `.env` is a different secret.

## Existing installation and planning workflow

An existing owner signs in normally after upgrading; do not run setup-owner again. Follow `upgrade_phase13.md` to preserve `.env`, all configured volumes and earlier migration files. Current migration head is `0013_financial_distributions`; the following earlier-phase walkthroughs remain feature examples.

Open Workspaces → workspace → project. Policies opens by default; Milestones holds planning budgets, and Settings and access retains the existing project controls. `policies_and_budgets.md` explains approval, acknowledgement, reserve and amendment behavior. No policy or budget is seeded automatically.

## Common commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\logs.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-team.ps1
```

Stop preserves the named database volume. `seed` creates one idempotent synthetic persistence marker; inspect it after sign-in in System overview. `seed-team` is optional, requires explicit confirmation and development tools, and creates isolated fictional team accounts. It prints random passwords once, never on ordinary startup. `reset-development.ps1` removes only the marker, never accounts or access history.

Linux/macOS equivalents: `bash scripts/manage.sh doctor`, `start`, `setup-owner`, `stop`, `logs`, `seed`, `seed-team`. Operator account commands are documented in `account_access.md`.

## Ports, origins, and local privacy

The web port defaults to 5173 and API to 8000. Both bind only to 127.0.0.1; the database has no published host port. To change a local port, edit its value in the existing `.env`, then stop/start. Compose derives the two allowed browser origins from the configured web port. Cookies for localhost and 127.0.0.1 are separate: keep one spelling. Invitation URLs inherit the current local browser origin and keep the one-time secret in a fragment that the UI removes after reading.

The API expects unsafe browser requests to include JSON, a permitted Origin, and the current X-CSRF-Token from a browser session. CORS is not enabled. Supplied API launch commands use `--no-proxy-headers`; keep that flag for native development so client headers cannot replace the peer address used for rate limiting. Using Swagger’s write buttons directly at port 8000 is not the supported account workflow; use the web app or the documented API protocol. Health/system diagnostics remain public on the loopback interface and contain technical status and a synthetic marker, not team records.

Never commit or share `.env`, setup/recovery tokens, invitation links, or passwords. The delivered source contains only synthetic test constants. Do not enable public tunnels, open router ports, or add private repository artifacts. Remote deployment is intentionally blocked pending phase 14.

## Troubleshooting

A download/build failure is not a database failure. Retain the output without secrets; dependency locks still await a clean network-backed verification. Do not delete locks or float versions to make an installation appear successful.

For an unavailable API, inspect service status and sanitized logs. For a migration-required message, rerun normal startup so the migrate service executes. For an invalid setup token, run setup-owner again before setup is complete; it invalidates the old token. After setup, use recovery instead. For a stale CSRF message, reload and review the form before resubmitting; writes are not automatically retried. Repeated failed sign-ins are limited per email and peer in 15-minute windows. The trusted local proxy shares a peer bucket; X-Forwarded-For is not trusted.

For a version-conflict message, refresh and review the latest record before editing again. For no visible projects, a workspace member may need an explicit project grant. A workspace admin's inherited access is not removed by changing an explicit project grant. See `account_access.md` for suspension and recovery behavior.

For policy or budget blockers, inspect participant acknowledgements and effective time. A stale amendment needs a new preview; repeated clicking cannot approve an outdated proposal. Units in reserve are unavailable until an explicit budget amendment. Missing contributors cannot be bypassed by deleting history.

Stop/start keeps data but is not a backup. Use an actual backup/restore procedure before important migrations; complete operational backup tooling is scheduled for phase 14.

## Work-package guidance

The new Work packages tab binds scopes to approved allocations; it does not accept evidence or issue credit. See `work_packages.md` for the workflow and `upgrade_phase4.md` before replacing an existing installation. A submitted scope must be withdrawn or returned for changes before editing. An amendment needs fresh planning approval.

## Phase-5 artifact storage

Upgrade guide: `docs/upgrade_phase5.md`. The default API now has its own persistent `evidence_data` volume; the web service does not mount it. Preserve this volume together with `postgres_data`. Normal stop/restart does not delete either. Native API startup should set `CL_OBJECT_STORAGE_ROOT` to a private absolute path; relative `.local/evidence` is based on the API working directory. No S3/API key is required. Missing store access is reported by evidence operations, not inferred from the database health card. See `docs/storage_operations.md` before changing backends or retiring bytes.

## Phase 7 simulator

Read `upgrade_phase7.md` for an existing installation and `revenue_simulator.md` for the current workflow. Sign in normally; no AI/GitHub credentials or account reset is required. Preserved examples are hypothetical only.

## Phase 10 continuation

The current source is 0.10.0-phase10. Follow `upgrade_phase10.md`, `ai_connections.md`, `ai_operations.md` and `testing_phase10.md` for optional synthetic AI setup. Normal startup requires no AI key. Only explicit operator/payer opt-in permits a potentially billable synthetic probe; actual evidence assessment remains phase 11. New `ai_credentials` and separate `ai_master` volumes require protected consistent recovery. All earlier unexecuted native/build/browser/live checks remain open.
