# Upgrading to phase 11

Baseline: complete `0.10.0-phase10` source. Delivery: full `0.11.0-phase11` source, not a patch or executable installer. Preserve local edits, `.env`, `postgres_data`, `evidence_data`, configured `github_secrets`, and both `ai_credentials` and separate `ai_master`. Verify a backup covering database, artifacts, credentials, master and configuration before changing a real installation. A database-only backup is incomplete.

Stop optional workers before migrations. The supplied normal startup scripts already do this. Extract/merge the full source into the existing `contribution-ledger` folder without deleting volumes or replacing private configuration. No prior source path is intentionally removed in this phase.

## Manual-only operation

With Docker Desktop running Linux containers, from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Existing owners sign in normally. No owner recreation, data reset or new provider connection is required. Normal startup makes no assessment request. Linux equivalent: `bash scripts/manage.sh start`.

The new additive migration is **0011_ai_evidence_review**. It creates six sealed assessment/history tables, adds a scoped assessment-plan link and kind to the existing AI job table, and adds a boolean-only native freshness function. Applied migrations 0001–0010 are unchanged. Existing jobs, profiles, prices, events, contributions and simulations remain preserved. A populated downgrade is refused; restore a verified backup rather than forcing history deletion.

## An existing AI deployment must refresh its grants

The previously provisioned AI worker lacks phase-11 access. Re-run the existing initialization explicitly; it preserves existing encrypted storage/master/password and re-provisions the known worker role with the additional narrow grants after migration. This is also the setup for a first synthetic AI deployment:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action init
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action start
```

Linux equivalents: `bash scripts/ai.sh init` then `bash scripts/ai.sh start`. Use `-WithGitHubSync` / `--with-github-sync` only for an already configured combined integration setup. Initialization contacts no model/provider, does not recreate a master, and refuses to adopt an unrelated privileged database role. The startup overlay may need internet access to obtain already pinned dependencies/images; clean installation is still unverified here.

Do not merely restart an old worker binary against a migrated database. Do not bypass missing grants by giving the evaluator superuser or ledger-write access. Check logs and status after re-provisioning. The native role operation is supplied but not executed in this environment.

## No automatic evidence authority

Existing phase-10 profiles contain pending evidence prompt/schema identifiers. They remain historical protocol configurations. Create a fresh evidence-review profile after a current compatibility probe, review it, and explicitly approve it. Its approval alone neither discloses data nor authorizes billing.

The new setting `CL_AI_EVIDENCE_ENABLED` defaults to false even when omitted from an existing `.env`. Keep all live/paid/evidence flags false for synthetic testing. Enabling evidence requires the earlier live and paid-generation flags, a permitted provider/data arrangement, exact per-plan administrator disclosure approval, and separate payer consent. This delivery made no live or paid request.

Inspect `docs/ai_assessments.md` and `docs/testing_phase11.md` before intentionally changing those flags. There is no public hosted credential-collection authorization, automatic outgoing source analysis or automatic model fallback.
