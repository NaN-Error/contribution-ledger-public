# ADR 0006 — Manual evidence, private blobs and immutable packets

Status: implemented in source; local/unit contracts tested, native/live/browser gates open. Date: September 13, 2026. Supersedes only the evidence-free behavior of **new** submissions after phase 4. Existing historical payloads are preserved.

## Decisions

Use five additive tables: evidence items, immutable revisions, immutable object references, immutable retirement records, and immutable evidence snapshots. Keep current item visibility/revision as a guarded projection. All references carry workspace/project/package scope; all endpoints recheck live membership. Writes lock workspace, milestone and package consistently with earlier phases. New evidence advances package version so existing reviewed work commands become stale.

Treat author/provenance/date as claims. Store explicit excluded/unavailable evidence with reasons. New packets include current scope, policy/hash, exact evidence revisions and limitations. No missing evidence becomes a zero contribution score. No file-size, author-detection or complexity score is added. Evidence changes never write awards/finance records.

Store accepted small originals privately, never by supplied filename. Preserve exact SHA-256/length and generate independent metadata-free PNG previews from bounded raster inputs. Text is escaped, not rendered as markup. Do not fetch URLs or execute repository/assets/macros. File downloads remain attachments with authentication/no-store/nosniff/sandbox behavior. Originals are not antivirus-scanned or guaranteed safe outside this UI.

Choose JSON/base64 for one bounded file per mutation: 2 MiB raster / 256 KiB UTF-8; keep 64 KiB limits elsewhere. This is a local pilot tradeoff, not a scalable resumable-upload design. Add conservative workspace cumulative quota, entry/revision/snapshot bounds and UUID idempotency. Crash/ambiguous-commit orphans are monitored operationally; no dangerous automatic deletion sweep is invented.

A packet is content-addressed within its package, with immutable capture state and a separate current availability envelope. Restricted entries are redacted at read time. A redacted representation does not reproduce the full canonical hash. All real acceptance decisions in phase 6 must bind exact scope/evidence/policy/attribution revisions and evaluate sufficiency independently.

New submissions archive packet ID/hash under current locks. Explicit `refresh_submission` creates another readiness record without a scope rewrite; it is not acceptance. Existing phase-4 readiness declarations remain evidence-free and unmodified. Add current-vs-submitted stale status; external link contents are never captured or guaranteed stable.

Retirement commits denial before best-effort physical deletion, preserving snapshots and accounting. It does not erase metadata, S3 versions, backups or previously downloaded copies. Tombstones must survive restore/migration. Personal-data erasure governance and automated backup/orphan operations require later explicit decisions.

## Dependencies and deployment

Add Pillow 12.3.0, boto3 1.43.18 and its exact installed transitive versions. Their official version metadata and API documentation were consulted. Existing framework/frontend/container dependency selections are unchanged. The runtime/dev locks are exact pins, not a completed clean-install or advisory certification; native psycopg distributions and frontend packages are absent here.

Default to an API-only protected Docker volume. Include the functional private S3-compatible adapter with stubbed SDK contract tests; no live cloud call/credential/deployment was used. Operator-only SDK credentials and endpoint configuration are not the future user-facing AI-key store. Do not enable cloud storage via ordinary UI input or silently switch/migrate existing objects.

Correct stale Compose source image labels to phase 5 without renaming project/volumes. Keep the local-only environment gate. Evidence writes are synchronous and bounded in this phase; live latency/load, background reconciliation, scoped DB roles, malware scanning and production hardening remain future gates, not implied completed work.

## References consulted

- OWASP file upload guidance: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- Pillow Image reference and decompression-bomb behavior: https://pillow.readthedocs.io/en/stable/reference/Image.html
- Pillow 12.3.0 version: https://pypi.org/project/pillow/12.3.0/
- boto3 1.43.18 version: https://pypi.org/project/boto3/1.43.18/
- AWS official PutObject contract: https://docs.aws.amazon.com/goto/boto3/s3-2006-03-01/PutObject

These are design/SDK sources, not blanket certification of this implementation or its cloud configuration. Actual execution evidence is in `docs/test_results.json`.
