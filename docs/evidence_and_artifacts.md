# Manual evidence and private artifacts

Source phase: P05, `0.5.0-phase5`. This is a local, synthetic-data pilot. Human acceptance, contribution awards and disputes arrive in phase 6. Do not treat an upload or a snapshot as verification that someone completed the work.

## Start with a work package

Open Workspaces → workspace → project → Work packages → a package. Below Current scope, Contribution evidence shows the visible entries, restricted-entry count and whether the latest submission matches the current evidence packet. Evidence is associated with this project's package and optionally with specific deliverables in its current scope.

Choose **Add evidence**. Supply title, relevance, claimed authors, source/provenance, claimed date, category, visibility and reason. A submitter account identifies who supplied a claim; the named original authors and dates remain unverified claims. Notes and descriptions are plain text. There is no HTML, Markdown or formula execution in previews.

Evidence types:

| Type | What is stored |
|---|---|
| Contributor statement or review note | Plain text, source/provenance and author claims |
| External source link | An HTTPS URL and its explanation; no server fetching, crawling or source verification |
| Uploaded artifact | Original bounded bytes, exact SHA-256/size/type, and separate regenerated raster preview when applicable |
| Missing evidence / limitation | An explicit unavailable entry with a reason; not a low contribution score |

For large game assets, music, videos or other currently unsupported formats, record a permitted HTTPS source link and a small relevant text/image artifact. The application does not claim to preserve or verify bytes behind external links. Supply no private source unless every intended viewer and configured storage destination is authorized.

## Upload limits and treatment

UTF-8 `.txt`, `.md`, `.csv` and `.json`: nonempty, at most 256 KiB. They are displayed as escaped plain text, not executed or parsed as an application. JSON syntax and CSV formulas are not evaluated. Text previews show at most 20,000 characters; the protected download retains the original allowed file.

Static `.png`, `.jpg`, `.jpeg` and `.webp`: nonempty, at most 2 MiB, 8,000,000 pixels and 8,192 pixels on each side. Animated/multipage images are rejected. The server verifies and decodes the selected raster format, applies orientation, reduces the preview to a maximum side of 1,024 pixels, and writes a fresh PNG without source metadata. The original is preserved separately and can still contain EXIF, comments or identifying metadata.

No SVG/HTML, archives, macros, executable/script files, PDFs/OCR, native Blender/game projects, audio/video uploads or automatic asset processing are supported here. Original downloads are **not malware-scanned** or guaranteed safe in another application. Do not open untrusted originals casually. File validation and re-encoding reduce the accepted surface; they are not an antivirus/security certification.

The browser encodes one bounded file inside JSON. This deliberately avoids multipart staging and a separate upload-session workflow for the small local pilot. The proxy and API allow at most 2,861,740 bytes of JSON on the two exact create/revision upload routes; other ordinary JSON mutations remain limited to 65,536 bytes. Compressed request bodies are rejected. These limits are conservative defaults, not a large-asset upload product.

A package permits at most 100 evidence entries, 50 revisions per entry and 2,000 distinct snapshots. Default workspace storage allowance is 256 MiB of **all recorded originals and previews**, including retired objects. Counting retired history prevents repeated retire/re-upload operations from bypassing the pilot cap. There is no quota-reset UI; the operator must review any expansion. This does not account for storage versions, backups or crash-created unreferenced objects, which also require monitoring.

## Visibility and current authorization

**Project:** users who currently have access to the project can inspect it.

**Restricted:** only the submitter, current project reviewers and administrators can inspect it. Workspace owners/administrators may have effective project-administrator access under the existing permission system. Restriction is not secrecy from the deployment operator or database/storage administrator.

Current project access is checked on metadata, history, snapshots, previews and downloads. A guessed ID or old link does not substitute for authorization. The browser/proxy/API use no-store responses and binary downloads have a sandbox content-security policy and nosniff header. There are no public object URLs or presigned downloads.

Current restriction also protects older formerly public revisions. A later public revision does **not** publish earlier restricted revisions. Snapshot responses redact hidden entries without modifying the stored canonical packet. A redacted response's visible JSON is consequently not the full document used for its displayed fingerprint.

Reviewers can add separate review notes but cannot rewrite another submitter's entry. An assigned contributor may add evidence; an unassigned ordinary contributor, finance user or viewer cannot. The submitter or an administrator can add a revision while they retain the necessary write authority. Completed/cancelled work and finalized-credit projections block this phase's ordinary evidence changes. Artifact retirement remains separate from credit retention.

