# Human review, contribution credit and disputes

Source 0.6.0-phase6. Use only synthetic local data until installation, independent review and team acceptance gates are completed. No payments, taxes, equity or AI assessment are implemented in this phase.

## The complete manual path

Create and approve a policy and obtain the required participant acknowledgements. Approve milestone/allocated work budgets. Create a complete work-package scope with independent deliverables and proposed attribution, approve it, start it, attach evidence and submit it. This phase begins from that submitted packet; earlier actions do not earn credit.

Open Work packages → the submitted package → Independent deliverable review. Expand a deliverable, inspect its exact proposed units, select the policy-required number of independent reviewers and enter the reason. The coordinator or an administrator may assign; a beneficiary may not act as the accepting reviewer merely because they administer the project. Each reviewer must have current reviewer/admin access and must not receive positive units anywhere in this package or be its submission author. Add a genuinely independent person through normal invitations/access/policy acknowledgement if no candidate exists. Separate accounts operated by one human do not establish real independence.

Reviewers sign in and open Human reviews → Inspect review. The page displays the captured evidence packet, source revisions, exact attribution, policy version and criterion requirements. Every criterion needs a finding (supported, unsupported or insufficient), explanation and applicable source references. Select accept only when the evidence warrants it; the presence of a reference proves neither the claim nor the quality of the work. A source link remains unverified until a human inspects the appropriate source. Missing evidence cannot be converted into a low contribution score. Reviewer comments are preserved; detailed findings are visible only to authorized reviewers/admins.

A vote records a decision but issues zero units. When every assigned reviewer accepts, one assigned independent reviewer explicitly confirms Finalize human-reviewed record against the exact decision set. The original policy, scope, evidence, membership and budgets are checked again. A successful transaction creates one award and its event lines and updates the projections. A repeated identical request returns its prior result, not a second award. Do not manually replay a timed-out command with modified data; refresh to inspect the recorded result.

## Partial completion

A 100-unit package can have a 60-unit implementation and 40-unit test deliverable. Accepting implementation issues only 60 units. The tests remain planned/unissued; unused milestone reserve belongs to nobody. An already-reviewed test deliverable can still finalize if its target is unchanged. Adding new test evidence makes unfinished rounds stale: explicitly resubmit current evidence, then start a new round for the tests. The first 60-unit award keeps its original packet. Finalizing the remaining 40 units completes the package.

Once any part is accepted, this version freezes the package's scope and proposed attribution. New evidence/resubmission is allowed for unfinished work, but editing or cancelling partially accepted scope is not. Major replanning should use separately budgeted new work; do not modify database projections manually. Releasing partially accepted residual budgets needs a future audited workflow.

## Reading contributions

The Contributions tab groups finalized units by named policy version, milestone and release/ongoing pool. The exact denominator and pending planned units are displayed. A contributor temporarily holding 100% of currently issued units has not necessarily earned 100% of the final game's revenue or ownership. Shares are rounded only for display. Amounts are contribution units, not dollars; project-wide totals are not a blended permanent share.

Inspect credit history to see current attribution reconstructed from event lines, the unchanged original award, source acceptance and signed adjustments. Removed or suspended members keep their historical identity/credit. Changing policy, retiring evidence or changing display names must not rewrite an award. In-app notification records are provided; no email or push notification is sent and there is no unread-state workflow yet.

## Disputes and corrections

Open an accepted award in Contributions → Raise an attribution concern. Enter a specific, project-visible reason. Filing creates no debit or new units; it marks the affected pool blocked for future financial closing. An already-open case for the award should receive supplementary notes instead of another parallel case.

In Disputes, an administrator assigns an independent resolver. Original beneficiaries, the complainant, original acceptance reviewers and reviewers of earlier finalized resolutions for this award cannot resolve their own outcome. The resolver reviews the immutable original decision and current credit plus supplementary notes. They propose either uphold or a complete replacement allocation totaling exactly the original accepted budget. Roles stay explicit. Previously credited departed people may retain or receive reallocated units for that award; a foreign-project identity cannot be introduced.

The same original-policy quorum reviews the proposal, including the resolver. Any proposed recipient is ineligible to review it. The resolver separately finalizes the fully approved proposal. Uphold closes the case without changing event lines. Reallocation appends linked debits and credits whose sum is zero; the original award remains. For example, an original 100-unit award to Alice followed by an approved 60/40 Alice/Bob allocation records Alice -40 and Bob +40. The accepted total remains 100, never 140.

New notes or a new resolver stale unfinished resolution votes. Resolved cases cannot be edited; new substantive concerns can open a new linked-to-award case. This release does not rescind the entire accepted budget, recover past payments, issue negative entitlement or automatically penalize later rewrites. Supplementary evidence here is bounded text/HTTPS reference, not a new unrestricted file-upload system for closed work.

## Verification and recovery

Administrators may GET the project's `/contributions/integrity` route. It reports whether all derived projections agree with immutable events and award totals; it never repairs through HTTP. A local operator can run the `check-credit` CLI described in ledger_operations.md. A rebuild changes only caches and records an audit event. It is not a shortcut to change who earned units.

Detailed routes: review_api.md. Deferred browser/role/accounting checks: testing_phase6.md. Upgrade: upgrade_phase6.md. Actual executed checks and unexecuted gates: test_results.json and project_status.md.
