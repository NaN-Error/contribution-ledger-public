# Historical review and contribution explanations

**Phase 12, source 0.12.0-phase12.** Use synthetic local data until installation, native, browser, security and human acceptance gates are complete.

## A worked workflow

1. Sign in as a project administrator. Approve the team's actual draft policy and obtain every required acknowledgement using Policies.
2. In Milestones, create a dedicated historical milestone, for example 1,000 units with 100 protected reserve. Explicitly approve its initial budget. Do not create work allocations yet.
3. In Historical review, create a batch using that empty milestone. Choose an inclusive UTC start and exclusive UTC end in the past. Record a description of the history to reconstruct, known omissions and a reference to the current retrospective agreement. Dates describe the work, not a backdated signature.
4. Inspect the exact historical scope, approved budget, current policy and existing recognized-credit baseline. Record an approval reason and confirm the reviewed scope. This still awards nothing.
5. Select a completed historical GitHub import inside that interval and group its captured records. Imports marked completed with omissions are permitted, with limitations visible. A batch can also be entirely manual: no repository is required to include artwork, testing, design, music or production.
6. Review each candidate. Inspect its pinned sources/provenance, replace generic grouping descriptions with useful outcomes, choose the category, and address every listed uncertainty. For every observed identity, explicitly identify a local participant or document why it is context rather than an asserted recipient. Matching an email or mapping suggestion does not assign credit. Merge/split draft groups when the captured relationships do not match useful outcomes.
7. Use the Missing-work queue so participants can report omitted contributions. Include a claim through a current candidate or decline it with a recorded explanation. Dispositions may be revised before archival; earlier decisions remain in history. Claims are not automatically accepted evidence.
8. In Milestones, allocate units to the intended historical outcome within the approved total and reserve. Return to Historical review and refresh. No unit amount is guessed from commit volume.
9. Choose Prepare work package. Inspect the pinned source contents and explicitly authorize project-evidence disclosure. Complete the normal scope form with coordinator, contributors, criteria, evidence requirements and independently budgeted deliverables. All budget and attribution must be assigned before this historical promotion; a draft candidate can remain incomplete beforehand.
10. The server creates an ordinary draft work package bound to that allocation. Open it in Work packages, inspect imported evidence, attach missing non-code artifacts, approve scope, start and submit. Independently assigned reviewers inspect the actual evidence and finalize accepted deliverables using Human reviews. Optional phase-11 AI can assist that evidence review only with its separate approvals. No new AI grouping is implemented here.
11. Return to the historical batch. All linked packages must be completed or an unaccepted cancelled package explicitly rejected. Draft groupings, included claims without accepted work, unlinked active allocations and unresolved affected disputes block archival. Reject irrelevant candidates without deleting their source claims. A linked package can never be rebound to another allocation; accepted credit cannot be removed through rejection.
12. Open Opening balance. Review the baseline and current pool denominators, each person's recognized share and the units specifically attributable to this batch. Other awards/corrections since scope approval are included in current credit and are not misrepresented as this batch's effects. Confirm the exact comparison and archive it. Changes before the command require a new review.

## What archival means

The award transactions occurred when each deliverable was finalized. Archiving an opening balance records existing recognized credit; it does not issue it again. No revenue is earned, transferred or legally vested by this screen. Later disputes can correct an award without rewriting this archived snapshot. Phase 13 separately implements financial closes and permanent release-share snapshots.

A closed historical scope is not automatically exhaustive. New work discovered later needs a new explicit batch/milestone, while an attribution error in an existing award uses its dispute process. A frozen milestone cannot be expanded by the older budget routes. Historical scope definitions cannot be silently edited; choose a new scope before using a wrong interval or agreement.

## Contribution overview

Each policy and contribution pool has its own denominator. Category and origin filters change that clearly labeled population. The person selector hides other rows but retains their units in the denominator. A 25% contributor does not become 100% merely because only their row is displayed. Departed participants' finalized units remain represented.

Pending planned units are unissued, unowned and not narrowed by the person display filter. A person with no accepted units may not have a finalized row yet; this is not a claim that their work had no value. The separate activity section counts retained source entities/versions for administrators and reviewers only. It is not a personal productivity ranking. Evidence snapshot counts show available archived references, not model certainty or proof of correctness.

## Privacy and duplicate handling

Historical batch definitions are visible to current project members. Raw candidate sources, identity claims, group history and opening-review inputs are administrator/reviewer-only. A missing claim is also visible to its author. Promotion explicitly shares its pinned source contents into ordinary project-visible work evidence; do not promote private source without reviewing that disclosure.

The importer does not reconstruct non-code work it never observed, execute binaries, call URLs or infer hours. Source claims deduplicate observed entity identity, not semantic work. Rephrased manual claims or different PRs for the same task still require human overlap review. The conservative source reservation can also block genuine shared-context reuse; regroup before promotion rather than bypassing it. Re-imports do not auto-award an opening balance.

## Limits

See ADR 0013 for exact pilot limits and the retained-data interpretation. The UI lists the latest 100 completed historical imports. Grouping fails above 500 observation rows and package promotion fails above 30 pinned records. Use bounded import scopes/groupings rather than assume a truncated list is complete. Candidate merge and split preserve prior documents and source movements in history.

Read `testing_phase12.md` for automated commands and the deferred full-browser walkthrough. The phase-7 simulator uses actual award acceptance times, not the original historical work dates.
