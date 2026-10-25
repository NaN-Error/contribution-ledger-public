# ADR 0004 — Policy governance and exact planning budgets

Date: September 13, 2026. Source: `0.3.0-phase3`. Scope: P03A/P03B/P03C. Baseline: actual phase-2 source archive. Status: implemented; native runtime verification pending.

## Decisions

Use 1,000 integer atoms per contribution unit, maximum 10^12 atoms. Pool weights are positive integer basis points summing to 10,000. No float-backed balances or person-worth metric is introduced. Financial minor-unit calculations remain phase 7/13. The UI converts decimal strings with integer arithmetic and retains exact ratio inputs for display.

Policies are immutable revisions, not mutable drafts. The newest draft may be approved by a project administrator, including its author, after confirming the exact fingerprint and reviewed examples. Approvals have non-backdated, monotonically ordered effective instants. Participant acknowledgements are self-service and bound to version/hash. Administrative planning authority is explicitly distinct from independent contribution-credit acceptance, which does not exist yet.

Required acknowledgements combine the original active non-viewer snapshot with current active non-viewer project participants, including inherited workspace administrators. This prevents removing an unacknowledged snapshot participant merely to bypass the gate. It may require a successor policy when a participant leaves or the roster changes before approval. No cancellation/rescheduling of immutable scheduled approvals is included in this phase.

The latest approved effective policy is the new-milestone candidate; missing acknowledgements never silently restore an older candidate. Existing active milestones stay pinned to their approved policy. Their future planning still requires current acknowledgement readiness. These semantics must not be reused to recalculate finalized awards or distributions when those features arrive.

Budget creation makes a zero-approved draft and an initial proposal. Propose/preview/approve/reject are separate. Protected reserve is within the total and remains unowned. Allocations represent intended work, not people or completed evidence. Total/resize/cancel changes preserve reasons and snapshots and cannot erase already-issued projections. Those projections can only be changed by the future ledger service, never by these routes.

Use one fixed transaction lock order: workspace then milestone. The workspace lock is deliberately coarse for this small pilot, serializing membership and planning mutations. Generate response data before commit while the coherent locks are held. Reject stale milestone versions, re-evaluate preview hashes on approval and give each proposal one immutable decision. Do not promise exactly-once network delivery. Repeating a decision yields a conflict; repeating an identical own-policy acknowledgement is safe.

Add database checks and tenant-scoped composite foreign keys. Reject ordinary UPDATE/DELETE operations on policy versions/participants/approvals/acks and budget amendments/decisions using database triggers. Applied migrations 0001 and 0002 remain unchanged. New migration 0003 refuses destructive downgrade when phase-3 records exist. The runtime still uses the earlier local database role; a database operator can bypass application-level assurances. Least-privilege deployment remains an explicit later hardening requirement.

## Deliberate implementation boundaries

The roadmap asks for dilution visibility. With no personal ledger yet, show exact before/after **planning-allocation shares of the milestone total**, explicitly not personal earned shares. Future ledger-derived previews can add person-level effects, but phase 3 must not manufacture those numbers. No funding rights or signed legal agreement is issued by acknowledgement. Single-admin policy/budget governance is not a universal team rule; broader quorum governance needs a separate policy/implementation decision.

Calendar accounting is limited to day-1 midnight monthly periods with a configured reject-on-ambiguous-boundary rule. No actual period-close engine runs yet. Templates are fetched only after authorized access and are never seeded or approved at startup. Limits of 200 policy versions/200 milestones/500 proposals keep this local pilot bounded. Proposal history pages contain 20 rows. Large-scale performance has not been benchmarked.

No new framework or third-party dependency was added. Preserve inherited exact package pins and explicitly label the frontend lock as unverified until a real network-backed installation/build. The full React build cannot be claimed based on TypeScript syntax transpilation.

## Reference behavior checked

PostgreSQL documents row locks and their transaction lifetime at `https://www.postgresql.org/docs/current/explicit-locking.html`. SQLAlchemy's `Select.with_for_update` is documented at `https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update`. Pydantic's strict-mode documentation is at `https://docs.pydantic.dev/latest/concepts/strict_mode/`.

These informed the implementation, not a claim of native PostgreSQL execution or an external security review. The complete executed/skipped evidence is in `docs/test_results.json`.
