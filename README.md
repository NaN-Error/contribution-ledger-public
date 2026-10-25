# Contribution Ledger

A local dashboard for understanding contributions across GitHub repositories,
adding missing non-code work, and reviewing outcome-based contribution proposals.

**Experimental release 0.17.8.** Contribution values are explained proposals;
accepted credit requires human review. Financial calculations are hypothetical
and synthetic. The application does not move money or determine anyone's worth.

## Start on Windows

1. Open [Releases](https://github.com/NaN-Error/contribution-ledger-public/releases).
2. Download **contribution-ledger-0.17.8-windows-x64.zip**, extract the whole ZIP,
   and double-click **Start.cmd** inside the extracted folder.
3. In the dashboard, paste a GitHub repository link and confirm the read.
4. Choose **Find repository activity dates**, check the dates, then choose
   **Analyze repositories**. Open a contributor, contribution, and its evidence.

The Windows package bundles Python, Node and PostgreSQL. No Docker, terminal
commands or signup are needed. If the Microsoft C++ runtime is missing, the
launcher opens verified official setup for your approval. First startup can take
several minutes. **Stop.cmd** stops the app and keeps your data.

GitHub's **Code → Download ZIP** contains developer source, without the bundled
runtimes. Use the Windows release ZIP for double-click startup.

## Public and private repositories

Public repositories need no GitHub login. For private repositories, enter the
links, expand **Connect GitHub**, and choose an existing GitHub CLI login or a
fine-grained token limited to selected repositories. Grant read-only Contents,
Issues, Pull requests and Metadata. Tokens are encrypted locally; CLI tokens
remain in memory. You can disconnect while retaining saved reports.

Analyze up to eight repositories per report. The initial period is only the last
90 days; older work needs earlier dates. Each report covers at most 366 days and
has visible capture limits. Keep the browser open while capture runs, or resume
it later. Repository code is never installed or executed.

## What you can explore

- Project and repository overviews, contributor usernames and source-cited summaries.
- Contributor → contribution → evidence drilldowns and saved reports.
- Manual contributions for design, art, documentation and other missing work.
- Explicit proposed units, attribution, and exact hypothetical money scenarios.
- Independent review, recorded corrections and scoped report sharing.

No AI key is needed for repository reports. Optional AI assessments require
separate provider, disclosure and spending authorization; AI cannot award credit.

## Your data stays separate

The Windows package creates personal state under
`%LOCALAPPDATA%\ContributionLedger\Personal`. Keep that folder private. It holds
your database, captures, credentials and encryption masters. Back up those stores
together. Never upload it, screenshots of private reports, or a ZIP of an existing
installation. The source repository and release packages contain no user database
or captured personal test reports.

## Developer setup

Use Python 3.13, Node 22 and Docker Desktop with Linux containers. From this source
checkout, run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1`
and open `http://127.0.0.1:5173`. For a fresh team database use the documented
owner setup in [start here](docs/user-guide/start_here.md). Preserve existing
data volumes and read the [upgrade guide](docs/upgrade_test_candidate.md).

Migration head is **0019_repository_read**. Applied migrations are immutable.
See [Windows details](docs/portable_windows.md), [repository workflow](docs/repository_analysis.md),
[security](SECURITY.md), and [release readiness](docs/release/readiness.md).

This is a local test candidate, not a public hosting or real compensation product.
Clean Windows VM acceptance, independent security/load review, real-model quality
and a human pilot remain separate. Automated results are scoped in
[test results](docs/test_results.json); Actions shows fresh public CI results.

## License

[MIT](LICENSE). Bundled runtimes and dependencies retain their own license notices.
