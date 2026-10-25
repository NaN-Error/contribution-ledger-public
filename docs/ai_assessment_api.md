# Assessment API contracts

All paths start at `/api/v1/workspaces/{workspace_id}/projects/{project_id}/ai/assessments`. All reads use current session/project access; state-changing requests additionally use existing origin/CSRF protection. Only current project administrators/reviewers can prepare or inspect packets. Advisory plan/results impose additional requester/payer/administrator visibility. Server-side authority is required even when UI controls are hidden.

| Method and suffix | Purpose |
|---|---|
| GET `/options?package_id=` | Current package version, deliverable/evidence options and concrete evidence profiles; at most latest 1,000 profiles with visible truncation |
| POST `/packets` | Local selection/redaction/snapshot, request idempotency; no external call |
| GET `/packets/{id}` | Exact packet/provenance plus current freshness |
| GET `/packets?package_id=&offset=` | Bounded packet history, 25 per page |
| POST `/plans` | Preserve mode, profile, packet, reason and required predecessor; no call |
| GET `/plans?package_id=&deliverable_id=&mode=&offset=` | All visible plans, newest first, 25 per page |
| GET `/plans/{id}` | Current grant/role/job/result state and frozen definition |
| POST `/plans/{id}/approve-data` | Administrator approves exact plan/hash/disclosure reference, lifetime at most 24 hours |
| POST `/plans/{id}/revoke` | Administrator or payer withdraws future authority; preserves history |
| GET `/plans/{id}/quote` | Payer-only current exact spending estimate; no call |
| POST `/plans/{id}/run` | Explicit payer consent, exact quote and idempotent request, one durable job per plan |
| GET `/results/{id}` | Hash-verified result/metadata and original packet with dynamic stale status |
| POST `/results/{id}/feedback` | Current independent reviewer commentary; not an acceptance decision |
| GET `/results/{id}/feedback?offset=` | Preserved commentary, 50 per page |

Packet requests specify request_id, package_id, deliverable_id, profile_id, expected_package_version, reason, optional evidence_ids, include_restricted, and excluded_paths. Profile creation through the existing AI settings API uses `purpose=evidence` and an output cap 512–8,192. The legacy compatibility purpose remains available and cannot be promoted implicitly.

Plan requests contain reviewed_packet_hash and explicit latest prior_plan_id for a rerun. Grant requests contain reviewed_plan_hash, permission_reference, reason, valid_until, packet_reviewed=true and authorized_to_share=true. Run requests use the existing bounded quote_hash/confirmed_reservation_microusd/payer_approved/request_id schema; no model prompt is accepted from the browser. Data and spending permissions are checked again at dispatch and receipt, not only in this endpoint.

Feedback contains reviewed_result_hash, review_id, criterion_id, action (accept/modify/reject/request_evidence), reason, optional replacement_text only for modify, request_id and original_evidence_reviewed=true. The existing work review and award-finalization APIs are unchanged. Claiming a result is valid cannot issue credit.

Output schema: `evidence-assessment-v1`, exact criteria statuses supported/contradicted/insufficient, line citations, known contributor aliases, bounded questions and within-packet overlap flags. Extra fields such as scores/amounts/commands are rejected. Invalid model output is not echoed in errors or stored as findings. Generic AI jobs expose only bounded status/usage/result identifiers. Errors retain the existing sanitized request-ID envelope.

Every immutable record has a content or linked-input fingerprint. This supports integrity checking and repeatable audit, not cryptographic attestation against a database superuser. Restricted schema grants and triggers do not replace a full security review.

Official rerun lineage is project-wide for each deliverable. Advisory lineage is per requester, so a private peer run cannot leak its identifier or block another reviewer. Administrators retain access to all advisory histories. Plan history supports `mine=true` to select the current requester.
