# Internal testing checklist

No step below is recorded as user-verified yet. Use fictional data first. Preserve logs and exact reproduction steps; do not reset a database to conceal a failure.

## Installation and basic access

A fresh source extraction must complete the pinned dependency installations, React typecheck, Vite build, migrations and startup. The browser must show actual API/database status. A seeded persistence marker must survive restart. If installation fails, stop here and record the error; downstream interface tests cannot be considered passed.

Create an owner and a project. Test invitation expiry/reuse, login/logout, password change and session revocation. Test a second workspace and verify that a member of one cannot inspect the other. Exercise viewer permissions through both the interface and direct endpoints. Optional MFA needs real browser enrollment, sign-out/sign-in and recovery-code tests before enabling it for a team.

## Complete manual workflow

Review a policy, create a successor, and verify that acknowledging the earlier version does not acknowledge the successor. Approve a 1,000-unit milestone with 100 protected reserve. Approve a 100-unit work allocation and reject an allocation exceeding the remaining capacity.

Create a package, divide it into 60/25/15-unit deliverables, propose complete attribution, approve scope, start work, attach a short report and submit. Test saving an incomplete draft versus trying to approve it. Stale edits must fail rather than overwrite newer scope.

Use a separate permitted reviewer account to inspect each criterion. Accept/finalize only the 60-unit deliverable; the remainder must stay pending. Repeat finalization and verify that it does not double credit. Attempt beneficiary self-approval and verify rejection. A person controlling all those accounts is a software test, not an independent human pilot.

Replace evidence and inspect the stale unfinished review. Existing accepted credit must not change. Try restricted evidence with a viewer, then suspend access and verify new downloads are blocked. Previously saved copies cannot be recalled.

## Contributions, disputes and calculations

Inspect pool denominators and filter one contributor without turning their share into 100%. Open a dispute, assign an independent resolver, and apply a reviewed reattribution without changing total issued units. Earlier history must remain intact.

Calculate a hypothetical distribution. Try zero-eligible-unit and disputed pools; their portions must remain blocked/unallocated rather than go to the owner. Save an example and confirm that later credit does not overwrite its captured result.

## Financial records and reproducible exports

Use fictional gross and net receipts. Attempt duplicate source lines and a fee already deducted from a linked net settlement. Unsupported/pending entries must not reduce an approved distribution. Test reserve/deficit carryforward and the sequential monthly scope.

Preview, propose and approve a synthetic close. Change an input before approval and verify stale-proposal rejection. Repeat closing and confirm there is only one closed record. Re-export the same close and compare bytes. Run the offline replay command. A later release-attribution correction must be prospective, not rewrite an earlier close.

Record a partial external-payment declaration, try the same provider/reference again, then void a mistaken declaration. None of these steps should send, reverse or independently verify money. Real-use finance must remain rejected.

## Optional integrations and evaluator

Only after the manual path works: authorize a small repository you control, inspect bounded history and omissions, map identities explicitly, and attach an exact source version. Verify that importing the same entity cannot double credit. Test disconnect and permissions using an authorized test installation; do not use a private unrelated repository.

Use the synthetic AI provider first. Inspect catalog → protocol probe → evidence profile → local packet → disclosure approval → payer approval → insufficient-evidence result → reviewer commentary. Commentary must not issue credit. Test stale packets, revocation, malformed output and an unavailable provider through the documented mocked fixtures before actual paid calls.

Live provider agreement, source disclosure, quota and billing behavior require separate authorized checks. Never supply real keys to a chat or source repository. The offline synthetic corpus does not prove model fairness or contribution accuracy.

## Recovery and remote deployment

Execute a coordinated native backup and restore into a new isolated deployment; inspect retained artifacts, MFA/provider key decryption and frozen distribution replay. Keep the original unchanged. Verify native database privileges and worker boundaries. Use the staged loopback browser drill before considering a private-network deployment. Public release and actual-compensation use are not enabled by this package.

## Reporting a defect

Record the candidate version, fresh/upgrade installation, OS/Docker version, command or screen, exact steps, expected result, actual result and sanitized error. Include a request ID when shown. Do not attach keys, `.env`, master files, database dumps, private source, or identifiable participant records. Use a small fictional example to reproduce the problem.
