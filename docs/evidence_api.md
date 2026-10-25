# Evidence API, phase 5

All routes below are relative to:
`/api/v1/workspaces/{workspace_id}/projects/{project_id}/work-packages/{package_id}/evidence`

Every route requires a live authenticated session and current scoped project access. Every mutation requires the exact allowed Origin, current CSRF token and JSON body. No raw storage path, object ID from a user, arbitrary backend or external credential is accepted as an upload destination. Pydantic rejects unexpected input fields.

| Method | Suffix | Result |
|---|---|---|
| GET | empty | Up to 20 visible entries, pagination, restricted count, permissions, current packet/hash and latest-submission state |
| POST | empty | Create an evidence item and revision 1, automatically snapshot; 201, with replay information |
| POST | `/{evidence_id}/revisions` | Append a revision or return the identical authorized replay; 200 |
| GET | `/{evidence_id}/revisions` | Visible revision history, at most 50 |
| GET | `/{evidence_id}/revisions/{number}` | Exact authorized revision and current availability |
| GET | `/{evidence_id}/revisions/{number}/preview` | Escaped/plain JSON text; no Markdown/HTML execution |
| GET | `/{evidence_id}/revisions/{number}/image` | Verified regenerated PNG, never the original embedded as an image |
| GET | `/{evidence_id}/revisions/{number}/download` | Verified original as `application/octet-stream` attachment |
| POST | `/{evidence_id}/revisions/{number}/retire` | Commit denial record, then attempt object deletion |
| GET | `/snapshots` | 20 packet summaries with `next_offset`; bounded history |
| POST | `/snapshots` | Explicit current packet capture/reuse; 201 |
| GET | `/snapshots/{snapshot_id}` | Immutable archived packet, redaction flag, stale flag and separate current artifact status |

## Example create command

Use actual IDs/version read from the package. These values are fictional examples, not a seed or a real credential.

```json
{
  "kind": "statement",
  "metadata": {
    "title": "Character animation review",
    "description": "Documents the movement states and the remaining transition problem.",
    "claimed_authors": "Fictional artist and tester",
    "provenance": "Prepared for the agreed synthetic animation deliverable.",
    "occurred_on": "2026-09-13",
    "category": "art",
    "visibility": "project",
    "inclusion": "included",
    "omission_reason": null,
    "deliverable_ids": []
  },
  "text": "The locomotion states are ready for review. A turn transition still needs testing.",
  "expected_package_version": 1,
  "request_id": "00000000-0000-4000-8000-000000000001",
  "reason": "Record a synthetic contributor statement for human review."
}
```

Kinds are `statement`, `link`, `file`, `unavailable`. File content is `{ "filename": "report.txt", "media_type": "text/plain", "content_base64": "..." }` in `file`; a source URL is `source_url`. Only the content matching the selected kind may be supplied. All non-included metadata needs a nonempty omission reason. Unavailable records remain unavailable; add the subsequently recovered evidence as a separate entry.

A revision command omits `kind`, includes the whole new metadata/text/URL plus `expected_revision`, `expected_package_version`, `request_id` and reason. `file: null` keeps the prior file; a supplied file creates new objects. UUID request IDs are unique per package. Exact repeat by the same authorized actor returns the original revision; changing its command or actor is a 409 conflict. Retrying after refresh with changed content requires a new request ID. Unsafe network failures are not automatically retried.

A capture command uses `expected_package_version`, package `reviewed_hash`, `reviewed: true`, and a reason. It is not an acceptance decision. A retirement uses the expected package version, `reviewed: true` and reason. The response includes `deletion_pending_objects`; committed denial remains effective even if deletion fails. Expected version checks guard concurrent metadata/retirement edits.

New work-package `POST .../actions` supports `action: "refresh_submission"` while submitted. It uses the existing work action shape (`expected_version`, `reviewed_hash`, `reviewed`, `reason`) and snapshots current evidence under the same checked transaction. Readiness/refresh does not award units.

## Permissions and state

Project administrators and assigned contributors can add evidence; current reviewers can add independent notes. Ordinary unassigned contributors, finance users and viewers cannot. Only the original submitter with current write permission or a project administrator can revise an entry. Restricted historical visibility is enforced on every route, not inferred from an opaque URL. Packet redaction applies to source claims, filenames, omissions and revision content; its full canonical fingerprint is retained with a redaction notice.

No package rebinding or cross-project/foreign deliverable reference is accepted. New snapshots and revisions are bounded. Artifact paths are server-generated UUIDs and are never returned as filesystem paths/public storage URLs.

Important states: `available` means stored availability metadata is consistent, not independent content acceptance; `external_unverified` means only the source URL is recorded; `excluded` / `declared_unavailable` come from explicit metadata; `missing`, `corrupt`, `retired`, `storage_unavailable` reflect object state. Full checksum verification happens before download/preview delivery.

Important errors: 401 unauthenticated; 403 insufficient mutation permission/CSRF/origin; 404 inaccessible or foreign record; 409 stale version, conflict, quota, finalized work, checksum failure or a closed package; 410 retired/missing/omitted artifact; 413 file/text/request too large; 415 unsupported request encoding/media; 422 invalid type, filename, metadata or unexpected field; 503 unavailable storage. Errors remain sanitized and request-correlated. Invalid or incomplete evidence never becomes a zero-value contribution award.

The application bounds JSON requests before model parsing, uses workspace → milestone → package locks for writes, and keeps original blob writes separate from authoritative database history. See storage operations for ambiguous-commit/orphan handling and the limits of local tests versus native PostgreSQL races.
