# Policies and milestone budgets

## What phase 3 recognizes

This release records **agreed rules and approved planning capacity**. It does not record accepted evidence, earned contribution units, ownership or amounts owed. Programming, art, design, QA, research, maintenance, marketing and other categories use the same policy/budget model. A work allocation is an intended outcome budget, not a contributor award.

## Policy workflow

Open Workspaces, the workspace, the project, then Policies. A project administrator can choose a release-only or release/ongoing **draft example**. Neither example is automatically saved or approved. Replace its title, agreement reference, terms, eligible categories, review threshold, pool weights and accounting rules. The reference is stored as text; the app does not fetch, validate or legally certify the referenced agreement.

Saving creates a new immutable version. Every revision has a predecessor, author, reason, exact rules, original participant snapshot and SHA-256 content fingerprint. There is no edit/delete route for saved policy text. Use **Create successor version** to correct or change a draft. The latest revision is the only one eligible for a new administrative approval. Creating a draft does not supersede a currently approved policy.

Before approving, review the full document and participant list, provide a reason and check the explicit review confirmation. Approval may be immediate or at a future ISO instant with seconds and an offset, such as `2030-01-01T12:00:00-04:00`. The date is a syntax example, not a recommendation. No backdating or implicit timezone guessing is allowed. Successor effective times must be later than all previously approved times. Scheduled approvals have no cancel/reschedule feature in phase 3; choose the date carefully and use a reviewed later successor when necessary.

Administrative approval and participant acknowledgement are separate. Each signed-in participant acknowledges only their own review of the exact approved fingerprint. An administrator cannot submit another person's acknowledgement. Repeating the same acknowledgement is safe and does not duplicate records. Acknowledging version 1 does not acknowledge version 2.

### Required participants and changes

The required set is the union of the original active non-viewer project-participant snapshot and the current active non-viewer participants. Workspace owners/administrators inherit project access and are included. Viewers are not required economic participants; their voluntary acknowledgement does not grant rights. The UI shows every required person, whether they were in the original snapshot, and whether they acknowledged this version.

If participants change before approval, create a successor to capture the new snapshot. If someone joins afterward, budget readiness pauses until they acknowledge. Suspending or removing an unacknowledged participant does not remove the original requirement. Resolve the situation with the team and a reviewed successor; the administrator cannot simply delete that person's required acknowledgement. Historical identities and records remain.

The current policy candidate is the newest approved version whose effective time has arrived. If it is missing acknowledgements, the application does **not** silently fall back to older economics for new milestones. An existing active milestone stays pinned to its original policy; that version must remain approved, effective and fully acknowledged for additional budget approvals. A draft milestone must still use the current ready policy before its initial budget is activated.

### Rules stored now, enforced in later workflows

The policy records independent acceptance-review thresholds (1–3), budgeted-deliverable acceptance, attribution, departures, pool eligibility, accounting period, expenses, reserves, capital repayment, empty-pool behavior and dispute blocking. Phase 3 validates supported configurations. Acceptance and financial workflows are not implemented yet, so storing a rule is not a claim that the later workflow exists.

A single project administrator can approve policies and planning amendments, including their own proposals. This governance choice is visible. It must never be reused to waive the future rule that a beneficiary cannot be the sole independent approver of their own contribution credit.

## Exact units and budget terminology

One contribution unit equals **1,000 atoms**. Browser input supports three decimal places (`0.001`, `12.345`, `1000`). API amounts are strict integer atoms: `12.345` units becomes `12345` atoms. Negative amounts, floating-point JSON atoms, strings, booleans, exponent-form browser input and excess precision are rejected. The current maximum per budget is 1,000,000,000 units (1,000,000,000,000 atoms).

| Field | Meaning |
|---|---|
| Approved total | Entire milestone planning capacity, including reserve |
| Planned allocations | Units committed to intended work budgets, not people |
| Protected reserve | Minimum unassigned capacity unavailable until a reserve amendment |
| Available to plan | Total minus planned allocations minus protected reserve |
| Unassigned | Total minus planned allocations; includes protected reserve |
| Issued units | Finalized contribution credit; always zero through normal phase-3 operations |
| Unissued | Total minus issued; includes both planned work and reserve |

