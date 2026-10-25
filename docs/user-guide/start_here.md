<!-- portable-2026-10-07 -->
# New personal Windows users: extract and double-click Start.cmd

The **complete Windows x64 package** includes the app and its Python/Node/PostgreSQL
runtimes. Extract all files, double-click Start.cmd and paste your public repository
link in the dashboard. No signup, setup-code copying, Docker or developer command
is needed. A missing Microsoft C++ runtime opens verified official setup once for
approval. Stop.cmd keeps your saved projects. See [package details](../portable_windows.md).

The separate **developer source ZIP** and existing team installations use the
account/Docker instructions below. Personal startup never adopts an existing team
owner. Version 0.17.5 adds migration 0018; preserve all original volumes/masters
when deliberately upgrading an existing installation.

<!-- portable-2026-10-07-end -->
# Start here: the internal test candidate

Version **0.17.4-phase17** adds the repository dashboard to the installed 0.16.2 foundation. Select a project, paste public repository links, explore contributor/source reports, add manual extras and calculate draft scenarios. The repository-first implementation and developer verification are complete; fictional owner acceptance remains; see [the workflow and requirement tracker](../repository_analysis.md). Complete Linux regression/recovery and current Windows API/native/rendered desktop/mobile checks have executed. This is a verified synthetic-only test candidate, ready for fictional owner acceptance.

You do not need to install or merge all earlier ZIPs. This archive contains the entire `contribution-ledger/` directory. Older version-specific guides are retained for history; this page and `docs/project_status.md` describe the current checkpoint.

For a short first session, follow [First practice session](first_practice_session.md). If Codex has already prepared a local instance on your computer, use the supplied `Start-Contribution.cmd` and `Get-Setup-Token.cmd` beside its quick-start instructions. Those machine-specific helpers use already-installed native runtimes; they are separate from this portable source ZIP and its Docker route.

## Fresh Windows installation

1. Extract the ZIP into a normal writable folder, for example `C:\Projects\contribution-ledger`. Do not run it from inside the ZIP. Avoid a folder synchronized to a shared cloud drive when storing local secrets and test data.
2. Start Docker Desktop in Linux-container mode. The documented Docker route does not require installing Python, Node.js or PostgreSQL directly on Windows. Its first build needs internet access to download the pinned packages and images.
3. Double-click `Start-local.cmd`, or open PowerShell in the extracted project folder and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

4. Only after successful startup, create the first-owner setup token:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-owner.ps1
```

5. Open `http://127.0.0.1:5173`, enter the token in the first-owner form, and create your own local account. Do not share the token or password in chat. No default password exists.
6. Sign in and open **Repository dashboard**. Select your project and add public repository links or manual extra contributions. Use fictional unit and money proposals. **Getting started** explains the separate policy, budget and independent-review workflow for approved credit.

Normal startup creates no owner, seed team, policy, contribution award, financial close or paid AI call. It does not delete a volume.

## Existing installation

Read `docs/upgrade_test_candidate.md` before replacing source. Back up and preserve `.env`, the database, artifacts and every configured secret/master volume. This checkpoint adds `0017_analysis_handoff` after 0015/0016; applied migrations 0001–0017 remain frozen on the retained practice instance. An installation older than phase 14 must also follow the phase-14 backup, PostgreSQL-image and MFA upgrade instructions.

Existing owners sign in normally. Do not generate another first-owner token, delete volumes, or run a reset to work around an upgrade problem.

## First useful test

Create a fictional team containing a contributor and a separate reviewer account. Review and approve a policy; each required participant acknowledges their own version. Create and approve a milestone budget, allocate work, define a work package with independently budgeted deliverables, attach evidence, obtain independent review and explicitly finalize only accepted portions.

Then inspect **Contribution overview** and **Revenue simulator**. The percentage denominator should stay visible. Unissued reserves and unfinished work are not personal credit. Test both accepted and insufficient-evidence cases.

Finally practice **Financial records** using fictional receipts. Inspect deductions, preview/approve a synthetic close, re-export it, and replay its JSON using the documented Python tool. An exported statement is not a payment, and an external transfer declaration neither sends nor independently verifies money.

A single human operating separate accounts is a software test only. Do not represent those accounts as a real independent-review pilot.

## Optional integrations come later in testing

The entire manual path works without GitHub and AI. After it is working locally, follow `docs/github_setup.md` for an authorized repository and `docs/ai_connections.md` for the synthetic provider. The synthetic model always answers insufficient; it tests the workflow, not quality.

Live source disclosure and paid AI generation remain separate explicit actions. Nobody needs to send API keys here. Unknown provider behavior, data terms and paid billing have not been verified in this delivery.

## Running automated checks

`Verify-local.cmd` or `scripts/test.ps1` builds the test images and runs their contained tests; it does not point tests at your saved application database. Native PostgreSQL/concurrency and real-browser tests have separately passed in CI; those tests require disposable fixture databases and explicit opt-ins, as recorded in the verification guide. Building the web image performs the React typecheck and Vite build; a failure there is a real installation blocker, not a cosmetic warning.

For a native development checkout with the Python and Node dependencies already installed, `python scripts/check_candidate.py` runs source verification, the synthetic calibration, backend fixtures, frontend helpers and the full web build. It never installs packages automatically or changes a running deployment. Reports go below ignored `.local/` by default. It strips `CL_` deployment configuration from child test processes. Skipped native checks do not become passes.

## When something fails

Keep the exact error text and the command that produced it. Record whether this was a fresh installation or an upgrade and which screen or workflow failed. Review logs before sharing: never attach `.env`, API keys, master keys, passwords, real private source, or a database dump.

Do not delete the database volume to solve a failed build. Do not replace a missing encryption master over retained encrypted records. The test checklist in `docs/user-guide/testing_checklist.md` and known limits in `docs/release/readiness.md` separate defects from intentionally unimplemented or disabled behavior.
