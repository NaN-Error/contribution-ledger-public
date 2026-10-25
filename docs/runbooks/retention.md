# Retention and deletion boundaries

Retention decisions belong to the operator and team agreements. This source does not invent a jurisdiction-wide retention duration or imply that an irreversible record resolves privacy obligations. Record the applicable policy, affected scope and reason before deletion. Obtain qualified guidance where legal retention/privacy duties conflict.

| Material | Available operation | What remains |
|---|---|---|
| Expired browser sessions and recovery tokens | Explicit operator `prune-auth` removes records expired more than seven days ago and old throttle buckets | Audit events and contributor identity |
| Active account access | Disable or suspend through existing account/membership controls | Finalized contribution history, required statement identity and historical evidence |
| Uploaded evidence bytes | Explicit artifact retirement plus recorded physical deletion/retry | Original evidence metadata, revisions and immutable review snapshots |
| API connection key | Rotate or revoke; delete old ciphertext through the existing checked operation | Usage/disclosure/history records and remote provider state |
| MFA enrollment | User-authenticated local disable or verified operator reset | Audit record; backups may retain earlier encrypted seeds |
| Prepared AI packet / assessment | Retained as a separate reviewed text copy in the database in this release | It is not erased by retiring a source artifact |
| Closed distribution / release snapshot / payment declaration | Linked financial corrections and declaration voids, not in-place history deletion | Original input, result and decision trail |
| Backup set | Explicit operator storage-policy deletion after a verified newer recovery set and retention review | Other copies, host snapshots, remote/offsite replication or remnants may remain |

Do not advertise a global "delete my data everywhere" button: it is not implemented. There is no automatic packet purge, financial-history redaction, source-account erasure, remote provider deletion or secure disk erasure. Those require a separately reviewed retention design, preservation of reproducibility obligations and actual provider/storage operations. Financial source documents are retained; their byte removal is not part of ordinary evidence retirement.

Before archiving or deleting a backup, verify that the remaining data bundle, matching protected recovery bundle, external key, source/tool version and required images together restore successfully. Deleting only a master key makes retained ciphertext unrecoverable; it is not a harmless rotation. Never delete the only tested recovery set as part of an upgrade.

Use the existing participant statement, financial JSON/CSV export and project-protected evidence views for authorized export. A financial audit ZIP is not a full personal-data export or full system backup. Keep export access separate from access to the entire repository and private accounting documents.
