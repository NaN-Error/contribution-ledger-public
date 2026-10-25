## Direct local private reads in 0.17.7

Enter links first, choose repository access, and confirm the read. **Find repository
activity dates** fills a suggested latest year without creating a report. Empty
history leaves the dates unchanged; current-day periods stop at analysis request
time. Multiple repositories share one period, so projects active in different
years may need separate reports. Analyze repositories captures activity and
source-cited draft summaries. Units and monetary scenarios still require explicit
human proposals and independent acceptance.

Connect GitHub within the input section for private links. The personal Windows
package initializes protected credential storage automatically. Other local
installations explicitly set `CL_REPOSITORY_PRIVATE_READS_ENABLED=true`, separate
`CL_REPOSITORY_CREDENTIAL_ROOT` and `CL_REPOSITORY_MASTER_KEY_FILE`, exclusively
loopback hosts/origins, then run `python -m app.cli init-repository-credentials`.
Remote/production direct token collection is rejected. No token belongs in chat,
source control, URL parameters or release packages.

Connections belong to their owner and project and expire locally after 30 days.
A token may expire or be revoked sooner on GitHub. Reconnect/update the selected
links before retrying a failed capture. Disconnect removes local ciphertext after
commit but preserves reports; revoke a GitHub token separately if needed. The CLI
path uses the recorded account and does not persist its token. Captured private
drafts are visible to project administrators/reviewers; contributor sharing still
requires an explicit exact review. No private source is sent to an AI provider.

Keep both GitHub credential/master directories in coordinated private operator
backups when using saved tokens. Never initialize a new master over ciphertext;
restore the retained pair or deliberately reconnect. Existing automatic credit,
paid provider, financial and public deployment boundaries are unchanged.

# Repository contribution dashboard

The requested goal is a repository-first application: add GitHub links, analyze several repositories within projects, explore each contributor and their username, include non-code/manual work, show explained units/shares/monetary scenarios, and drill into related evidence. The implementation is verified for fictional local acceptance; this document records its workflow, executed evidence and practical limits.

## Current workflow

1. Start the local application and sign in. Repository dashboard is the default signed-in entry point. Select a workspace and project, or create another project on that screen.
2. Expand Add repositories or refresh analysis. Paste public HTTPS GitHub repository links, choose a UTC period (exclusive end), and confirm the source read. Public reads need no account credentials. For private repositories in the personal Windows package, enter links, expand Connect GitHub, and use an existing GitHub CLI login or a fine-grained token. Choose only selected repositories with read-only Contents, Issues, Pull requests and Metadata. Then select Connected GitHub account. Configured team installations can still use completed GitHub App imports.
3. Choose Analyze repositories. The open browser advances persisted checkpoints. Pause capture stops new requests; Continue analysis resumes. Failures preserve progress, expose their code/retry time, and offer retry, partial completion or cancellation. Closing the browser does not complete an unfinished report automatically.

   The initial dates cover only the last 90 days, and each report permits up to
   366 days. A repository whose work predates the selected window can produce a
   completed context-only report with zero contributor sources. The dashboard
   now states this explicitly, keeps the input open and, for newly captured
   reports, offers **Use latest year of repository activity**. That button changes
   the dates/links only; confirm and analyze again. Old snapshots are preserved.
   Multiple repositories share one period; capture bounds still apply.

4. Open a contributor card, then a contribution outcome and its supporting evidence. GitHub usernames are project-specific drilldowns. Saved report selectors preserve old source snapshots. Repository display filters keep the project denominator.
5. Propose outcome units and explicit attribution with a rationale. No commit/line-count unit formula is applied. Incomplete attribution leaves unassigned units and money visible. Use Correct contributor identities for verified aliases, not merely matching display names.
6. Add an extra contribution for artwork, design, audio, planning or other missing work. Choose an observed contributor or add a manual person. Record its date, evidence and proposed units. Only entries inside the selected report period contribute to that report scenario.
7. Enter a hypothetical distributable USD amount. Draft estimates use proposed units; approved credit remains separately grouped by policy and contribution pool. Every cent reconciles, including unallocated amounts. Financial operations remain synthetic-only.
8. Manage extra contributions to correct entries, exclude or restore them with reasons, and inspect preserved entry history. Editing an excluded entry keeps it excluded. Identity corrections can explicitly link an observed GitHub account to a current local member; names/emails are never matched automatically.
9. As administrator, preview the exact report for sharing. Inspect included profiles, evidence excerpts and repository context, confirm permitted disclosure to current project members, and give a reason. Share the resulting address manually. Members sign in to browse fixed profiles/outcomes/evidence. Excluded work, correction history and raw imports stay outside that snapshot. Later edits need a new snapshot; revocation stops in-app access while retaining history.

