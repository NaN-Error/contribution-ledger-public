# Upgrade to 0.17.2-phase17 development checkpoint

This complete source adds repository dashboard migrations 0015/0016 and the additive **0017_analysis_handoff**. Dependency versions are unchanged from 0.16.2. Preserve accounts, source edits, evidence and every credential/MFA master. Stop application writers, take a coordinated backup, reconcile/rebuild the source, run `python -m app.cli migrate` from apps/api with the existing deployment configuration, and restart. Docker Start-local.cmd/scripts/start.ps1 perform the explicit configured startup/migration route. Do not repeat owner setup or reset data.

Native tests verified populated 0014/0015/0016 upgrades, repeated migrations, races and immutable history. The installed practice 0016→0017 upgrade also preserved all 97 existing table row digests and private files. Applied **0001–0017** on that instance are now frozen. Restricted staging requires reviewed API grants for the new tables; workers gain no report/ledger/finance authority. Current image tag is `0.17.2-phase17` and head is `0017_analysis_handoff`. See [the workflow](repository_analysis.md).

---

Retained previous upgrade checkpoint:

# Upgrade to 0.16.2-phase16

Baseline: supplied **0.16.0-phase16**. This complete candidate adds installed verification and targeted repairs. It is ready for fictional local testing. There is no new migration or persistent volume; head remains `0014_security_recovery` and migrations 0001–0014 are unchanged.

1. Preserve existing edits and take the coordinated backup described in `docs/runbooks/backup_restore.md` before replacing a running installation. Keep `.env`, `postgres_data`, `evidence_data`, configured `github_secrets`, `ai_credentials`, `ai_master` and `auth_master`. A database dump alone is incomplete.
2. Stop the existing API and optional writers using the documented operator scripts. Reconcile local edits with the alphabetical changes list; the source ZIP contains no private configuration or retained data.
3. Replace the source files and rebuild using `scripts/start.ps1` or `Start-local.cmd`. The image tag changes to 0.16.2-phase16. Exact Python security updates and Python 3.13.14 require a rebuild or fresh native dependency installation; see ADR 0017. Frontend dependency versions are unchanged, with completed integrity records.
4. Sign in with the existing owner. Do not repeat first-owner setup, delete volumes, replace retained encryption masters or reset accounts. Optional GitHub/AI workers remain explicitly enabled; an upgrade does not authorize a connection or paid request.
5. Check health, protected evidence, existing histories and the fictional workflow in `docs/user-guide/testing_checklist.md`. Keep failures and exact commands visible; use coordinated restoration into a new isolated destination when required.

Populated native PostgreSQL upgrade/repeat-upgrade checks passed. Actual Docker startup/restart and isolated recovery passed in Linux CI, with Windows native/browser checks recorded separately. Windows Docker Desktop operator execution remains for a machine with Docker Desktop installed; every PowerShell script was syntax-checked here. The completed React build no longer has the inherited missing-module blocker.

For an installation older than phase 14, also follow `docs/upgrade_phase14.md`, including its PostgreSQL patch and MFA-master requirements. Existing migration history must never be edited to bypass an upgrade problem.

`python scripts/verify_release.py` checks the delivered listed source bytes and ignores private local files. `.gitattributes` preserves those exact bytes across Git checkouts. Legitimate local edits must be reviewed as edits, not hidden by rewriting the manifest. No source path was deleted in this patch.

No upgrade step approves policies, discloses packets, awards contribution credit, closes financial periods, sends money or completes a human pilot. Finance remains synthetic-only.