Pool weights use integer basis points (10,000 = 100%). They are distribution-policy settings, not instructions to force the same ratio of planning budgets. Release-only and release plus ongoing are supported. New policies copy the project's USD/IANA timezone settings, then preserve that version's timezone independently of later project changes.

## Milestone workflow

Open Milestones. An effective, acknowledged current policy is required to create a milestone. Enter its name, description, initial total, protected reserve and reason. The milestone initially has zero approved capacity and a pending initial-budget proposal. A separate decision activates it.

Review the stored before/after preview and reason, confirm the exact preview and approve. The system rechecks permissions, policy readiness, expected milestone revision and preview fingerprint inside the transaction. Saving a proposal, viewing a preview or rejecting a proposal does not alter approved capacity.

Once active, use **Propose a budget change** to allocate work, change the total/reserve, resize an active allocation or cancel an allocation with no issued units. Preview first, save the proposal, then make an explicit decision. A cancelled allocation remains visible in history; it is not deleted or resurrected in place. Reducing amounts below allocated/issued bounds is rejected.

An approval increments the milestone revision. Other pending proposals based on the old revision become stale and cannot be approved. After refreshing, an administrator may reject them with a reason or create new proposals using the current amounts. Duplicate decisions return a conflict rather than applying twice. History is paginated in groups of 20 and retains the exact reviewed snapshots and actors.

### Example without real earnings

Create a synthetic milestone with 1,000 total units and 100 protected reserve. Before approval, approved total remains zero. After approval, 900 are available to plan. Approve a 700-unit reconnection allocation: 200 remain available; no contributor has earned units. A further 201-unit allocation would breach the protected reserve and must be rejected.

Raising the total to 1,200 while retaining the same 700-unit allocation and 100 reserve leaves 400 available. The preview shows the allocation's planned share changing from 70.00% to 58.33% of the milestone total. This is **not** a person's earned or revenue share. The stored ratio is exact; the displayed percentage is rounded only for readability. Finalized personal-share/dilution explanations become possible after the ledger exists.

## Practical acceptance checklist for later testing

1. Create and approve a draft under a synthetic owner; observe that required acknowledgements still block milestone creation. Acknowledge as each required account and confirm readiness. A viewer cannot approve policy or budgets.
2. Create version 2; verify version 1 remains unchanged and version-2 acknowledgements start empty. Confirm old acknowledgements cannot be reused. A new effective version missing acknowledgements must block new milestones rather than fall back.
3. Add a contributor after approval; inspect the new acknowledgement requirement. Suspend an unacknowledged original participant and confirm the requirement does not vanish. Use a reviewed successor instead of editing records.
4. Perform the 1,000/100/700-unit example above. Verify preview and saved-pending proposal do not spend capacity. Inspect planned ratios in a total-budget amendment.
5. Open two administrator sessions and submit competing allocations against the same revision. Only capacity-valid, current-revision approvals may succeed. Repeated approval must not duplicate spending. Native PostgreSQL race tests exercise this independently when available.
6. Try invalid precision, negative/excessive amounts, invalid pool weights and mismatched project references. Check that errors do not create partial milestones or awards.
7. Test policy and milestone history at narrow widths and by keyboard. Inspect delayed/error refreshes and a role change in another session. Refresh should clear inaccessible data; already delivered information cannot be erased from someone's memory/browser.

## Local-pilot limits

Maximum 200 policy versions and 200 milestones per project, 500 proposals per milestone. Reaching a limit gives an explicit error; do not delete history to bypass it. Large-team performance is unmeasured. Policy lists are bounded, not an enterprise analytics interface. No policies/budgets are seeded at startup. Model settings, GitHub, work-package evidence, accepted units, financial statements and actual payments are still absent. Use synthetic data and keep the deployment local until all earlier verification and later security gates are satisfied.