10. To recognize credit, define/approve a historical scope and exact budget allocation. Open an outcome and choose Prepare this contribution for human review. Inspect its precise sources/limitations, map each identity to a current participant or context only, confirm project sharing, select the exact allocation and enter measurable criteria. Save the retrospective draft; planning approval/start/submission, independent reviewer assignment/decision and separate credit finalization follow in the ordinary package screens. The dashboard profile compares approved credit using explicit mappings and full policy/pool denominators. Reopen its preserved package from the outcome. Analysis categories testing/audio map visibly to existing policy qa/art.

## Complete goal requirements and evidence

| Requirement | Current implementation/evidence | Verified scope and limits |
|---|---|---|
| Paste repository URL and view a report before budgeting | Public checkpoint capture and saved reports; injected two-repository API/browser checks; actual anonymous `octocat/Hello-World` capture completed | Window/pagination/context/source/request-bound tests pass; capture remains explicitly bounded |
| Several repositories per project and several projects | Eight inputs/report, project selector, native persisted snapshots, browser project-isolation check | Eight-input bound, preserved retry/backoff and explicit omitted evidence; larger captures require another bounded report |
| Meaningful source-cited summaries | Contributor-specific authorship/review/discussion highlights; cited goal/status/file/review findings and context/overlap limits | Optional approved assessments can follow the ordinary review transfer; no model quality claim |
| Contributor names/usernames and aliases | Numeric IDs, profiles, explicit local-member identity links, reviewed shared snapshots and current-member reads | Explicit recipient/context mapping verified in API/native/browser transfer |
| Manual extras and imported contributor selection | Intake, correction, reasoned exclusion/restoration and actual-entry history; UTC period preservation | Pinned aware manual date/evidence and retained corrections verified during ordinary review transfer |
| Explained units, project shares and money scenarios | Versioned rubric, rationale/attribution, exact cents, stale evidence exclusions, unassigned amounts | Rendered independent acceptance/finalization and contributor approved-credit comparison pass |
| Click overview → contributor → outcome → evidence | React drilldowns, reloadable profile/outcome links, mobile browser checks | Basic keyboard activation, browser history, reload/login and 390px panel bounds pass; broader assistive-technology testing remains external |
| Integration setup, scoped access and persistence | Source permissions, leases/cancel/version/backoff tests; native populated 0014 upgrade and immutable guards; retained practice through 0017 with all 97 preexisting tables/private files unchanged | Complete 1,387-pass backend CI, current frontend/browser/recovery/Docker and operator/user guides reconciled; fictional owner acceptance remains |

## Run the new checks

With the pinned Python/Node dependencies and the frontend built:

```text
cd apps/api
python -m pytest tests/test_repository_analysis.py tests/test_analysis_sharing.py tests/test_analysis_handoff.py tests/test_migrations.py tests/test_process_model_registration.py -q
```

For native checks, configure `CL_TEST_DATABASE_URL` to a disposable loopback PostgreSQL database ending in `_test`, then run `tests/test_postgres_analysis.py`. Each native test uses its own schema. Never use the practice/user database for these tests.

For the complete rendered fixture workflow, set development tools, disabled live integrations, a disposable loopback `_test` database, installed Chromium and `CL_E2E_ALLOW_ANALYSIS_FIXTURES=1`, then:

```text
python tests/e2e/repository_analysis_acceptance.py
python tests/e2e/analysis_handoff_acceptance.py
```

This creates a new schema/private `.local` directory, starts temporary loopback servers on 18003/15176 or 18005/15178, captures screenshots/results and stops those servers. It uses injected GitHub responses. Passing it is not a live private-repository test, paid-provider validation or a human pilot.

## Upgrade boundaries

Back up the existing database and retain evidence/credential/MFA stores and their masters. Stop application writers, run the existing explicit migration command, and restart the application. Head is `0019_repository_read`; applied migrations 0001–0018 remain unchanged. The retained practice instance is at its separately recorded head; the personal Windows upgrade adds 0019 without resetting accounts or reports. Restricted staging operators must review/reprovision API grants for the added tables. AI workers receive no new report/ledger/finance authority. Do not reset accounts, replace masters or restore into the original deployment merely to test this feature.

## Selected-period evidence

Recent reviews and discussion on older parent threads are included within the capture bounds. Parent context alone creates no contribution and its older authorship is excluded from in-period attribution. Evidence cards show captured timestamps in UTC and later-edit caveats; current text/status is not a reconstruction of historical text. At most three parent pages and one child page are fetched, so visible omissions must be reviewed. Manual evidence days use UTC while retaining the original aware instant. See the repair record (local output omitted; see docs/test_results.json).

## Completed implementation verification

The October 4 application checkpoint passed its full developer collection and recovery/browser checks. For the current private-read review, see `test_results.json`. See complete verification (local output omitted; see docs/test_results.json) for counts, tested commit, platform scope, archive audit and separately required user/live checks.
