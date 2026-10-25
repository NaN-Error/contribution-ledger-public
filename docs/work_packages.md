# Work packages and deliverables

Phase 4 adds a place to agree on useful work within an already approved budget. Code, art, QA, research, maintenance and production follow the same scope workflow. The inherited category and revenue-pool label come from the selected milestone allocation; they cannot be changed by relabeling a package.

**Every attribution amount here is proposed, not earned.** Creating, approving, starting or submitting a package does not issue units, accept evidence, calculate revenue, or prove authorship.

## First example

Sign in, open a project, and first complete the policy/milestone workflow described in `policies_and_budgets.md`. Use fictional data. Approve a 1,000-unit milestone with 100 units of protected reserve, then approve a 100-unit allocation for reconnection work. All required active non-viewer participants must acknowledge the pinned policy themselves. Joining collaborators can create a new acknowledgement requirement.

Open **Work packages**, refresh the available allocations, and choose **Create work package**. Select the approved allocation. Specify a title, useful outcome, measurable criteria, required evidence, coordinator and intended contributors. The selected allocation may belong to only one package.

For a 100-unit package, add these independently acceptable portions:

| Deliverable | Planning budget | Example evidence requirement |
|---|---:|---|
| Reconnection behavior | 60 units | Exact source revision and reproducible reconnection case |
| State-restoration tests | 25 units | Test report identifying the revision and failure cases |
| Integration guide | 15 units | Reviewed, versioned guide |

Assign the proposed contributor roles and amounts within each deliverable. Direct units permit three decimal places. Percentages permit two decimal places and are converted to exact atoms on the server. For example, a 60-unit deliverable split 75% / 25% proposes 45 / 15 units; those are not current revenue shares. A person can have different roles, but duplicate rows for the same person and role in one deliverable are rejected.

Save the draft with a reason. It is fine to save unfinished attribution or an unplanned portion of the parent budget; the detail screen names the blockers. Before planning approval, distribute the entire parent budget into deliverables and completely attribute each deliverable. Unassigned units stay visible and never become the owner's credit.

Review **Current scope**, then use **Work-package action → Approve this scope for work**. This is administrative scope approval, not independent credit acceptance. Select **Start work**, then **Submit readiness declaration** when the declared work is ready for a later review. Each state command requires a reason and explicit confirmation. A submission preserves the exact scope and proposed attribution rather than merely changing a free-text status.

## Scope changes and submission history

Use **Amend scope** to save a new immutable revision. Editing approved or in-progress work returns it to draft; the previous approval cannot authorize the new scope. A submitted package must first be withdrawn by its coordinator/administrator, or returned for changes by a reviewer/administrator. Old submissions remain available through **Recent submissions** and **Recorded changes**.

After withdrawal or a request for changes, save a new revision, approve it again, start, and submit. There is no need to alter a field just to force a new revision: a reasoned unchanged-scope resubmission is still recorded as a new reviewable revision. A stale browser tab receives a conflict rather than overwriting someone else's work. Refresh and review; do not blindly repeat the command.

The **Inspect scope** and **Inspect submission** controls read archived documents, including original participant labels and fingerprints. Display names are snapshots, not proofs of identity. Removed project access is rechecked when reading archives. Already delivered information cannot be erased from somebody's memory or browser by later removing access.

## Resizing or cancelling

A package cannot move to another milestone, policy or allocation. To change its budget, first return the package to draft with a scope amendment. If reducing the total, reduce its deliverable budgets/proposed allocations first. Then use **Milestones** to propose, inspect and approve the allocation resize. The system appends a scope revision bound to the new approved parent amount. Review and approve that scope again. Increasing a parent leaves an explicit unplanned remainder until the scope is amended; it is not automatic credit.

An administrator can cancel an unsubmitted, unaccepted package using **Cancel package and release its budget**. A submitted package must first be withdrawn/returned for changes. Cancellation approves the linked planning-budget release in the same transaction, preserves the package and all submissions, and leaves protected reserve unchanged. It is terminal; replacement work needs another allocation. Attempting cancellation twice cannot release capacity twice.

If any earned-credit projection is present, phase-4 editing/cancellation is blocked. Future independent-review and adjustment rules must handle that case; the application never deletes finalized credit to make a cancellation succeed.

## Roles

| Action | Required project access |
|---|---|
| Read lists, current scope and permitted archives | Any current project member, including viewer |
| Create package | Administrator or contributor |
| Amend, start, submit or withdraw | Administrator or explicitly assigned current coordinator with non-viewer access |
| Approve planning scope or cancel | Administrator |
| Request changes to submitted scope | Administrator or reviewer |
| Complete or award credit | Not available in phase 4 |

Workspace owners/admins inherit project administration as before. A coordinator's authority is scoped to the package they coordinate. Membership, policy readiness and amounts are rechecked on the server, not only by showing/hiding controls.

## Limits and current omissions

At most 200 packages/project, 30 deliverables/package revision and 30 attribution rows/deliverable are supported in this local pilot. A UTF-8 request must fit the bounded request size; reduce repeated text when the form reports a size limit. Search covers title/coordinator and category/state filters. `Completed` is a reserved filter; it has no actionable completion control yet.

There are no attachments, uploaded evidence, GitHub links fetched by the server, verified tests, contribution awards, AI evaluations or earnings in this phase. Text describing required evidence is a requirement, not the evidence itself. Phase 5 adds the evidence system; phase 6 adds independent acceptance and issued units.

## Deferred manual acceptance checklist

1. Preserve an existing phase-3 owner, policy and milestone through migration 0004 and a restart. Confirm unchanged earlier IDs and approved totals.
2. Create networking, animation and QA allocations/packages. They all use the same scope workflow; category/pool remain inherited. A second package using the same allocation is rejected.
3. Split the 100-unit example into 60/25/15. Attempt a 101-unit child total; reject it. Save an incomplete draft; approval must name the missing budgets/attribution. No issued units change.
4. Test direct units and percentages, two roles for one person, tiny amounts/rounding, missing attribution, duplicate roles and inactive or foreign-project participants.
5. Approve/start/submit; inspect the exact snapshot. Open the same revision in two tabs, amend from one, and verify the other's stale command is rejected.
6. Withdraw, amend, reapprove and resubmit. Original snapshot and audit events remain readable. Viewers cannot mutate and unrelated contributors cannot edit another coordinator's scope.
7. Try legacy budget resize/cancel while scope is approved. It must not bypass the package. Resize a permissible draft through reviewed budget amendments; inspect the automatically recorded new scope revision.
8. Cancel eligible unaccepted work. Only its budget becomes available again; reserve remains unchanged. Repeated cancellation has no second effect, and archived work cannot be rebound or deleted.
9. Remove access in another session. Subsequent list/detail/archive/action requests must be denied. No data from another workspace should appear by guessing IDs.
10. Test keyboard-only operation, mobile layout, slow/lost API responses, oversize scope messages, history pagination and reloading after provider-free operation. Run the supplied actual-browser smoke in a separate disposable deployment, not your normal database.

These are pending checks, not claims that a browser or user has already performed them.
