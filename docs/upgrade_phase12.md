# Upgrade to phase 12

**From:** the full phase-11 source (`0.11.0-phase11`). **To:** `0.12.0-phase12`. Keep this development build localhost-only and synthetic. User, native, installed-browser and security acceptance remain open.

## Preserve before replacing source

Back up according to the existing guides and preserve `.env`, `postgres_data`, `evidence_data`, any configured `github_secrets`, and both `ai_credentials` and the separate `ai_master`. The ZIP contains no private data. A database backup alone cannot restore artifacts or encrypted key storage. No new volume or credential is required in phase 12.

Stop the running application/optional workers, replace source under the same `contribution-ledger/` root, and retain the private files/volumes. Do not run `docker compose down -v`, do not reset, and do not create another owner on an existing installation. No old source path is intentionally deleted; the complete alphabetical inventory accompanies this delivery.

Normal upgrade/start from the extracted root with Docker Desktop running Linux containers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The startup script stops optional workers before migration. It applies the new additive migration `0012_historical_reconstruction`. Migrations 0001 through 0011 are byte-for-byte preserved. Six tables are added; no account, award, evidence, provider profile or simulation is reset. A nonempty reconstruction downgrade is refused rather than deleting history.

Open `http://127.0.0.1:5173` and sign in with the existing account. The system status should identify source phase 12 and the 0012 migration head. The existing AI initializer now checks the current migration head instead of incorrectly requiring 0011. It grants no reconstruction or ledger access to the AI worker. Existing synthetic optional AI deployments can use their established `scripts/ai.ps1 -Action init` / `-Action start` workflow. All live/paid/evidence flags remain unchanged and false by default.

No new runtime dependency versions are introduced. The inherited frontend/Python/jobs locks still need clean artifact installation validation; this source archive is not a prebuilt Windows program or verified Docker image.

## First synthetic inspection

Open Historical review and Contribution overview. Existing projects without historical batches should have honest empty states, not fake percentages. A current approved empty milestone can host a new batch. Follow `reconstruction.md`: define historical scope, review baseline, group captured history or add non-code work, allocate planned units, promote to ordinary packages, independently review and finalize, then archive the explained opening balance.

The older normal work-package creation selector excludes historical reserved allocations; create those packages through the historical batch. Individual accepted awards already exist before opening archival. A frozen historical archive is not phase-13 release economics, payment or legal ownership. Pending reconstruction and separately accepted work may still change current contribution shares.

If any migration, install or browser step fails, preserve logs with secrets removed and stop before entering real contributor data. The project status keeps earlier unresolved checks; generated source alone does not satisfy them.
