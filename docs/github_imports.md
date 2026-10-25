# GitHub imports and evidence semantics

## Scope and date interpretation

Connect one or more explicitly authorized repositories to a project. In the GitHub Imports panel, select a repository, an increasing timezone-qualified range of at most 366 days, the number of root entities to consider per type, and the data-request budget. The end is exclusive and cannot be in the future. The UI converts its local datetime inputs to qualified instants before submission.

Pull requests and issues are selected by creation date in `[start_at, end_before)`. Commits are selected by committed date on the default branch anchored at its observed head SHA. PR-associated commit metadata is also fetched. This is not a crawl of every branch, deleted reference or historical state. Repository identity is checked before accepting content; renames/transfers require reconnection rather than following a redirect to a different resource silently.

The import preserves `requested_as_of`, actual observation time, default-branch anchor, source revisions and omissions. A PR created in the range may have changed later. Its fetched current representation is labeled as observed now; current comments, reviews and checks do not magically become historical snapshots. A post-cutoff update is a visible limitation, not silently discarded. Re-import a bounded interval to collect a newer version; recurring reconciliation is phase 9. Deleted/inaccessible history may remain unavailable permanently.

## Bounded collection

| Limit | Current implementation |
|---|---|
| Root entities | Configurable 1–200 each for PRs, issues and branch commits |
| Data requests | Configurable 10–1,000 per run; failed reserved requests still count |
| Root pagination | At most 20 pages of up to 100 items per type |
| Child pagination | Normally at most five pages per child collection |
| PR commit metadata | At most three pages; reported API cap of 250 is flagged |
| PR changed-file pages | At most 10 pages / 1,000 entries, stricter than GitHub's maximum |
| Fetch tasks | At most 5,000 per import |
| One response | 2 MiB JSON maximum; oversized responses are not trusted |
| Normalized source | 512 KiB maximum per stored document |
| Project normalized-source quota | Default 128 MiB; configurable 1–512 MiB |
| Retained repositories / runs | At most 100 repositories and 500 runs per project |
| Concurrent active import | One per repository; atomic guarded creation |

The data-request budget does not include installation verification/token issuance requests. Each worker checkpoint obtains a current restricted token; total provider HTTP requests may therefore exceed the displayed data-request count. The source quota measures normalized source JSON, not indexes, identities, observations, WAL, backups or complete database disk use. Monitor actual storage separately.

Data categories include PR details, issue details, review decisions, discussion/inline comments, PR commit metadata, bounded file patches, default-branch commit details/files and check-run metadata. Pull-request files are bracketed by head/base checks; changed revisions cause that patch capture to be omitted rather than mixed with the older declared SHA. Check statuses are evidence of those checks, not proof that the whole game is correct. Binary/API-excluded/missing patches are explicitly absent; no byte count or line count becomes credit.

Known sensitive-path patches are omitted and credential-like text is redacted on a best-effort basis. This is not comprehensive secret detection, a malware scanner or a substitute for source-owner permission. Treat retained private source as sensitive even after redaction. Fetched content is displayed as text; repository scripts, binaries, builds, package installers, CI commands and code are never executed. No clone is performed.

## Durable processing and failure states

Creating an import writes its durable database record and outbox entry in one transaction. The separate phase-8 worker polls this outbox and runs fetch tasks. PostgreSQL records the lease, fencing token, task cursor, attempts, delay and committed observations. Network work happens outside long database transactions; current authorization and fence are checked again before saving the result. A process killed after fetching may fetch again, but source versions are content-deduplicated and observed separately.

Rate limits cause a recorded delay using server retry/reset information with bounded exponential backoff, not a tight loop. At most five attempts are allowed for a failing task/run path. Resume cannot override a not-yet-due delay. Permanent access errors, quota limits or malformed responses preserve already-captured evidence and show the reason. A completed job can still have omissions; `completed` is not a completeness guarantee. A failed or cancelled import is not silently rolled back as though nothing was observed.

Cancellation invalidates pending work and its fence. An already dispatched network request cannot be recalled, but its post-cancellation response cannot commit new observations. Runtime restart can reclaim an expired 180-second lease; avoid assuming immediate recovery. Reauthorizing a connection versions its grants and cancels unfinished jobs from the old grant. Start a new bounded run against the updated selection. No webhooks, scheduler, Celery or Redis are activated in phase 8; ADR 0009 documents the deliberate first database-worker adapter.

## Authorship and mapping

GitHub numeric user IDs are distinct from local user IDs. Commit authors, committers, PR authors, reviewers and mergers are retained in their own source roles. Git email/name values and Co-authored-by trailers are unverified claims. A null author remains unknown. Bots are identified separately and cannot be mapped to a human through this interface. An email equal to a local account's email does not automatically establish identity or an award.

A project administrator can explicitly link or unlink an observed identity to an active project participant, recording the reason and expected version. Mapping history is preserved. Mapping one of a person's emails does not implicitly link their other claims. A later mapping change does not rewrite a historical evidence attachment or award. Source-version counts are labeled by their actual metric; no personal-worth ranking is produced.

## Attach a source to a work package

Raw imported source and connection details are limited to project administrators and reviewers. In Sources, inspect the preserved document and omissions, choose the exact source version, then select the intended work package. Add relevance/provenance, date/category and any applicable deliverable IDs. Choose visibility explicitly; restricted is the default. Confirm sharing and the reviewed source hash before attaching.

This creates a normal evidence revision containing a readable excerpt and a server-authored exact-source pin. The full pinned document remains available only through a currently authorized evidence-revision route. Choosing project visibility deliberately makes that pinned document available to project readers who can access the evidence, even though they cannot browse the rest of the import store. This is a deliberate source-sharing action, not an automatic repository-wide grant.

Duplicate attachment of the same version to the same package reuses the original link; different source versions remain distinct choices. One source may support multiple packages, but neither a link nor multiple links issue units. Future review must still consider overlapping work. A new attachment changes the current evidence packet and makes relevant unfinished assessments/submissions stale. It never rewrites an archived snapshot, accepted award, dispute resolution or saved hypothetical financial example. Ordinary manual evidence edits preserve the server-provided origin and cannot forge one.

Local membership revocation stops future authorized reads. No application can erase copies already delivered to another person's browser/device. Disconnecting the repository stops new fetches but preserves previously authorized records; deletion/retention of imported raw source is not an implemented phase-8 erasure service.

## References for upstream limitations

- https://docs.github.com/en/rest/pulls/pulls — PR file/commit endpoints and their limits.
- https://docs.github.com/en/rest/checks/runs — check-run evidence.
- https://docs.github.com/en/rest/commits/commits — commit selection and responses.
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api — retry/reset guidance.

Provider behavior was checked September 14, 2026. Our stricter caps above are application choices, not claims that the upstream service guarantees complete history within them.
