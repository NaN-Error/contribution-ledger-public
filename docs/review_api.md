# Phase-6 review and contribution API

Base: `/api/v1/workspaces/{workspace_id}/projects/{project_id}`. Every request requires an authenticated current membership, and all writes require the inherited origin/CSRF safeguards and bounded JSON body. IDs in nested paths are scoped by the server; knowing an ID is not permission. See auth_api.md for the session protocol. JSON examples below are shapes, not usable secrets or real people.

| Method and relative path | Function |
|---|---|
| GET `/reviews/options?package_id=UUID` | Exact per-deliverable target fingerprint, eligible reviewers, quorum and blockers |
| POST `/reviews` | Create immutable independently assigned review round (201) |
| GET `/reviews?offset=0&limit=20&package_id=UUID` | Bounded queue; optional package filter |
| GET `/reviews/{id}` | Exact target, state, masked/currently authorized observations and available actions |
| POST `/reviews/{id}/decisions` | Record one immutable human decision; no credit yet |
| POST `/reviews/{id}/finalize` | Explicit checked finalization; award or dispute resolution |
| GET `/contributions` | Scoped finalized units, exact ratios, pending planning and open-case blockers |
| GET `/contributions/integrity` | Administrator-only read-only projection verification |
| GET `/contributions/awards?offset=0&limit=20` | Preserved awards with current attribution |
| GET `/contributions/awards/{id}?offset=0&limit=50` | Award, original/current attribution and paged event lines |
| POST `/disputes` | Open one active concern for a finalized award (201) |
| GET `/disputes?offset=0&limit=20` | Bounded case history |
| GET `/disputes/{id}` | Context hash, notes, assignments, original award and resolution |
| POST `/disputes/{id}/assignments` | Administrator assigns conflict-free resolver |
| POST `/disputes/{id}/notes` | Preserve project-visible supplementary text/optional source URL (201) |
| POST `/disputes/{id}/proposals` | Current resolver creates uphold/reallocate review (201) |
| GET `/notifications?offset=0&limit=20` | Current user's project notification records only |

Normal list limits are 1–50 (event list 1–100); next_offset=null ends paging. Offset is bounded. All mutating phase-6 schemas reject unknown fields and use request_id UUIDs. Reusing the same ID for different actor/input is a conflict. Permission checks still occur on replay. State change effects and responses commit atomically; an operational failure rolls back all credit writes.

## Request bodies

ReviewCreate: `request_id`, `package_id`, `deliverable_id`, `expected_package_version`, `reviewed_target_hash`, `reviewer_ids` (exact policy quorum, unique), `reason` (8–500 characters). The target is derived by the server; callers cannot supply a budget or arbitrary percentage at this endpoint.

DecisionCreate: `request_id`, `reviewed_target_hash`, `decision` (`accept`, `request_evidence`, `reject`), `findings` (one per displayed criterion), `evidence_reviewed=true`, `independent=true`, `reason`. Each finding: `criterion_id`, `result` (`supported`, `unsupported`, `insufficient`), `evidence_refs` (distinct exact packet/dispute refs), `explanation` (8–500 characters). Acceptance requires all supported and nonempty valid refs. References do not establish truth automatically. Requesting changes leaves balances unchanged.

Finalize: `request_id`, `reviewed_decisions_hash`, `reviewed=true`, `reason`. Credit state ready_to_finalize is derived, not a client-set flag. All quorum members must retain current independent authority. An owner/beneficiary cannot bypass it. The resolver alone may finalize a dispute resolution after its assigned quorum accepts.

DisputeCreate: `request_id`, `award_id`, `reason`. AssignResolver: `request_id`, `reviewed_context_hash`, `resolver_id`, `reason`. NoteCreate: `request_id`, `text` (12–4,000 printable characters), `source_url` (optional bounded credential-free HTTPS reference; never fetched).

ResolutionCreate: `request_id`, `reviewed_context_hash`, `disposition` (`uphold`, `reallocate`), `attributions`, `reviewer_ids`, `reason`. Uphold uses empty attributions. Reallocate specifies the complete replacement as `{user_id, role, atoms}` positive exact integers; sum must equal the preserved accepted budget. Roles match the existing work-package roles. The current resolver is required in the quorum, but no proposed recipient can review.

## State and privacy

Review states: awaiting_decisions, changes_requested, ready_to_finalize, stale, finalized. Stale covers changed evidence/scope/dispute/permission/quorum context and explicit supersession. Finalized historical records remain finalized despite later artifact retirement. Partial awards do not change the planning target of other unchanged deliverables. Evidence changes do.

Artifact access is always through the existing protected evidence routes. Read-only contributors cannot retrieve reviewer-only findings or restricted artifact titles/reference IDs through a review. Dispute text, URLs, reasons, attribution and accounting records are intentionally project-visible; do not place secrets in them. Full canonical snapshots stay internal and are redacted on authorized reads where necessary. Accounts already holding downloaded information cannot be made to forget it by access revocation.

No arbitrary balance setter, history DELETE, automated award, payment, equity, model evaluator or financial close route exists. Error messages are sanitized ApiError envelopes with request identifiers. Unknown/out-of-scope records use existing not-found semantics.
