# Upgrade to phase 5

Baseline: actual `0.4.0-phase4` source archive. Target: `0.5.0-phase5`. This is a full source delivery, not a prebuilt installer. User testing remains deferred; these are instructions for later verification.

## Preserve before replacing

Stop the existing API/web normally. Preserve your `.env`, current source edits and database volume. Preserve any existing artifact store and operator credential configuration; never copy private data into a source ZIP. The application now adds the named `evidence_data` volume. Back up both database and artifacts once evidence exists. Do not use `down --volumes`, delete Docker volumes, reset accounts or recreate the owner during an upgrade.

Extract the new complete `contribution-ledger/` folder into the same deployment location after saving local changes. Keep the same Compose project name. This release intentionally deletes no baseline source paths. Compare `docs/file_changes.md` before replacing user-modified files. No `.env`, real credentials, database contents, uploads, dependencies or built frontend are included.

## Start / forward migration

With Docker Desktop running Linux containers, open PowerShell in the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Startup rebuilds images with the committed dependency manifests and applies `0005_manual_evidence`. Migrations `0001_foundation`, `0002_accounts_access`, `0003_policies_budgets` and `0004_work_packages` are unchanged. The new migration adds five tables, scoped references, indexes and immutable-history guards; it does not seed accounts, add example evidence, reset anything or issue units. A nonempty phase-5 downgrade refuses to drop its history.

Open `http://127.0.0.1:5173` and sign in normally. Only a fresh installation uses `scripts/setup-owner.ps1`. The default private artifact volume needs no external key or GitHub configuration. First builds require network access to container images/package registries, including newly pinned Pillow and boto3 dependencies.

The previous Compose image labels still said phase 2 even in later source deliveries. They are now corrected to phase 5; the Compose project and volume names are preserved. Do not remove old images/volumes until preservation checks pass.

## Confirm after upgrade

Check the system's migration state, existing workspaces, policy versions, milestone totals, package revisions and archived submissions. Pre-phase-5 declarations retain their exact original evidence-free payload. They display an earlier-submission warning rather than being silently backfilled.

Open a non-cancelled synthetic package and add a small text/image artifact. Verify its snapshot and original download. Restart/recreate API and web containers **without deleting volumes**, log back in, and check identical original hashes and packet history. Native read-only-container ownership behavior, PostgreSQL locks and Windows execution remain untested here and must pass locally.

Use `docs/evidence_and_artifacts.md` for the full walkthrough. No submission or upload changes issued credit. Approval/dispute/award workflows arrive in phase 6.

## Failure recovery

Read sanitized API logs and request IDs. A storage failure does not justify changing permissions globally, placing artifacts in the webroot, resetting the database or deleting a volume. Check that the API-only private volume is mounted and writable by the configured user. An old database with a new model needs the forward migration; a new database with an older source must not be forced to drop recorded evidence.

A failed React typecheck/install should be corrected using visible dependency/source changes rather than deleting locks and floating versions. Clean network-backed installation, native PostgreSQL, Docker, PowerShell, full React and browser acceptance remain explicit open gates. Keep synthetic localhost-only use until these are resolved.
