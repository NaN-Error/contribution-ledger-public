# Upgrade from phase 12 to phase 13

Baseline: complete `0.12.0-phase12` archive. Target: `0.13.0-phase13`, migration `0013_financial_distributions`. No existing source file is intentionally deleted. Applied migrations 0001–0012 are unchanged.

Preserve your actual `.env`, `postgres_data`, `evidence_data`, configured `github_secrets`, and separate `ai_credentials`/`ai_master` with protected recovery material. Financial supporting documents use the existing private evidence storage; no new credentials, dependency versions or storage volumes are required. A database-only backup is not a complete artifact/key backup. Full coordinated backup/restoration implementation is phase 14 and still needs testing.

For an existing local installation, stop optional integration workers before replacing source. The normal startup helper stops the known optional overlays before applying migrations. Do not delete Docker volumes, reset the database, recreate the owner, or edit old migration files. Put the supplied files under the same `contribution-ledger/` root, retaining local configuration not present in the ZIP.

From PowerShell in that root, with Docker Desktop running Linux containers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Open `http://127.0.0.1:5173` and sign in normally. A fresh database only still uses `scripts/setup-owner.ps1`. Source changes alone never create a finance period, disclosure, accepted award, paid provider request, close or transfer declaration.

The additive migration creates eleven finance tables and immutable-history guards. It does not convert old simulator examples or historical opening archives into distributions. Existing account, evidence, credit and integration records remain in their earlier tables. In populated phase-13 installations, destructive downgrade is deliberately refused. Recovery from a failed upgrade may require an operator-controlled restored copy, not forcing a downgrade through history guards.

Optional AI/GitHub deployments follow their existing reviewed setup and restart procedures. AI grants are not expanded to finance tables. No bank credentials or payment-provider integration exists. All phase-13 finance records remain synthetic-only even when GitHub/AI are separately enabled.

Read `finance.md`, `finance_api.md`, `testing_phase13.md`, and ADR 0014. Verify readiness reports 0013, inspect the former accounts/awards/scenarios, then use a disposable synthetic project for financial testing. A calendar month must be finished before closing; do not backdate real contribution records to bypass that rule.

Remaining installation/native/browser/Windows/security checks are documented in `project_status.md`. This package is source, not a prebuilt installer or production authorization.