Authorization changes stop subsequent requests. They cannot recall data already visible, held in a browser's memory or saved by a person. Reloading/refetching clears denied content; this phase does not provide push-based remote erasure. Do not describe no-store headers as deletion of saved copies.

## Revisions, packets and submissions

**Add a revision** creates a new immutable metadata/content record and advances the package version. Leaving the replacement-file input empty reuses the same original; choosing a new file preserves earlier bytes and records a new original/preview pair. Earlier hashes and source history are not edited. Scope changes that remove an evidence-linked deliverable are flagged for review in the next packet.

Each evidence change automatically captures a content-addressed packet with the exact scope revision, acceptance criteria, policy reference/hash, evidence revision/hash, stored object IDs, availability-at-capture and explicit omissions. Identical canonical content reuses the same packet ID; a new submitter action can still have its own work-submission record. These are human-review inputs, not AI scores or accepted awards.

Packet capture checks object existence/recorded size (and S3 object metadata). Original and preview delivery verifies the full recorded SHA-256 before returning any bytes. The UI never treats a metadata/existence check as proof that a file was fully verified at capture. Availability can change outside the application; archived packets preserve their capture state and return a separate current-status envelope. Files that disappear or fail integrity checks remain referenced and are not delivered as valid evidence.

New readiness submissions include the exact evidence snapshot ID and hash. Adding/replacing evidence, changing scope, retiring an artifact or detecting changed availability makes a mismatching unfinished submission visibly stale. **Resubmit with current evidence** is an explicit coordinator/administrator action while submitted. It creates a new work submission; it never overwrites the earlier one. A changed scope still needs its normal amendment/approval workflow.

Phase-4 submissions are preserved with their original evidence-free status. Upgrading never backfills a packet or implies that old work was evidence-reviewed. No evidence submissions issue units. Phase 6 must require a current authorized reviewer, exact relevant revisions, sufficient evidence and an independent human decision before credit issuance.

## Retiring stored artifact bytes

A project administrator can inspect a current or archived file revision and choose **Retire stored bytes**. Read the effect, supply a reason, and confirm. It blocks original and preview delivery for every revision referencing those objects, then attempts physical deletion. There is no undo route for the tombstone.

The database denial is committed before deletion. If the store is unavailable, delivery remains blocked and the response displays how many objects still need physical deletion. Refresh the package and explicitly repeat retirement with its current version to retry deletion. Repeating the command does not issue another credit change. Repeated unchanged retirement can retry the same tombstoned objects.

Metadata, statements, historical snapshots, hashes and accounting remain. Object versions, backups, exported copies and previously saved originals are not erased by this command. This is a raw-artifact retention tool, **not** a complete privacy-erasure implementation. Restoring data or changing stores must preserve the denial records. Text-only personal-data retention needs a separately reviewed future policy, not ordinary history edits.

## Deferred browser and storage checklist

Use fictional data and a disposable installation. These checks are supplied; actual browser, Docker and Windows results are still open.

1. Add a design statement, a small character PNG and an explicit missing QA report. Verify each role's access and zero issued units.
2. Preview Markdown containing `<script>` as text. Upload a fake PNG/SVG, oversized image, animated image, invalid UTF-8 and path-like filename; each must fail without adding evidence. Verify no secret/path text in errors.
3. Inspect the image preview and download its original. Compare the original SHA-256 with the recorded hash. Check that the preview lacks source metadata and is limited in size.
4. Submit work. Replace an artifact and inspect the old submission and old download. Observe stale status, explicitly resubmit, and confirm both submissions and distinct evidence revisions remain.
5. Change visibility to restricted. Inspect old and current packets as a viewer and reviewer. Suspend the viewer and retry every previously known image/download URL; subsequent requests must fail.
6. Retire an old file through its revision-history view. Inspect the archived packet's preserved capture state and current retired status. Confirm downloads are denied and units/budgets do not change.
7. Restart/recreate API and web containers without deleting volumes. Log back in; metadata, originals, previews and snapshots should persist. Test missing/corrupt bytes only in disposable storage and confirm unavailable/integrity warnings, not a successful download.
8. Test Windows paths/spaces, keyboard forms, mobile widths, errors and retry behavior. Run the opted-in Playwright account smoke for the complete evidence flow once the real frontend build works.

Storage operation and live S3 checklist: `docs/storage_operations.md`. API contract: `docs/evidence_api.md`. Upgrade: `docs/upgrade_phase5.md`.
