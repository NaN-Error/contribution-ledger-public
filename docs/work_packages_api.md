# Work-package API — phase 4

Base: `/api/v1/workspaces/{workspace_id}/projects/{project_id}/work-packages`. Every route requires a valid browser session and current scoped project access. Mutations additionally require the existing exact Origin, JSON content type, CSRF header and bounded request body. Do not put passwords/tokens into these JSON records. All examples use fictional UUID placeholders; copy actual authorized IDs from the preceding responses.

| Method | Relative route | Behavior |
|---|---|---|
| GET | `/options` | Current non-viewer participants and approved positive unlinked allocations; explicit truncation flag |
| GET | `` | List/filter with `q`, `category`, `state`, `offset`, `limit` |
| POST | `` | Bind a new draft package to an existing allocation |
| GET | `/{id}` | Current scope, review fingerprint, policy readiness, actions, blockers and history |
| POST | `/{id}/revisions` | Append a scope revision; reset planning approval |
| POST | `/{id}/actions` | Explicit, checked lifecycle command |
| GET | `/{id}/revisions/{number}` | Authorized immutable scope snapshot |
| GET | `/{id}/submissions/{submission_id}` | Authorized exact readiness-declaration snapshot |

## Create

```json
{
  "milestone_id": "11111111-1111-4111-8111-111111111111",
  "allocation_id": "22222222-2222-4222-8222-222222222222",
  "expected_allocation_version": 1,
  "scope": {
    "title": "Reconnection behavior",
    "outcome": "Restore the saved session after a temporary disconnection.",
    "acceptance_criteria": ["A returning player recovers the same saved session."],
    "evidence_requirements": "Source revision plus a reproducible reconnection test report.",
    "coordinator_id": "33333333-3333-4333-8333-333333333333",
    "intended_contributor_ids": ["33333333-3333-4333-8333-333333333333"],
    "deliverables": [{
      "id": null,
      "title": "Restore session state",
      "outcome": "Recover the documented state without duplicating a session.",
      "acceptance_criteria": ["The synthetic dropped-connection test can be reproduced."],
      "evidence_requirements": "A report naming the source revision and exact test conditions.",
      "budget_atoms": 100000,
      "attribution": {
        "mode": "units",
        "entries": [{"user_id": "33333333-3333-4333-8333-333333333333", "role": "implementation", "atoms": 100000}]
      }
    }]
  },
  "reason": "Define the agreed synthetic scope before beginning work."
}
```

100,000 atoms represents 100 units, not money. The selected allocation must have that approved capacity. UUIDs are validated/scoped, not trusted because they are syntactically valid. Supplied deliverable IDs must be unique within the revision; omitted/null IDs are generated. Any future reference to a deliverable must include its package/revision, never only the nested ID.

A percentage plan instead uses `{"mode":"percent","entries":[{"user_id":"...","role":"testing","basis_points":10000}]}`. Positive basis points total at most 10,000; incomplete plans may be saved as drafts. Direct atom rows total at most their deliverable budget. Every attributed identity must also be an intended contributor. Unknown fields, booleans/floats for integer amounts, duplicate person/role rows, invalid text and over-bound input are rejected. Only active non-viewer participants in this project are eligible for a new scope.

Responses include raw proposed percentages/atoms and server-derived `resolved_attributions`, `unassigned_atoms` and `attribution_complete`. Never send derived fields back as editable scope input. The browser's `scopeDraft`/`buildScope` helpers perform that separation.

## Amend and change state

A revision command is `{"expected_version":N,"reviewed_hash":"CURRENT_HASH","scope":{...},"reason":"..."}`. Use the current detail response. An amendment appends a new document and returns to draft. It never rewrites a previous revision.

A state command is `{"action":"approve_scope","expected_version":N,"reviewed_hash":"CURRENT_HASH","reviewed":true,"reason":"..."}`. Other accepted actions are `start`, `submit`, `request_changes`, `withdraw`, `cancel`. A request cannot set an arbitrary state, completed flag, issued amount, attribution score or earned share. Mutation retries are not automatic: refresh after a conflict or uncertain outcome, inspect history, and decide whether a new command is needed.

The review hash covers package state/version, scope fingerprint, approval revision and parent allocation/milestone versions. It is a consistency token, not a cryptographic signature or permission grant. Access and policy readiness are always checked separately. Repeated approval/submission/cancellation with stale versions produces a conflict, not duplicate effects.

## Pagination and errors

Lists default to 20, maximum 50, with `total` and `next_offset`. Detail history uses `history_offset` in pages of 20 and `next_history_offset`; recent submissions show 10 with older submission IDs available from events. Boundaries and limit messages are explicit rather than silent deletion.

Useful error codes include `allocation_already_linked`, `stale_allocation`, `package_budget_exceeded`, `participant_unavailable`, `stale_version`, `review_hash_mismatch`, `scope_incomplete`, `scope_budget_changed`, `invalid_transition`, `linked_package`, `package_amendment_required`, `deliverable_budget_bound`, and `finalized_work_protected`. Existing authentication, policy-readiness and budget errors still apply. For foreign/missing resources, respond with scoped not-found rather than disclosing another project's data.

No endpoint in this phase accepts evidence, finalizes earned credit, calls AI or makes a payment. Archive read permissions do not imply approval authority.
